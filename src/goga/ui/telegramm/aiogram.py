"""Взаимодействие с Гогой через Telegramm на базе aiogram"""
import logging
import os

from aiogram import (
    Bot,
    Dispatcher,
    types,
)
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.utils.markdown import hbold
from dotenv import (
    find_dotenv,
    load_dotenv,
)

from goga.utils import get_images_directory

load_dotenv(find_dotenv())

API_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
DEVELOPMENT_CHAT_ID = -4831473627

PRIVATE_ANSWER= """Я - Гога, сын Giga, в том смысле, что я создан на базе LLM моделей GigaChat. """ \
    """Моя основная задача помогать команде разработки RAG-слоя в решении различных вопросов, """ \
    """связанных с разработкой. Я построен, как мульти-агентная система на базе """ \
    """искусственного интеллекта, и я горжусь своими "предками".

На сегодняшний день, в личных сообщениях я отвечаю только этим приветствием. """ \
    """Чтобы получить от меня обдуманный ответ, необходимо явно ко мне обратиться по имени в чате разработки RAG-слоя. """ \
    f"""Например так
> {hbold('Гога, что такое RAG-слой?')}
или так
> {hbold('Добавь пользователя Василия, Гога, в список участников дейли')}

Мой создатель - Павел Басс (@Kademn), один из программистов команды разработки RAG-слоя. Он создал меня и непрерывно улучшает """ \
    """не только с целью дать команде удобного в использовании и полезного AI-ассистента, но также для того, """ \
    """чтобы на практике опробовать различные приёмы и подходы в разработке мульти-агентных систем """ \
    """на базе искусственного интеллекта.

Я дружелюбен и эмпатичен, а также люблю делиться интересными фактами по обсуждаемой теме. """ \
    """Пока что я совсем маленький и мало чего могу, но я быстро расту и каждый день стараюсь быть полезным."""

logger = logging.getLogger('Goga')
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

async def send_message_with_photo(message: types.Message):
    """Отправляет приветствие с фото"""
    file_path = get_images_directory() / 'goga-kid.jpg'
    file = types.FSInputFile(path=file_path)
    await bot.send_photo(
        message.chat.id,
        file,
        reply_to_message_id=message.message_id
    )
    greeting = f'Привет, {hbold(message.from_user.full_name)}!\n'
    await bot.send_message(message.chat.id, greeting + PRIVATE_ANSWER, parse_mode=ParseMode.HTML)


@dp.message(Command(commands=['start', 'info']))
async def send_welcome(message: types.Message):
    """Реакция на команды /start и /info"""
    if message.chat.type != 'private':
        return
    await send_message_with_photo(message)


@dp.message()
async def message(message: types.Message):
    """Реакция на любое сообщение"""
    if message.chat.type == 'private':
        return
    await handle_group_message(message)
     

async def handle_group_message(message: types.Message):
    """Обработка групповых сообщений"""
    if message.chat.id != DEVELOPMENT_CHAT_ID:
        logger.info(f'Got message from unknown chat {message.chat.id}')
        return
    if not message.text:
        return
    if 'Гога' not in message.text:
        return
    answer = get_goga_answer(message.text)
    if isinstance(answer, str):
        await bot.send_message(message.chat.id, answer)
    if hasattr(answer, 'text'):
        await bot.send_message(message.chat.id, answer.text)
    if hasattr(answer, 'photo'):
        await bot.send_photo(message.chat.id, answer.photo)


async def handle_private_message(message: types.Message):
    """Обработка приватных сообщений"""
    await send_welcome(message)


async def main():
    """Запуск бота"""
    await dp.start_polling(bot)

