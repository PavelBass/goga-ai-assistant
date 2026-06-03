"""Тесты репозитория и HTTP API истории чата

Требуют работающую PostgreSQL по строке DATABASE_URL; если БД недоступна,
пропускаются (skip), а не падают (как в test_news_api). Юнит-тесты извлечения
полей сообщения, не требующие БД, вынесены в test_chat_history_extract.
"""

import datetime as dt

import httpx
import pytest
from httpx import ASGITransport
from sqlalchemy import text

from goga.api.app import create_app
from goga.api.tokens import create_token
from goga.data.chat_history import ChatHistoryRepository
from goga.db.engine import (
    Base,
    get_engine,
    session_scope,
)
from goga.db.models import MessageDirection

pytestmark = pytest.mark.asyncio(loop_scope='session')

_CHAT_ID = -1009999000111


async def _prepare_db_and_token() -> str | None:
    """Создаёт схему, очищает таблицы истории и выпускает тестовый токен

    Returns:
        полный токен для авторизации или None, если PostgreSQL недоступна
    """
    try:
        engine = get_engine()
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    except Exception:
        return None
    async with session_scope() as session:
        await session.execute(text('TRUNCATE message_media, messages, chats RESTART IDENTITY CASCADE'))
        await session.execute(text('TRUNCATE api_tokens RESTART IDENTITY CASCADE'))
        _, token = await create_token(session, 'pytest-history')
    return token


def _client() -> httpx.AsyncClient:
    """Асинхронный HTTP-клиент поверх ASGI-приложения без сетевого порта"""
    return httpx.AsyncClient(transport=ASGITransport(app=create_app()), base_url='http://test')


async def _seed_messages(count: int) -> None:
    """Записывает в историю count сообщений с tg_message_id 1..count"""
    async with session_scope() as session:
        repository = ChatHistoryRepository(session)
        await repository.upsert_chat(chat_id=_CHAT_ID, chat_type='supergroup', title='Команда')
        for index in range(1, count + 1):
            await repository.save_message(
                chat_id=_CHAT_ID,
                tg_message_id=index,
                direction=MessageDirection.Incoming,
                date=dt.datetime(2026, 6, 3, 12, index, tzinfo=dt.UTC),
                content_type='text',
                text=f'Сообщение {index}',
            )


async def test_save_message_is_idempotent():
    """Повторная вставка той же (chat_id, tg_message_id) игнорируется"""
    if await _prepare_db_and_token() is None:
        pytest.skip('PostgreSQL недоступна')
    async with session_scope() as session:
        repository = ChatHistoryRepository(session)
        await repository.upsert_chat(chat_id=_CHAT_ID, chat_type='supergroup')
        first = await repository.save_message(
            chat_id=_CHAT_ID,
            tg_message_id=1,
            direction=MessageDirection.Incoming,
            date=dt.datetime(2026, 6, 3, 12, 0, tzinfo=dt.UTC),
            content_type='text',
            text='раз',
        )
        second = await repository.save_message(
            chat_id=_CHAT_ID,
            tg_message_id=1,
            direction=MessageDirection.Incoming,
            date=dt.datetime(2026, 6, 3, 12, 0, tzinfo=dt.UTC),
            content_type='text',
            text='два',
        )
    assert first is not None
    assert second is None


async def test_apply_edit_updates_text():
    """apply_edit обновляет текст и проставляет edit_date"""
    if await _prepare_db_and_token() is None:
        pytest.skip('PostgreSQL недоступна')
    await _seed_messages(1)
    async with session_scope() as session:
        repository = ChatHistoryRepository(session)
        updated = await repository.apply_edit(
            chat_id=_CHAT_ID,
            tg_message_id=1,
            edit_date=dt.datetime(2026, 6, 3, 12, 30, tzinfo=dt.UTC),
            text='исправлено',
        )
        assert updated is True
    async with session_scope() as session:
        repository = ChatHistoryRepository(session)
        messages = await repository.latest(_CHAT_ID, limit=10)
    assert messages[0].text == 'исправлено'
    assert messages[0].edit_date is not None


async def test_latest_and_before_pagination():
    """Последние N отдаёт latest, предыдущую страницу — messages_before"""
    if await _prepare_db_and_token() is None:
        pytest.skip('PostgreSQL недоступна')
    await _seed_messages(5)
    async with session_scope() as session:
        repository = ChatHistoryRepository(session)
        latest = await repository.latest(_CHAT_ID, limit=2)
        before = await repository.messages_before(_CHAT_ID, before_id=4, limit=2)
    assert [m.tg_message_id for m in latest] == [4, 5]
    assert [m.tg_message_id for m in before] == [2, 3]


async def test_messages_api():
    """API отдаёт последние сообщения и страницу перед курсором, требует токен"""
    token = await _prepare_db_and_token()
    if token is None:
        pytest.skip('PostgreSQL недоступна')
    await _seed_messages(5)
    auth = {'Authorization': f'Bearer {token}'}
    async with _client() as client:
        assert (await client.get(f'/api/v1/chats/{_CHAT_ID}/messages')).status_code == 401

        chats = await client.get('/api/v1/chats', headers=auth)
        assert _CHAT_ID in [chat['id'] for chat in chats.json()]

        page = await client.get(f'/api/v1/chats/{_CHAT_ID}/messages', headers=auth, params={'limit': 2})
        body = page.json()
        assert [m['tg_message_id'] for m in body['messages']] == [4, 5]
        assert body['has_more'] is True
        assert body['oldest_id'] == 4

        prev = await client.get(f'/api/v1/chats/{_CHAT_ID}/messages', headers=auth, params={'before_id': 4, 'limit': 2})
        assert [m['tg_message_id'] for m in prev.json()['messages']] == [2, 3]


async def test_media_not_found_returns_404():
    """Запрос несуществующего/нескачанного медиа возвращает 404"""
    token = await _prepare_db_and_token()
    if token is None:
        pytest.skip('PostgreSQL недоступна')
    auth = {'Authorization': f'Bearer {token}'}
    async with _client() as client:
        response = await client.get(f'/api/v1/chats/{_CHAT_ID}/media/unknown', headers=auth)
    assert response.status_code == 404
