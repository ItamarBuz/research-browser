"""Liveness endpoint the desktop shell polls while the engine starts."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from rb_engine import API_VERSION, __version__

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str
    api_version: int


@router.get("/health", operation_id="getHealth")
def get_health() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__, api_version=API_VERSION)
