"""Команды управления новостями (для администраторов)

Новости хранятся в PostgreSQL. Показанные новости не удаляются, а помечаются
статусом Shown (это делает ежедневная задача/инструмент get_news). Команда
/news_delete выполняет физическое удаление и предназначена для ручной чистки.

Логика «добавить новость из ссылки» вынесена в общий сервис
goga.data.news_ingest (его же использует HTTP API), здесь — только UX команды.
"""

import logging

from aiogram import types
from aiogram.enums import ParseMode
from aiogram.filters import Command

from goga import config
from goga.data.news import NewsRepository
from goga.data.news_ingest import (
    NewsIngestError,
    ingest_news_from_url,
)
from goga.db.engine import session_scope
from goga.db.models import NewsStatus
from goga.ui.telegram.aiogram.bot import bot
from goga.ui.telegram.aiogram.dispatcher import dp

logger = logging.getLogger('Goga news')


def _is_developer(message: types.Message) -> bool:
    """Проверяет, является ли отправитель разработчиком"""
    if not message.from_user:
        return False
    return message.from_user.username in {user['username'] for user in config.CONFIG['users']['developers']}


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

    try:
        async with session_scope() as session:
            news = await ingest_news_from_url(
                session,
                url,
                created_by=message.from_user.username if message.from_user else None,
                source_id=message.chat.id,
            )
            news_id, title, description = news.id, news.title, news.description
    except NewsIngestError as error:
        if error.kind == 'download':
            await bot.send_message(message.chat.id, 'Не удалось загрузить или извлечь содержимое статьи.')
        else:
            await bot.send_message(
                message.chat.id,
                f'Не удалось распознать ответ. Ответ Гоги:\n\n{error.raw}',
                parse_mode=ParseMode.MARKDOWN,
            )
        return

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
