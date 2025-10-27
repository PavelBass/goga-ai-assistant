"""Обработка сообщений с помощью Гоги"""
import logging

from aiogram import types
from aiogram.enums import ParseMode

from goga.gigachat.agents import get_goga_answer
from goga.ui.telegram.aiogram.bot import bot
from goga.utils import get_images_directory

logger = logging.getLogger('Goga aiogram')

async def handle_goga_answer(message: types.Message):
    """Получить и отправить ответ от Гоги"""
    logger.info(f'Got message from user {message.from_user}: {message.text}')
    answer = await get_goga_answer(message.chat.id, message.text)
    if isinstance(answer, str):
        if 'Позвольте поприветствовать вас словами в виде тоста!' in answer:
            file_path = get_images_directory() / 'goga-toast.jpg'
            file = types.FSInputFile(path=file_path)
            await bot.send_photo(
                message.chat.id,
                file,
            )
        await bot.send_message(message.chat.id, answer, parse_mode=ParseMode.MARKDOWN)
    if hasattr(answer, 'text'):
        await bot.send_message(message.chat.id, answer.text, parse_mode=ParseMode.MARKDOWN)
    if hasattr(answer, 'photo'):
        await bot.send_photo(message.chat.id, answer.photo)

