"""Эндпоинты управления новостями (защищены Bearer-токеном)"""

import datetime as dt
from itertools import groupby
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
    NewsFromUrl,
    NewsOut,
    NewsPlanDayOut,
    NewsPlanOut,
    NewsReorder,
    NewsUpdate,
)
from goga.api.security import require_token
from goga.data.news import NewsRepository
from goga.data.news_ingest import (
    API_INGEST_SOURCE_ID,
    NewsIngestError,
    ingest_news_from_url,
)
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
    """Создаёт новость с готовым текстом (title + description)"""
    return await NewsRepository(session).add(**payload.model_dump(exclude_none=True), created_by='api')


@router.post('/from-url', response_model=NewsOut, status_code=status.HTTP_201_CREATED)
async def create_news_from_url(payload: NewsFromUrl, session: SessionDep):
    """Создаёт новость из ссылки: Гога скачивает статью и сам делает анонс

    Raises:
        fastapi.HTTPException: 422 — не удалось скачать/извлечь статью;
            502 — LLM вернул ответ не в ожидаемом формате
    """
    try:
        return await ingest_news_from_url(
            session,
            payload.url,
            created_by='api',
            source_id=API_INGEST_SOURCE_ID,
            scheduled_for=payload.scheduled_for,
            position=payload.position,
        )
    except NewsIngestError as error:
        if error.kind == 'download':
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail='Не удалось загрузить или извлечь содержимое статьи',
            ) from error
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail='LLM вернул ответ не в ожидаемом формате',
        ) from error


@router.get('/plan', response_model=NewsPlanOut)
async def news_plan(
    session: SessionDep,
    from_: Annotated[dt.date | None, Query(alias='from')] = None,
    days: Annotated[int, Query(ge=1, le=60)] = 7,
):
    """Возвращает план показа: новости по дням на период + непоказанные без даты

    Период — [from; from + days - 1] включительно (from по умолчанию — сегодня).
    """
    repository = NewsRepository(session)
    start = from_ or dt.date.today()
    end = start + dt.timedelta(days=days - 1)

    scheduled = await repository.scheduled_between(start, end)
    plan_days = [
        NewsPlanDayOut(date=day, items=[NewsOut.model_validate(news) for news in group])
        for day, group in groupby(scheduled, key=lambda news: news.scheduled_for)
    ]

    pending = await repository.list(status=NewsStatus.Pending, limit=500)
    undated = [NewsOut.model_validate(news) for news in pending if news.scheduled_for is None]
    return NewsPlanOut(days=plan_days, undated=undated)


@router.put('/plan/{plan_date}', response_model=NewsPlanDayOut)
async def set_news_plan(plan_date: dt.date, payload: NewsReorder, session: SessionDep):
    """Задаёт план показа на день: дату и порядок для перечисленных новостей

    Каждой новости из ids проставляется scheduled_for=plan_date и position =
    индекс в списке (0..N-1); статус Pending переводится в Scheduled.

    Raises:
        fastapi.HTTPException: 404 — какой-то id не найден; 400 — новость уже
            показана/архивирована и не может быть в плане
    """
    repository = NewsRepository(session)
    try:
        items = await repository.reorder_day(plan_date, payload.ids)
    except KeyError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'Новость не найдена: id {error.args[0]}',
        ) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    return NewsPlanDayOut(date=plan_date, items=[NewsOut.model_validate(news) for news in items])


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
