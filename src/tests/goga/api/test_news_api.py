"""Интеграционные тесты HTTP API новостей и репозитория

Тестам нужна работающая PostgreSQL по строке DATABASE_URL. Если БД недоступна,
тесты пропускаются (skip), а не падают.
"""

import datetime as dt

import httpx
import pytest
from httpx import ASGITransport
from sqlalchemy import text

from goga.api.app import create_app
from goga.api.tokens import create_token
from goga.data.news import NewsRepository
from goga.db.engine import (
    Base,
    get_engine,
    session_scope,
)

# Все async-тесты модуля выполняются в одном event loop, чтобы переиспользовать
# глобальный движок БД (его пул соединений привязан к создавшему его циклу).
pytestmark = pytest.mark.asyncio(loop_scope='session')


async def _prepare_db_and_token() -> str | None:
    """Создаёт схему, очищает таблицы и выпускает тестовый токен

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
        await session.execute(text('TRUNCATE news RESTART IDENTITY CASCADE'))
        await session.execute(text('TRUNCATE api_tokens RESTART IDENTITY CASCADE'))
        _, token = await create_token(session, 'pytest')
    return token


def _client() -> httpx.AsyncClient:
    """Асинхронный HTTP-клиент поверх ASGI-приложения без сетевого порта"""
    return httpx.AsyncClient(transport=ASGITransport(app=create_app()), base_url='http://test')


async def test_health_without_token():
    """/api/v1/health доступен без авторизации"""
    await _prepare_db_and_token()
    async with _client() as client:
        response = await client.get('/api/v1/health')
    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}


async def test_news_requires_token():
    """Без токена доступ к новостям запрещён (401)"""
    if await _prepare_db_and_token() is None:
        pytest.skip('PostgreSQL недоступна')
    async with _client() as client:
        assert (await client.get('/api/v1/news')).status_code == 401
        bad = await client.get('/api/v1/news', headers={'Authorization': 'Bearer wrong'})
        assert bad.status_code == 401


async def test_create_get_and_filter():
    """Создание новости, чтение по id и фильтр по статусу"""
    token = await _prepare_db_and_token()
    if token is None:
        pytest.skip('PostgreSQL недоступна')
    auth = {'Authorization': f'Bearer {token}'}
    async with _client() as client:
        created = await client.post(
            '/api/v1/news',
            headers=auth,
            json={'title': 'Заголовок', 'description': 'Текст', 'url': 'https://example.com'},
        )
        assert created.status_code == 201
        news_id = created.json()['id']
        assert created.json()['status'] == 'pending'

        fetched = await client.get(f'/api/v1/news/{news_id}', headers=auth)
        assert fetched.status_code == 200
        assert fetched.json()['title'] == 'Заголовок'

        pending = await client.get('/api/v1/news', headers=auth, params={'status': 'pending'})
        assert [item['id'] for item in pending.json()] == [news_id]


async def test_mark_shown_keeps_record():
    """Показанная новость не удаляется, а помечается Shown с shown_at"""
    token = await _prepare_db_and_token()
    if token is None:
        pytest.skip('PostgreSQL недоступна')
    auth = {'Authorization': f'Bearer {token}'}
    async with _client() as client:
        news_id = (await client.post('/api/v1/news', headers=auth, json={'title': 'Новость'})).json()['id']

        marked = await client.post(f'/api/v1/news/{news_id}/mark-shown', headers=auth)
        assert marked.status_code == 200
        assert marked.json()['status'] == 'shown'
        assert marked.json()['shown_at'] is not None

        # запись сохранилась и доступна
        still_there = await client.get(f'/api/v1/news/{news_id}', headers=auth)
        assert still_there.status_code == 200
        assert still_there.json()['status'] == 'shown'


async def test_schedule_order_and_due_for_today():
    """Порядок показа учитывает день и позицию; due_for_today исключает будущее и показанные"""
    if await _prepare_db_and_token() is None:
        pytest.skip('PostgreSQL недоступна')
    today = dt.date(2026, 6, 3)
    async with session_scope() as session:
        repository = NewsRepository(session)
        await repository.add(title='Завтра', scheduled_for=today + dt.timedelta(days=1), position=1)
        await repository.add(title='Сегодня-2', scheduled_for=today, position=2)
        await repository.add(title='Сегодня-1', scheduled_for=today, position=1)
        await repository.add(title='Без даты')

    async with session_scope() as session:
        repository = NewsRepository(session)
        due = list(await repository.due_for_today(limit=10, today=today))
        titles = [news.title for news in due]
        # сначала сегодняшние по позиции, затем без даты; завтрашняя исключена
        assert titles == ['Сегодня-1', 'Сегодня-2', 'Без даты']
        marked = await repository.mark_shown([news.id for news in due])
        assert marked == 3

    async with session_scope() as session:
        repository = NewsRepository(session)
        assert list(await repository.due_for_today(limit=10, today=today)) == []
