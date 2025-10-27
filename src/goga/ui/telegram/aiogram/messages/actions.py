"""Общие действия на сообщениях"""
from aiogram import types
from aiogram.enums import ParseMode

from goga.ui.telegram.aiogram.bot import bot
from goga.ui.telegram.answers import PRIVATE_ANSWER
from goga.utils import get_images_directory


async def send_message_with_photo(message: types.Message):
    """Отправляет приветствие с фото"""
    file_path = get_images_directory() / 'goga-kid.jpg'
    file = types.FSInputFile(path=file_path)
    await bot.send_photo(
        message.chat.id,
        file,
        reply_to_message_id=message.message_id
    )
    greeting = f'Привет, **{message.from_user.full_name}**!\n'
    await bot.send_message(message.chat.id, greeting + PRIVATE_ANSWER, parse_mode=ParseMode.MARKDOWN)


