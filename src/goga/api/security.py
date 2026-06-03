"""Авторизация запросов к HTTP API по сервисному Bearer-токену"""

from typing import Annotated

from fastapi import (
    Depends,
    HTTPException,
    status,
)
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from sqlalchemy.ext.asyncio import AsyncSession

from goga.api.tokens import verify_token
from goga.db.engine import get_session
from goga.db.models import ApiToken

_bearer = HTTPBearer(auto_error=False, description='Сервисный токен, выпущенный Гогой')


async def require_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ApiToken:
    """FastAPI-зависимость: пропускает запрос только с действующим токеном

    Args:
        credentials: разобранный заголовок Authorization (или None)
        session: асинхронная сессия БД

    Returns:
        запись активного токена, которым авторизован запрос

    Raises:
        fastapi.HTTPException: 401, если токен отсутствует, недействителен или отозван
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Требуется Bearer-токен',
            headers={'WWW-Authenticate': 'Bearer'},
        )
    token = await verify_token(session, credentials.credentials)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Недействительный или отозванный токен',
            headers={'WWW-Authenticate': 'Bearer'},
        )
    return token
