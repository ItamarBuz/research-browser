"""Bearer-token check shared by every route.

The token is generated per launch by the desktop shell, so other local processes and web
pages open in a browser cannot call the engine even though it listens on loopback.
"""

import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer(auto_error=False)


def require_token(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> None:
    expected: str = request.app.state.settings.token
    if credentials is None or not secrets.compare_digest(credentials.credentials, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid engine token",
            headers={"WWW-Authenticate": "Bearer"},
        )
