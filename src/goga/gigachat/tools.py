from pathlib import Path

from langchain.tools import tool
from pydantic import BaseModel, Field

from goga.data.daily import DailyRepository


class Participant(BaseModel):
    """Участник Daily Standup"""

    username: str = Field(description='Username в Telegram (без символа @), например: Kademn')
    name: str = Field(description='Имя участника, например: Павел')

_repository = None

def get_or_create_repository(daily_db_json: Path | str | None = None) -> DailyRepository:
    """Возвращает или создает репозиторий данных участников Daily Standup

    Позволяет инициировать репозиторий с необходимыми параметрами
    """
    global _repository
    if not _repository:
        if not daily_db_json:
            raise ValueError('daily_db_json is required')
        _repository = DailyRepository(daily_db_json)
    return _repository


@tool
def add_daily_standup_participants(participants: list[Participant]) -> None:
    """Добавляет новых участников Daily Standup.

    Args:
        participants: список участников с полями username (в Telegram, без @) и name (имя).
            Пример: [{"username": "pbass", "name": "Павел"}, {"username": "Kademn", "name": "Кирилл"}]
    """
    data = {p.username: p.name for p in participants}
    get_or_create_repository().add_participants(data)

@tool
def get_daily_standup_participants() -> str:
    """Возвращает всех участников Daily Standup через запятую"""
    participants = get_or_create_repository().get_all_participants()
    parts = []
    for username, name in participants.items():
        parts.append(f'{name} (@{username})')
    return ', '.join(parts)

def _format_moderator(repository, username: str) -> str:
    """Форматирует ведущего: имя и @username"""
    name = repository.get_name(username)
    return f'{name} (@{username})' if name else f'@{username}'

@tool
def get_today_daily_standup_moderator() -> str:
    """Возвращает сегодняшнего ведущего Daily Standup"""
    repository = get_or_create_repository()
    return _format_moderator(repository, repository.today_daily_standup_moderator)

@tool
def get_tomorrow_daily_standup_moderator() -> str:
    """Возвращает завтрашнего ведущего Daily Standup"""
    repository = get_or_create_repository()
    return _format_moderator(repository, repository.tomorrow_daily_standup_moderator)

@tool
def force_change_today_daily_standup_moderator() -> str:
    """Принудительно меняет назначенного ранее ведущего Daily Standup на сегодня"""
    repository = get_or_create_repository()
    repository.force_change_today_daily_standup_moderator()
    return _format_moderator(repository, repository.today_daily_standup_moderator)

