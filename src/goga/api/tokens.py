"""Сервис управления API-токенами

Токен имеет формат ``goga_<секрет>``. В БД хранится только SHA-256 хеш полного
токена и открытый префикс для опознания — сам токен показывается один раз при
выпуске. Используется как HTTP API (проверка токена), так и CLI ``goga-token``
(выпуск/просмотр/отзыв).
"""

import datetime as dt
import hashlib
import secrets
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goga.db.models import ApiToken

_TOKEN_BYTES = 32
_PREFIX_LENGTH = 12


def _hash_token(token: str) -> str:
    """Возвращает SHA-256 хеш токена в hex"""
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


async def create_token(session: AsyncSession, name: str) -> tuple[ApiToken, str]:
    """Выпускает новый токен для сервиса

    Args:
        session: асинхронная сессия БД
        name: уникальное имя сервиса-потребителя

    Returns:
        кортеж (запись ApiToken, полный токен в открытом виде). Полный токен
        возвращается единственный раз и в БД не сохраняется.

    Raises:
        sqlalchemy.exc.IntegrityError: если имя сервиса уже занято
        sqlalchemy.exc.SQLAlchemyError: при иной ошибке записи в БД
    """
    token = 'goga_' + secrets.token_urlsafe(_TOKEN_BYTES)
    record = ApiToken(name=name, token_prefix=token[:_PREFIX_LENGTH], token_hash=_hash_token(token))
    session.add(record)
    await session.flush()
    return record, token


async def verify_token(session: AsyncSession, token: str) -> ApiToken | None:
    """Проверяет токен и обновляет время последнего использования

    Args:
        session: асинхронная сессия БД
        token: полный токен из заголовка Authorization

    Returns:
        активная запись ApiToken или None, если токен не найден/отозван

    Raises:
        sqlalchemy.exc.SQLAlchemyError: при ошибке чтения/записи в БД
    """
    result = await session.execute(
        select(ApiToken).where(
            ApiToken.token_hash == _hash_token(token),
            ApiToken.revoked_at.is_(None),
        )
    )
    record = result.scalar_one_or_none()
    if record is not None:
        record.last_used_at = dt.datetime.now(dt.UTC)
        await session.flush()
    return record


async def list_tokens(session: AsyncSession) -> Sequence[ApiToken]:
    """Возвращает все токены (включая отозванные), новые первыми

    Raises:
        sqlalchemy.exc.SQLAlchemyError: при ошибке чтения из БД
    """
    result = await session.execute(select(ApiToken).order_by(ApiToken.created_at.desc()))
    return result.scalars().all()


async def revoke_token(session: AsyncSession, name: str) -> bool:
    """Отзывает токен по имени сервиса (без удаления записи)

    Args:
        session: асинхронная сессия БД
        name: имя сервиса

    Returns:
        True, если активный токен найден и отозван; False, если токен не найден
        или уже отозван

    Raises:
        sqlalchemy.exc.SQLAlchemyError: при ошибке записи в БД
    """
    result = await session.execute(select(ApiToken).where(ApiToken.name == name))
    record = result.scalar_one_or_none()
    if record is None or record.revoked_at is not None:
        return False
    record.revoked_at = dt.datetime.now(dt.UTC)
    await session.flush()
    return True
