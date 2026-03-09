"""Команды управления новостями (для администраторов)"""
import logging
import re

import trafilatura
from aiogram import types
from aiogram.enums import ParseMode
from aiogram.filters import Command

from goga import config
from goga.gigachat.agents import get_goga_answer
from goga.gigachat.tools import get_or_create_news_repository
from goga.ui.telegram.aiogram.bot import bot
from goga.ui.telegram.aiogram.dispatcher import dp

logger = logging.getLogger('Goga news')

ADD_NEWS_PROMPT = (
    'Тебе даны извлечённые данные статьи. Сформируй файл новости в формате markdown на русском языке. '
    'Файл должен содержать: заголовок статьи (# Заголовок), краткий анонс статьи (2-3 предложения о сути не более 30-35 слов), '
    'и ссылку на оригинал в формате [Читать оригинал](ссылка). '
    'Также верни имя файла в формате ГГГГММДД Краткое название.md, '
    'где ГГГГММДД — дата публикации оригинальной статьи (если дата неизвестна, используй сегодняшнюю). '
    'Ответ верни на русском языке строго в следующем формате без дополнительных комментариев:\n'
    'FILENAME: имя файла\n'
    'CONTENT:\n'
    'содержимое файла'
)


def _is_developer(message: types.Message) -> bool:
    """Проверяет, является ли отправитель разработчиком"""
    if not message.from_user:
        return False
    return message.from_user.username in {user['username'] for user in config.CONFIG['users']['developers']}


def _extract_article(url: str) -> dict | None:
    """Извлекает заголовок, текст и дату статьи по ссылке"""
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


@dp.message(Command('news_add'))
async def add_news(message: types.Message):
    """Добавление новости: /news_add <ссылка на статью>"""
    print('PEWPEPEWPEWPE', flush=True)
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
    print(prompt)

    answer = await get_goga_answer(message.chat.id, prompt)

    filename_match = re.search(r'FILENAME:\s*(.+\.md)', answer)
    content_match = re.search(r'CONTENT:\s*\n([\s\S]+)', answer)

    if not filename_match or not content_match:
        await bot.send_message(
            message.chat.id,
            f'Не удалось распознать ответ. Ответ Гоги:\n\n{answer}',
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    filename = filename_match.group(1).strip()
    content = content_match.group(1).strip()

    news_repo = get_or_create_news_repository()
    file_path = news_repo.add_news(filename, content)

    await bot.send_message(
        message.chat.id,
        f'Новость добавлена: `{filename}`\n\n{content}',
        parse_mode=ParseMode.MARKDOWN,
    )
    logger.info(f'Новость добавлена: {file_path}')


@dp.message(Command('news_list'))
async def list_news(message: types.Message):
    """Список новостей: /news_list"""
    if not _is_developer(message):
        return

    news_repo = get_or_create_news_repository()
    items = news_repo.get_news_list()

    if not items:
        await bot.send_message(message.chat.id, 'Нет непоказанных новостей.')
        return

    lines = []
    current_day = 0
    limit = config.CONFIG['news']['limit']
    for index, filename, content in items:
        day_number = (index - 1) // limit + 1
        if day_number != current_day:
            current_day = day_number
            lines.append(f'\n*День показа {day_number}:*')
        first_line = content.split('\n', maxsplit=1)[0].lstrip('# ').strip()
        lines.append(f'  {index}. {first_line} (`{filename}`)')

    text = 'Список новостей:\n' + '\n'.join(lines)
    await bot.send_message(message.chat.id, text, parse_mode=ParseMode.MARKDOWN)


@dp.message(Command('news_delete'))
async def delete_news(message: types.Message):
    """Удаление новости: /news_delete <номер>"""
    if not _is_developer(message):
        return
    if not message.text:
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().isdigit():
        await bot.send_message(message.chat.id, 'Использование: /news\\_delete <номер из /news\\_list>')
        return

    index = int(parts[1].strip())
    news_repo = get_or_create_news_repository()
    deleted = news_repo.delete_news(index)

    if deleted:
        await bot.send_message(message.chat.id, f'Новость удалена: `{deleted}`', parse_mode=ParseMode.MARKDOWN)
        logger.info(f'Новость удалена: {deleted}')
    else:
        await bot.send_message(message.chat.id, f'Новость с номером {index} не найдена.')
