"""Обработка команд Telegramm"""
import json
from pathlib import Path

from aiogram import types
from aiogram.enums import ParseMode
from aiogram.filters import Command

from goga import config
from goga.ui.telegram.aiogram.bot import bot
from goga.ui.telegram.aiogram.dispatcher import dp
from goga.ui.telegram.aiogram.messages.actions import send_message_with_photo


@dp.message(Command(commands=['start', 'info']))
async def send_welcome(message: types.Message):
    """Реакция на команды /start и /info

    Команды разрешены только в личных сообщениях и в чатах разработки
    """
    if not (
        message.chat.id in config.CONFIG['chats']['development']
        or message.chat.id in config.CONFIG['users']['developers']
    ):
        return
    await send_message_with_photo(message)


@dp.message(Command('dailydb'))
async def show_dailydb(message: types.Message):
    """Реакция на команду /dailydb

    Команды разрешены только в личных сообщениях и в чатах разработки
    """
    if not (
        message.chat.id in config.CONFIG['chats']['development']
        or message.chat.id in config.CONFIG['users']['developers']
    ):
        return
    dailydb_file = config.CONFIG['db']['daily']
    dailydb_path = Path(dailydb_file)
    data = json.loads(dailydb_path.read_text())
    content = '```python\n' + json.dumps(data, indent=2, ensure_ascii=False) + '\n```'
    await bot.send_message(message.chat.id, content, parse_mode=ParseMode.MARKDOWN)

