# rb-engine

The local Python engine behind Research Browser. The desktop shell starts it as a sidecar
bound to `127.0.0.1`; every request must carry the per-launch bearer token.

```bash
uv sync
uv run rb-engine --port 8765 --token dev-token   # run standalone
uv run pytest                                    # tests
uv run ruff check . && uv run ruff format --check . && uv run mypy   # quality gates
uv run python -m rb_engine.export_openapi        # print the OpenAPI schema (source of the TS client)
```

Layout follows ports and adapters: `domain/` (models, errors) and `ports/` (Protocols) never
import from `adapters/`; `services/` orchestrate through ports; `api/` is the HTTP edge.
