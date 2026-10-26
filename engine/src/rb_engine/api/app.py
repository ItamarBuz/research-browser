"""FastAPI application factory."""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from rb_engine import __version__
from rb_engine.api import health, library_api, models_api, online_api, system
from rb_engine.api.auth import require_token
from rb_engine.api.problems import register_problem_handlers
from rb_engine.runtime.container import EngineServices
from rb_engine.runtime.settings import EngineSettings

ServicesFactory = Callable[[], EngineServices]


def create_app(settings: EngineSettings, services_factory: ServicesFactory) -> FastAPI:
    """Services are built in the lifespan hook, so merely creating the app (e.g. to export
    the OpenAPI schema) never touches the disk or probes hardware."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        services = services_factory()
        app.state.services = services
        await services.start()
        try:
            yield
        finally:
            await services.stop()

    app = FastAPI(
        title="Research Browser Engine",
        version=__version__,
        # Interactive docs are off: the engine is a private sidecar, and the schema is
        # exported offline (rb_engine.export_openapi) to generate the TypeScript client.
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        dependencies=[Depends(require_token)],
        lifespan=lifespan,
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
    app.include_router(system.router)
    app.include_router(models_api.router)
    app.include_router(library_api.router)
    app.include_router(online_api.router)
    return app
