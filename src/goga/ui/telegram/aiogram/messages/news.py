"""Команды управления новостями (для администраторов)

Новости хранятся в PostgreSQL. Показанные новости не удаляются, а помечаются
статусом Shown (это делает ежедневная задача/инструмент get_news). Команда
/news_delete выполняет физическое удаление и предназначена для ручной чистки.
"""

import datetime as dt
import logging
import re

import trafilatura
from aiogram import types
from aiogram.enums import ParseMode
from aiogram.filters import Command

from goga import config
from goga.data.news import NewsRepository
from goga.db.engine import session_scope
from goga.db.models import NewsStatus
from goga.gigachat.agents import get_goga_answer
from goga.ui.telegram.aiogram.bot import bot
from goga.ui.telegram.aiogram.dispatcher import dp

logger = logging.getLogger('Goga news')

ADD_NEWS_PROMPT = (
    'Тебе даны извлечённые данные статьи. Сформируй короткую новость на русском языке. '
    'Верни заголовок статьи и краткий анонс (2-3 предложения о сути, не более 30-35 слов). '
    'Ответ верни на русском языке строго в следующем формате без дополнительных комментариев:\n'
    'TITLE: заголовок\n'
    'DESCRIPTION:\n'
    'текст анонса'
)


def _is_developer(message: types.Message) -> bool:
    """Проверяет, является ли отправитель разработчиком"""
    if not message.from_user:
        return False
    return message.from_user.username in {user['username'] for user in config.CONFIG['users']['developers']}


def _extract_article(url: str) -> dict | None:
    """Извлекает заголовок, текст и дату статьи по ссылке

    Args:
        url: ссылка на статью

    Returns:
        словарь с ключами title, date, text, url или None, если не удалось
        загрузить/извлечь содержимое
    """
    downloaded = trafilatura.fetch_url(url)
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


def _parse_source_date(raw: str | None) -> dt.date | None:
    """Парсит дату публикации (ISO ГГГГ-ММ-ДД) или возвращает None"""
    if not raw:
        return None
    try:
        return dt.date.fromisoformat(raw[:10])
    except ValueError:
        return None


@dp.message(Command('news_add'))
async def add_news(message: types.Message):
    """Добавление новости: /news_add <ссылка на статью>"""
    if not _is_developer(message):
        return
    if not message.text:
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await bot.send_message(message.chat.id, 'Использование: /news\\_add <ссылка на статью>')
        return

    url = parts[1].strip()
    await bot.send_message(message.chat.id, 'Загружаю и анализирую статью...')

    article = _extract_article(url)
    if not article:
        await bot.send_message(message.chat.id, 'Не удалось загрузить или извлечь содержимое статьи.')
        return

    prompt = ADD_NEWS_PROMPT + '\n\n'
    prompt += f'Ссылка: {article["url"]}\n'
    prompt += f'Заголовок: {article["title"]}\n'
    prompt += f'Дата публикации: {article["date"]}\n'
    prompt += f'Текст статьи:\n{article["text"][:3000]}'

    answer = await get_goga_answer(message.chat.id, prompt)

    title_match = re.search(r'TITLE:\s*(.+)', answer)
    description_match = re.search(r'DESCRIPTION:\s*\n([\s\S]+)', answer)

    if not title_match or not description_match:
        await bot.send_message(
            message.chat.id,
            f'Не удалось распознать ответ. Ответ Гоги:\n\n{answer}',
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    title = title_match.group(1).strip()
    description = description_match.group(1).strip()

    async with session_scope() as session:
        news = await NewsRepository(session).add(
            title=title,
            description=description,
            url=url,
            source_date=_parse_source_date(article['date']),
            created_by=message.from_user.username if message.from_user else None,
        )
        news_id = news.id

    await bot.send_message(
        message.chat.id,
        f'Новость добавлена (id `{news_id}`):\n\n**{title}**\n{description}',
        parse_mode=ParseMode.MARKDOWN,
    )
    logger.info(f'Новость добавлена: id={news_id} {title!r}')


@dp.message(Command('news_list'))
async def list_news(message: types.Message):
    """Список непоказанных новостей: /news_list"""
    if not _is_developer(message):
        return

    async with session_scope() as session:
        items = await NewsRepository(session).list(limit=100)
        items = [news for news in items if news.status in (NewsStatus.Pending, NewsStatus.Scheduled)]

        if not items:
            await bot.send_message(message.chat.id, 'Нет непоказанных новостей.')
            return

        lines = []
        for news in items:
            when = news.scheduled_for.isoformat() if news.scheduled_for else 'без даты'
            lines.append(f'  `{news.id}`. {news.title} ({when})')

    text = 'Список непоказанных новостей:\n' + '\n'.join(lines)
    await bot.send_message(message.chat.id, text, parse_mode=ParseMode.MARKDOWN)


@dp.message(Command('news_delete'))
async def delete_news(message: types.Message):
    """Удаление новости: /news_delete <id>"""
    if not _is_developer(message):
        return
    if not message.text:
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().isdigit():
        await bot.send_message(message.chat.id, 'Использование: /news\\_delete <id из /news\\_list>')
        return

    news_id = int(parts[1].strip())
    async with session_scope() as session:
        deleted = await NewsRepository(session).delete(news_id)

    if deleted:
        await bot.send_message(message.chat.id, f'Новость удалена: id `{news_id}`', parse_mode=ParseMode.MARKDOWN)
        logger.info(f'Новость удалена: id={news_id}')
    else:
        await bot.send_message(message.chat.id, f'Новость с id {news_id} не найдена.')
