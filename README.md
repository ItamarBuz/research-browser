# Research Browser

A local-first, open-source desktop app for academic research. You ask a question in Hebrew
or English. The app finds peer-reviewed papers and ranks them by a calibrated **match %**. It
**highlights the sentences that answer the question** and shows a **criticism %** derived from
how other papers cite each one. All AI processing runs on your machine and adapts to its
hardware. External LLM APIs are optional.

> Status: **M0 scaffold**: desktop shell, engine sidecar and the health handshake. See the
> architecture plan for milestones M1–M6.

## Layout

| Path | What |
|---|---|
| `engine/` | Python 3.12 engine (FastAPI), ports-and-adapters architecture |
| `apps/desktop/` | Tauri v2 shell + React/TypeScript UI (Hebrew RTL / English) |
| `apps/desktop/src-tauri/` | Rust: launches the engine sidecar, hands the UI its port and token |
| `.github/workflows/ci.yml` | Lint, type checks and tests on Windows, macOS and Linux |

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (it installs Python 3.12 automatically)
- Node 24 and pnpm 10
- Rust (stable) plus the [Tauri v2 prerequisites](https://v2.tauri.app/start/prerequisites/)
  for your OS (MSVC Build Tools + WebView2 on Windows; webkit2gtk on Linux)

## Develop

```bash
pnpm install
(cd engine && uv sync)
pnpm dev            # opens the desktop app; the engine starts automatically
```

Quality gates (CI runs the same):

```bash
(cd engine && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest)
pnpm lint && pnpm typecheck && pnpm test
(cd apps/desktop/src-tauri && cargo clippy --all-targets -- -D warnings && cargo test)
```

After changing engine routes or models, regenerate the typed client with `pnpm gen:api`.

## How the shell and engine connect

1. Tauri reserves a free loopback port and generates a random token.
2. It starts the engine with `--port` and `--parent-pid`, and passes the token in the
   `RB_ENGINE_TOKEN` environment variable.
3. The UI calls the `engine_connection` command, then polls `GET /health` with the token.
4. The engine accepts only loopback connections, requests carrying the token, and the app's
   own origins (CORS). It exits by itself if the shell process disappears.
