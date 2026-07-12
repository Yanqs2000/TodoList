import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from .config import Settings


def require_token(
    settings: Annotated[Settings, Depends(Settings.from_env)],
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    scheme, separator, supplied_token = (authorization or "").partition(" ")
    valid_scheme = bool(separator) and scheme.lower() == "bearer"
    valid_token = secrets.compare_digest(supplied_token.encode(), settings.token.encode())
    if not valid_scheme or not valid_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        )
