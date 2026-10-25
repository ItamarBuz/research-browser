"""RFC 7807 problem responses for engine errors and unexpected failures."""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from rb_engine.domain.errors import EngineError

logger = logging.getLogger(__name__)

PROBLEM_MEDIA_TYPE = "application/problem+json"


class Problem(BaseModel):
    type: str
    title: str
    status: int
    detail: str | None = None


def _problem_response(problem: Problem) -> JSONResponse:
    return JSONResponse(
        status_code=problem.status,
        content=problem.model_dump(exclude_none=True),
        media_type=PROBLEM_MEDIA_TYPE,
    )


async def _handle_engine_error(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, EngineError)
    return _problem_response(
        Problem(
            type=f"urn:rb-engine:problem:{exc.type_slug}",
            title=exc.title,
            status=exc.status_code,
            detail=exc.detail,
        )
    )


async def _handle_unexpected(_request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled engine error", exc_info=exc)
    # Never leak internals (paths, stack traces) to the client.
    return _problem_response(
        Problem(type="urn:rb-engine:problem:internal", title="Internal engine error", status=500)
    )


def register_problem_handlers(app: FastAPI) -> None:
    app.add_exception_handler(EngineError, _handle_engine_error)
    app.add_exception_handler(Exception, _handle_unexpected)
