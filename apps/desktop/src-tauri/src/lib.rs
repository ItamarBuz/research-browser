mod engine;

use std::sync::Mutex;

use tauri::{Manager, RunEvent, State};

use engine::{EngineConnection, EngineProcess};

/// The running engine, or the reason it failed to start (shown in the UI).
struct EngineState(Mutex<Result<EngineProcess, String>>);

#[tauri::command]
#[allow(clippy::needless_pass_by_value)] // Tauri injects `State` by value.
fn engine_connection(state: State<'_, EngineState>) -> Result<EngineConnection, String> {
    let guard = state
        .0
        .lock()
        .map_err(|_| "engine state poisoned".to_owned())?;
    guard
        .as_ref()
        .map(|process| process.connection().clone())
        .map_err(Clone::clone)
}

/// Builds and runs the desktop application.
///
/// # Panics
/// Panics if the Tauri runtime cannot be initialised (e.g. no webview available).
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            let process = EngineProcess::spawn().map_err(|err| {
                log::error!("{err}");
                err.to_string()
            });
            app.manage(EngineState(Mutex::new(process)));
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![engine_connection])
        .build(tauri::generate_context!())
        .expect("error while building the Tauri application")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                if let Ok(mut guard) = app.state::<EngineState>().0.lock() {
                    if let Ok(process) = guard.as_mut() {
                        process.shutdown();
                    }
                }
            }
        });
}
