"""Эндпоинты Daily Standup (только чтение, защищены Bearer-токеном)

Источник данных в этой итерации — существующий JSON-репозиторий дейли
(DailyRepository). Перенос состояния дейли в PostgreSQL запланирован отдельно.
"""

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from goga.api.schemas import (
    ModeratorOut,
    ParticipantOut,
)
from goga.api.security import require_token
from goga.data.daily import DailyRepository
from goga.gigachat.tools import get_or_create_repository

router = APIRouter(
    prefix='/api/v1/daily',
    tags=['daily'],
    dependencies=[Depends(require_token)],
)


def _repository() -> DailyRepository:
    """Возвращает инициализированный репозиторий дейли

    Raises:
        fastapi.HTTPException: 503, если репозиторий ещё не инициализирован
    """
    try:
        return get_or_create_repository()
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='Репозиторий дейли не инициализирован',
        ) from error


@router.get('/moderator/today', response_model=ModeratorOut)
async def today_moderator():
    """Возвращает сегодняшнего ведущего Daily Standup"""
    repository = _repository()
    username = repository.today_daily_standup_moderator
    return ModeratorOut(username=username, name=repository.get_name(username))


@router.get('/moderator/tomorrow', response_model=ModeratorOut)
async def tomorrow_moderator():
    """Возвращает завтрашнего ведущего Daily Standup"""
    repository = _repository()
    username = repository.tomorrow_daily_standup_moderator
    return ModeratorOut(username=username, name=repository.get_name(username))


@router.get('/participants', response_model=list[ParticipantOut])
async def participants():
    """Возвращает всех участников Daily Standup"""
    repository = _repository()
    return [
        ParticipantOut(username=username, name=name) for username, name in repository.get_all_participants().items()
    ]
