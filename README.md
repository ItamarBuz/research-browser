# Research Browser

A local-first, open-source desktop app for academic research. You ask a question in Hebrew
or English. The app finds peer-reviewed papers and ranks them by a calibrated **match %**. It
**highlights the sentences that answer the question** and shows a **criticism %** derived from
how other papers cite each one. All AI processing runs on your machine and adapts to its
hardware. External LLM APIs are optional.

> Status: **M2 local library**: import your own PDFs and search them offline, in Hebrew and
> English, including cross-lingual search. Next is M3 (online academic sources). See the
> architecture plan for M3–M6.

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

### Developing the UI in a plain browser

Start the engine yourself, then point Vite at it:

```bash
(cd engine && RB_ENGINE_TOKEN=dev-token-0123456789 uv run rb-engine --port 8799)
(cd apps/desktop && VITE_ENGINE_URL=http://127.0.0.1:8799 VITE_ENGINE_TOKEN=dev-token-0123456789 pnpm dev)
```

## Performance tiers and models

At startup the engine measures RAM, CPU and GPU (NVIDIA through `nvidia-smi`, and Apple
Silicon). It picks a tier: **Lite** (under 12 GB), **Standard** (12 GB or more, or a 4 GB+ GPU)
or **Pro** (24 GB or more, or a 10 GB+ GPU). Each tier has a recommended set of models.
Users can override the tier in Settings, and `RB_TIER=lite|standard|pro` forces it for
testing.

The model catalog lives in two files:

- [`models.toml`](engine/src/rb_engine/catalog/models.toml): which models to offer. You edit
  this one.
- `models.lock.json`: the exact Hugging Face revision, size and SHA-256 of every file. This
  one is generated.

After editing `models.toml`, run `uv run python scripts/pin_models.py` from `engine/`. It also
rejects any license outside the permissive allowlist (Apache-2.0, MIT, BSD).

Downloads resume after interruptions and are verified against the pinned hashes before use.
They are stored in the per-user data folder (`%LOCALAPPDATA%\ResearchBrowser`,
`~/Library/Application Support/ResearchBrowser`, or `~/.local/share/ResearchBrowser`).
Override the location with `RB_DATA_DIR` or `--data-dir`.

## Local library and search

Import PDFs on the **Library** page by dropping them in or choosing files. Each file is
copied into the data folder and processed in the background:

1. **Read**: PDFium extracts the text of each page. Running headers, page numbers and
   end-of-line hyphenation are removed, and every sentence keeps its position in the original
   page text, ready for highlighting in M4.
2. **Split**: sentences are grouped into passages of about 120 words. Language is detected per
   passage and per document. Reference lists ("References", "מקורות") and author or
   affiliation lists are recognised by cheap text rules and kept in the library, but left out
   of the search index, so they never crowd out the paper's own text.
3. **Index**: body passages are embedded with the tier's multilingual model and stored in
   LanceDB, next to a keyword index. Hebrew words are indexed with and without their prefixes
   (ו/ה/ב/כ/ל/מ/ש), so "מחקר" also matches "והמחקר".

Search combines semantic and keyword matches with reciprocal rank fusion. The sources filter
limits results to English or Hebrew documents, or keeps all languages for cross-lingual
search (a Hebrew question finds English papers).

Documents imported before the embedding model is downloaded are parsed right away and indexed
later with **Index now**. Each embedding model has its own index, so changing the performance
tier asks for a re-index rather than mixing incompatible vectors. Scanned PDFs without a text
layer are reported as failed, because OCR is not supported yet.

To run the real-model test (it is skipped otherwise), point it at a downloaded E5 model:
`RB_TEST_EMBEDDER_DIR=<data dir>/models/embed-e5-small/<revision> uv run pytest tests/test_embedder.py`.

## How the shell and engine connect

1. Tauri reserves a free loopback port and generates a random token.
2. It starts the engine with `--port` and `--parent-pid`, and passes the token in the
   `RB_ENGINE_TOKEN` environment variable.
3. The UI calls the `engine_connection` command, then polls `GET /health` with the token.
4. The engine accepts only loopback connections, requests carrying the token, and the app's
   own origins (CORS). It exits by itself if the shell process disappears.
