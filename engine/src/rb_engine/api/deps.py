"""FastAPI dependencies that hand routes the engine services."""

from typing import Annotated

from fastapi import Depends, Request

from rb_engine.runtime.container import EngineServices


def get_services(request: Request) -> EngineServices:
    services: EngineServices = request.app.state.services
    return services


Services = Annotated[EngineServices, Depends(get_services)]
