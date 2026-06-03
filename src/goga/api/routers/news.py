"""Эндпоинты управления новостями (защищены Bearer-токеном)"""

import datetime as dt
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from goga.api.schemas import (
    NewsCreate,
    NewsOut,
    NewsUpdate,
)
from goga.api.security import require_token
from goga.data.news import NewsRepository
from goga.db.engine import get_session
from goga.db.models import NewsStatus

router = APIRouter(
    prefix='/api/v1/news',
    tags=['news'],
    dependencies=[Depends(require_token)],
)

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get('', response_model=list[NewsOut])
async def list_news(
    session: SessionDep,
    status_filter: Annotated[NewsStatus | None, Query(alias='status')] = None,
    scheduled_for: dt.date | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """Возвращает список новостей с фильтрами по статусу и дню показа"""
    items = await NewsRepository(session).list(
        status=status_filter, scheduled_for=scheduled_for, limit=limit, offset=offset
    )
    return list(items)


@router.post('', response_model=NewsOut, status_code=status.HTTP_201_CREATED)
async def create_news(payload: NewsCreate, session: SessionDep):
    """Создаёт новость"""
    return await NewsRepository(session).add(**payload.model_dump(exclude_none=True), created_by='api')


@router.get('/{news_id}', response_model=NewsOut)
async def get_news_item(news_id: int, session: SessionDep):
    """Возвращает новость по id"""
    news = await NewsRepository(session).get(news_id)
    if news is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Новость не найдена')
    return news


@router.patch('/{news_id}', response_model=NewsOut)
async def update_news(news_id: int, payload: NewsUpdate, session: SessionDep):
    """Обновляет поля новости (правка, перенос дня показа, порядок, статус)"""
    fields = payload.model_dump(exclude_unset=True)
    news = await NewsRepository(session).update(news_id, **fields)
    if news is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Новость не найдена')
    return news


@router.post('/{news_id}/mark-shown', response_model=NewsOut)
async def mark_news_shown(news_id: int, session: SessionDep):
    """Помечает новость показанной (без удаления)"""
    repository = NewsRepository(session)
    if await repository.get(news_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Новость не найдена')
    await repository.mark_shown([news_id])
    return await repository.get(news_id)


@router.delete('/{news_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_news_item(news_id: int, session: SessionDep):
    """Физически удаляет новость (админская очистка)"""
    if not await NewsRepository(session).delete(news_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Новость не найдена')
