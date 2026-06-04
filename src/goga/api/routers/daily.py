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
    DailyPlanOut,
    ModeratorOut,
    ParticipantOut,
    PretendentsSwap,
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


@router.get('/plan', response_model=DailyPlanOut)
async def daily_plan():
    """Выгружает текущий план ведущих и участников дейли (полный дамп JSON)"""
    return _repository().daily_plan


@router.post('/plan/swap', response_model=DailyPlanOut)
async def swap_pretendents(payload: PretendentsSwap):
    """Меняет местами двух запланированных ведущих по их позициям в плане

    Raises:
        fastapi.HTTPException: 400, если позиция выходит за границы плана ведущих
    """
    repository = _repository()
    try:
        repository.swap_pretendents(payload.first, payload.second)
    except IndexError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    return repository.daily_plan


@router.delete('/plan/pretendents/{position}', response_model=DailyPlanOut)
async def remove_pretendent(position: int):
    """Удаляет запланированного ведущего по его позиции в плане

    Raises:
        fastapi.HTTPException: 404, если на указанной позиции нет ведущего
    """
    repository = _repository()
    try:
        repository.remove_pretendent(position)
    except IndexError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    return repository.daily_plan


@router.post('/plan/recreate', response_model=DailyPlanOut)
async def recreate_plan():
    """Пересоздаёт план ведущих заново из текущих участников дейли"""
    repository = _repository()
    repository.recreate_plan()
    return repository.daily_plan
