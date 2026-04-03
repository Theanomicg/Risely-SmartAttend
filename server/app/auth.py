from __future__ import annotations

from fastapi import Header, HTTPException, Query, status

from app.config import get_settings


settings = get_settings()


def _validate_token(token: str | None, allowed_tokens: list[str]) -> None:
    if not settings.auth_enabled:
        return

    expected_tokens = [value for value in allowed_tokens if value]
    if token and token in expected_tokens:
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized.",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def require_teacher_access(
    x_smartattend_token: str | None = Header(default=None),
    token: str | None = Query(default=None),
) -> None:
    _validate_token(x_smartattend_token or token, [settings.teacher_token, settings.admin_token])


async def require_admin_access(
    x_smartattend_token: str | None = Header(default=None),
    token: str | None = Query(default=None),
) -> None:
    _validate_token(x_smartattend_token or token, [settings.admin_token])


def authorize_websocket(token: str | None = Query(default=None)) -> None:
    _validate_token(token, [settings.teacher_token, settings.admin_token])
