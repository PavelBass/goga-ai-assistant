from pathlib import Path

from langchain.tools import tool
from pydantic import BaseModel, Field
from goga import config

from goga.data.daily import DailyRepository
from goga.data.news import NewsRepository


class Participant(BaseModel):
    """Участник Daily Standup"""

    username: str = Field(description='Username в Telegram (без символа @), например: Kademn')
    name: str = Field(description='Имя участника, например: Павел')

_repository = None
_news_repository = None

def get_or_create_news_repository(news_dir: Path | str | None = None) -> NewsRepository:
    """Возвращает или создает репозиторий новостей"""
    global _news_repository
    if not _news_repository:
        if not news_dir:
            raise ValueError('news_dir is required')
        _news_repository = NewsRepository(news_dir)
    return _news_repository

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

@tool
def get_news() -> str:
    """Возвращает список непрочитанных новостей для ежедневного сообщения.

    Каждая новость содержит заголовок, краткое описание и ссылку на оригинальную статью.
    Новости отсортированы от старых к новым. После вызова этого инструмента новости
    считаются показанными и перемещаются в архив.
    Если новостей нет, возвращает пустую строку.
    """
    limit = config.CONFIG['news']['limit']
    news_repo = get_or_create_news_repository()
    items = news_repo.get_news(limit=limit)
    if not items:
        return ''
    news_repo.mark_as_seen(limit=limit)
    parts = []
    for i, item in enumerate(items, 1):
        first_line, content = item.split('\n', maxsplit=1)
        first_line = first_line.lstrip('# ').strip()
        parts.append(f'<news id={i}>\n<title>**{first_line}**</title>\n<description>{content}</description>\n</news>')
    return '\n\n'.join(parts)

