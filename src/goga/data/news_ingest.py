"""Ингест новости из ссылки: скачивание статьи и сжатие её LLM в анонс

Общий сервис для телеграм-команды ``/news_add`` и HTTP API
(``POST /api/v1/news/from-url``). Логика одна, поэтому живёт здесь, а не в слое
UI: оба вызывающих кода передают свою асинхронную сессию (репозиторий не делает
commit сам — это остаётся за ``session_scope``/FastAPI-зависимостью).

Блокирующий ``trafilatura.fetch_url`` выполняется в отдельном потоке через
``asyncio.to_thread``, чтобы не вставать в общий event loop (в нём крутятся и
поллинг aiogram, и uvicorn API).
"""

import asyncio
import datetime as dt
import re

import trafilatura
from sqlalchemy.ext.asyncio import AsyncSession

from goga.data.news import NewsRepository
from goga.db.models import News

# Источник (thread_id памяти LLM) для ингеста через API — отдельный от чатов,
# чтобы текст статьи не подмешивался в память разговоров.
API_INGEST_SOURCE_ID = 'api:news-ingest'

ADD_NEWS_PROMPT = (
    'Тебе даны извлечённые данные статьи. Сформируй короткую новость на русском языке. '
    'Верни заголовок статьи и краткий анонс (2-3 предложения о сути, не более 30-35 слов). '
    'Ответ верни на русском языке строго в следующем формате без дополнительных комментариев:\n'
    'TITLE: заголовок\n'
    'DESCRIPTION:\n'
    'текст анонса'
)


class NewsIngestError(Exception):
    """Ошибка ингеста новости из ссылки

    Attributes:
        kind: вид ошибки — 'download' (не удалось скачать/извлечь статью) или
            'parse' (LLM вернул ответ не в ожидаемом формате)
        raw: сырой ответ LLM (только для kind='parse', иначе None)
    """

    def __init__(self, kind: str, *, raw: str | None = None) -> None:
        self.kind = kind
        self.raw = raw
        super().__init__(f'Не удалось добавить новость из ссылки: {kind}')


async def extract_article(url: str) -> dict | None:
    """Извлекает заголовок, текст и дату статьи по ссылке

    Скачивание блокирующее, поэтому выполняется в отдельном потоке.

    Args:
        url: ссылка на статью

    Returns:
        словарь с ключами title, date, text, url или None, если не удалось
        загрузить/извлечь содержимое

    Raises:
        Exception: пробрасывает ошибки сети/парсинга из trafilatura
    """
    downloaded = await asyncio.to_thread(trafilatura.fetch_url, url)
    if not downloaded:
        return None
    metadata = trafilatura.extract_metadata(downloaded)
    text = trafilatura.extract(downloaded)
    if not text:
        return None
    return {
        'title': metadata.title if metadata else '',
        'date': metadata.date if metadata else '',
        'text': text,
        'url': url,
    }


def parse_source_date(raw: str | None) -> dt.date | None:
    """Парсит дату публикации (ISO ГГГГ-ММ-ДД) или возвращает None

    Args:
        raw: строка с датой (берутся первые 10 символов) или None

    Raises:
        Не бросает исключений: некорректная дата трактуется как None
    """
    if not raw:
        return None
    try:
        return dt.date.fromisoformat(raw[:10])
    except ValueError:
        return None


async def summarize_article(article: dict, source_id: str | int | float) -> tuple[str, str]:
    """Сжимает статью в заголовок и анонс через LLM

    Args:
        article: данные статьи из extract_article (title, date, text, url)
        source_id: идентификатор треда памяти LLM (chat id или служебная строка)

    Returns:
        кортеж (title, description) — заголовок и текст анонса

    Raises:
        NewsIngestError: kind='parse', если LLM вернул ответ не в формате
            TITLE/DESCRIPTION (в raw кладётся сырой ответ)
    """
    # Ленивый импорт: построение GigaChat-агента происходит при первом обращении,
    # а не при сборке FastAPI-приложения (news-роутер импортирует этот модуль).
    from goga.gigachat.agents import get_goga_answer

    prompt = ADD_NEWS_PROMPT + '\n\n'
    prompt += f'Ссылка: {article["url"]}\n'
    prompt += f'Заголовок: {article["title"]}\n'
    prompt += f'Дата публикации: {article["date"]}\n'
    prompt += f'Текст статьи:\n{article["text"][:3000]}'

    answer = await get_goga_answer(source_id, prompt)

    title_match = re.search(r'TITLE:\s*(.+)', answer)
    description_match = re.search(r'DESCRIPTION:\s*\n([\s\S]+)', answer)
    if not title_match or not description_match:
        raise NewsIngestError('parse', raw=answer)

    return title_match.group(1).strip(), description_match.group(1).strip()


async def ingest_news_from_url(
    session: AsyncSession,
    url: str,
    *,
    created_by: str | None,
    source_id: str | int | float,
    scheduled_for: dt.date | None = None,
    position: int | None = None,
) -> News:
    """Создаёт новость из ссылки: скачивает статью, сжимает LLM и сохраняет

    Сессию commit-ит вызывающая сторона (репозиторий лишь flush-ит).

    Args:
        session: асинхронная сессия БД
        url: ссылка на статью
        created_by: источник добавления (telegram username или имя сервиса)
        source_id: идентификатор треда памяти LLM (chat id или служебная строка)
        scheduled_for: день, на который запланирован показ (опционально)
        position: порядок показа в пределах дня (опционально)

    Returns:
        созданная новость с заполненным id

    Raises:
        NewsIngestError: kind='download', если не удалось скачать/извлечь статью;
            kind='parse', если LLM вернул ответ не в ожидаемом формате
        sqlalchemy.exc.SQLAlchemyError: при ошибке записи в БД
    """
    article = await extract_article(url)
    if not article:
        raise NewsIngestError('download')

    title, description = await summarize_article(article, source_id)

    return await NewsRepository(session).add(
        title=title,
        description=description,
        url=url,
        source_date=parse_source_date(article['date']),
        scheduled_for=scheduled_for,
        position=position,
        created_by=created_by,
    )
