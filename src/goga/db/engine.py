"""Подключение к PostgreSQL и фабрика асинхронных сессий

Строка подключения берётся из переменной окружения ``DATABASE_URL`` и должна
использовать асинхронный драйвер, например:
``postgresql+asyncpg://goga:***@localhost:5432/goga``.
"""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from dotenv import (
    find_dotenv,
    load_dotenv,
)
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

load_dotenv(find_dotenv())


class Base(DeclarativeBase):
    """Базовый декларативный класс для всех ORM-моделей"""


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_database_url() -> str:
    """Возвращает строку подключения к БД из окружения

    Raises:
        RuntimeError: если переменная окружения DATABASE_URL не задана
    """
    url = os.environ.get('DATABASE_URL')
    if not url:
        raise RuntimeError('Переменная окружения DATABASE_URL не задана')
    return url


def get_engine() -> AsyncEngine:
    """Возвращает (лениво создавая) асинхронный движок SQLAlchemy

    Raises:
        RuntimeError: если переменная окружения DATABASE_URL не задана
    """
    global _engine
    if _engine is None:
        _engine = create_async_engine(get_database_url(), pool_pre_ping=True)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Возвращает (лениво создавая) фабрику асинхронных сессий

    Raises:
        RuntimeError: если переменная окружения DATABASE_URL не задана
    """
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _sessionmaker


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Контекстный менеджер сессии с автоматическим commit/rollback

    Raises:
        Exception: пробрасывает любое исключение из тела блока, предварительно
            откатив транзакцию
    """
    session = get_sessionmaker()()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI-зависимость: отдаёт сессию на время обработки запроса"""
    async with session_scope() as session:
        yield session
