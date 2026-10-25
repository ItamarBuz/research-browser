//! Lifecycle of the Python engine sidecar.
//!
//! The shell picks a free loopback port and a random per-launch token, starts the engine,
//! and hands both to the webview through the `engine_connection` command. The engine also
//! receives our PID and exits by itself if we die without cleaning up.

use std::net::TcpListener;
use std::path::PathBuf;
use std::process::{Child, Command};

use serde::Serialize;
use uuid::Uuid;

const TOKEN_ENV_VAR: &str = "RB_ENGINE_TOKEN";
/// Overrides how the engine is launched, e.g. `RB_ENGINE_CMD="python -m rb_engine"`.
const COMMAND_OVERRIDE_ENV_VAR: &str = "RB_ENGINE_CMD";

#[derive(Debug, thiserror::Error)]
pub enum EngineError {
    #[error("could not reserve a loopback port: {0}")]
    Port(#[source] std::io::Error),
    #[error("could not start the engine ({program}): {source}")]
    Spawn {
        program: String,
        #[source]
        source: std::io::Error,
    },
    #[error("engine launch command is empty")]
    EmptyCommand,
    #[error("could not locate the bundled engine: {0}")]
    Locate(#[source] std::io::Error),
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct EngineConnection {
    pub base_url: String,
    pub token: String,
}

pub struct EngineProcess {
    child: Child,
    connection: EngineConnection,
}

impl EngineProcess {
    pub fn spawn() -> Result<Self, EngineError> {
        let port = reserve_loopback_port()?;
        let token = new_token();
        let mut command = launch_command()?;
        command
            .args(["--port", &port.to_string()])
            .args(["--parent-pid", &std::process::id().to_string()])
            .env(TOKEN_ENV_VAR, &token);
        hide_console_window(&mut command);

        let program = command.get_program().to_string_lossy().into_owned();
        let child = command
            .spawn()
            .map_err(|source| EngineError::Spawn { program, source })?;
        log::info!("engine started (pid {}) on port {port}", child.id());

        Ok(Self {
            child,
            connection: EngineConnection {
                base_url: format!("http://127.0.0.1:{port}"),
                token,
            },
        })
    }

    pub fn connection(&self) -> &EngineConnection {
        &self.connection
    }

    pub fn shutdown(&mut self) {
        if let Err(err) = self.child.kill() {
            log::warn!("failed to stop engine: {err}");
        }
        let _ = self.child.wait();
    }
}

impl Drop for EngineProcess {
    fn drop(&mut self) {
        if matches!(self.child.try_wait(), Ok(None)) {
            self.shutdown();
        }
    }
}

/// Asks the OS for a free port. There is a small window before the engine binds it; a
/// collision there only surfaces as an engine start failure the UI reports and can retry.
fn reserve_loopback_port() -> Result<u16, EngineError> {
    let listener = TcpListener::bind(("127.0.0.1", 0)).map_err(EngineError::Port)?;
    Ok(listener.local_addr().map_err(EngineError::Port)?.port())
}

fn new_token() -> String {
    // Two v4 UUIDs = 244 bits from the OS CSPRNG.
    format!("{}{}", Uuid::new_v4().simple(), Uuid::new_v4().simple())
}

fn launch_command() -> Result<Command, EngineError> {
    if let Ok(raw) = std::env::var(COMMAND_OVERRIDE_ENV_VAR) {
        let mut parts = raw.split_whitespace();
        let program = parts.next().ok_or(EngineError::EmptyCommand)?;
        let mut command = Command::new(program);
        command.args(parts);
        return Ok(command);
    }
    if cfg!(debug_assertions) {
        // Development: run the engine from source through uv.
        let engine_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../engine");
        let mut command = Command::new("uv");
        command
            .arg("run")
            .arg("--project")
            .arg(engine_dir)
            .arg("rb-engine");
        return Ok(command);
    }
    // Release: the frozen engine ships next to the app executable (Tauri `externalBin`).
    let exe = std::env::current_exe().map_err(EngineError::Locate)?;
    let dir = exe.parent().map(PathBuf::from).unwrap_or_default();
    Ok(Command::new(dir.join(format!(
        "rb-engine{}",
        std::env::consts::EXE_SUFFIX
    ))))
}

#[cfg(windows)]
fn hide_console_window(command: &mut Command) {
    use std::os::windows::process::CommandExt;
    const CREATE_NO_WINDOW: u32 = 0x0800_0000;
    command.creation_flags(CREATE_NO_WINDOW);
}

#[cfg(not(windows))]
fn hide_console_window(_command: &mut Command) {}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn tokens_are_long_and_unique() {
        let (a, b) = (new_token(), new_token());
        assert_eq!(a.len(), 64);
        assert_ne!(a, b);
    }

    #[test]
    fn reserves_a_nonzero_port() {
        assert_ne!(reserve_loopback_port().unwrap(), 0);
    }
}
