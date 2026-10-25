"""FastAPI application factory."""

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from rb_engine import __version__
from rb_engine.api import health
from rb_engine.api.auth import require_token
from rb_engine.api.problems import register_problem_handlers
from rb_engine.runtime.settings import EngineSettings


def create_app(settings: EngineSettings) -> FastAPI:
    app = FastAPI(
        title="Research Browser Engine",
        version=__version__,
        # Interactive docs are off: the engine is a private sidecar, and the schema is
        # exported offline (rb_engine.export_openapi) to generate the TypeScript client.
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        dependencies=[Depends(require_token)],
    )
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    register_problem_handlers(app)
    app.include_router(health.router)
    return app
