from pathlib import Path

from langchain.tools import tool

from goga.data.daily import DailyRepository

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
def add_daily_standup_participants(participants: list[str]) -> None:
    """Добавляет новых участников Daily Standup"""
    get_or_create_repository().add_participants(participants)

@tool
def get_daily_standup_participants() -> str:
    """Возвращает всех участников Daily Standup через запятую"""
    return ', '.join(get_or_create_repository().get_all_participants())

@tool
def get_today_daily_standup_moderator() -> str:
    """Возвращает сегодняшнего ведущего Daily Standup"""
    return get_or_create_repository().today_daily_standup_moderator

@tool
def force_change_today_daily_standup_moderator() -> str:
    """Принудительно меняет назначенного ранее ведущего Daily Standup на сегодня"""
    get_or_create_repository().force_change_today_daily_standup_moderator()
    return get_or_create_repository().today_daily_standup_moderator

