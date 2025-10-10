from langchain.tools import tool

from goga.data.daily import DailyStandupParticipantsRepository

repository = DailyStandupParticipantsRepository()


@tool
def add_daily_standup_participants(participants: list[str]) -> None:
    """Доавляет новых участников Daily Standup"""
    repository.add_participants(participants)

@tool
def get_daily_standup_participants() -> str:
    """Возвращает всех участников Daily Standup через запятую"""
    return ', '.join(repository.get_all_participants())

@tool
def get_today_daily_standup_participant() -> str:
    """Возвращает сегодняшнего ведущего Daily Standup"""
    return repository.today_random_participant

@tool
def force_change_today_daily_standup_participant() -> str:
    """Меняет случайного ведущего Daily Standup на сегодня"""
    repository.force_change_today_random_participant()
    return repository.today_random_participant

