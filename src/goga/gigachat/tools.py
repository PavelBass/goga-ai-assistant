import contextvars
from pathlib import Path

from langchain.tools import tool
from pydantic import BaseModel, Field

from goga import config
from goga.data.daily import DailyRepository
from goga.data.news import NewsRepository
from goga.db.engine import session_scope

# Управляет побочным эффектом get_news: помечать ли отданные новости показанными.
# По умолчанию True (боевой показ). Режим предпросмотра (тест-показ в dev-чат)
# выставляет False на время вызова агента, чтобы тестовая отправка не «сжигала»
# новости. get_news — async-инструмент, LangGraph ждёт его в том же контексте,
# поэтому значение долетает до вызова без явной передачи через цепочку агента.
news_mark_shown: contextvars.ContextVar[bool] = contextvars.ContextVar('news_mark_shown', default=True)


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


@tool
async def get_news() -> str:
    """Возвращает список непоказанных новостей для ежедневного сообщения.

    Каждая новость содержит заголовок, ссылку на оригинальную статью и краткое
    описание. Новости отсортированы по плану показа. После вызова этого
    инструмента новости считаются показанными (помечаются Shown), но не
    удаляются из базы. Если новостей нет, возвращает пустую строку.

    В режиме предпросмотра (ContextVar ``news_mark_shown`` == False, его
    выставляет тест-показ в dev-чат) новости отдаются, но показанными НЕ
    помечаются — чтобы тестовая отправка не «сжигала» план показа.
    """
    limit = config.CONFIG['news']['limit']
    async with session_scope() as session:
        repository = NewsRepository(session)
        items = list(await repository.due_for_today(limit))
        if not items:
            return ''
        parts = []
        for i, news in enumerate(items, 1):
            url_tag = f'<url>{news.url}</url>\n' if news.url else ''
            parts.append(
                f'<news id={i}>\n<title>**{news.title}**</title>\n'
                f'{url_tag}<description>{news.description}</description>\n</news>'
            )
        if news_mark_shown.get():
            await repository.mark_shown([news.id for news in items])
    return '\n\n'.join(parts)
