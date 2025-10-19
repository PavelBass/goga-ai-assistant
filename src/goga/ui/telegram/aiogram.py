"""Взаимодействие с Гогой через Telegramm на базе aiogram"""
import logging
import os

import rich
from aiogram import (
    Bot,
    Dispatcher,
    types,
)
from aiogram.enums import ParseMode
from aiogram.filters import (
    Command,
    CommandStart,
)
from aiogram.utils.markdown import hbold
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import (
    find_dotenv,
    load_dotenv,
)
from rich.logging import RichHandler

from goga import config
from goga.gigachat.agents import get_goga_answer
from goga.ui.telegram.tasks import say_about_daily_standup_leader
from goga.utils import get_images_directory

load_dotenv(find_dotenv())

API_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']

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
    """Пока что я совсем маленький и мало чего могу, но я быстро расту и каждый день стараюсь быть полезным.

https://github.com/PavelBass/goga-ai-assistant
"""

logger = logging.getLogger('Goga aiogram')
logger.addHandler(RichHandler())
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
    """Реакция на команды /start и /info

    Команды разрешены только в личных сообщениях и в чатах разработки
    """
    if message.chat.type != 'private':
        return
    if message.chat.id not in config.CONFIG['chats']['development']:
        return
    await send_message_with_photo(message)


@dp.message()
async def message(message: types.Message):
    """Реакция на любое сообщение"""
    if message.chat.type == 'private':
        return await handle_private_message(message)
    await handle_group_message(message)


async def handle_private_message(message: types.Message):
    """Обработка личных сообщений бота

    Общаться с ботом в личке могут только разработчики
    """
    if not message.from_user:
        return
    if message.from_user.username not in {user['username'] for user in config.CONFIG['users']['developers']}:
        # TODO: Use rich logger
        rich.print(f'Got message from unknown user {message.from_user.username}')
        rich.print(config.CONFIG)
        return
    await handle_goga_answer(message)


async def handle_group_message(message: types.Message):
    """Обработка групповых сообщений"""
    if not (message.chat.id in config.CONFIG['chats']['development']
            or message.chat.id in config.CONFIG['chats']['production']):
        logger.info(f'Got message from unknown chat {message.chat.id} - {message.chat.full_name}')
        logger.info(f'Chats config: {config.CONFIG["chats"]}')
        return
    if not message.text:
        logger.debug(f'Got message without text from chat {message.chat.full_name}')
        return
    if 'Гога' not in message.text:
        # К Гоге не обращаются
        return
    if not message.from_user:
        # Сообщение не от пользователя (бот, например)
        return
    if message.from_user.username not in {user['username'] for user in config.CONFIG['users']['customers']}:
        # Обращается к Гоге не заказчик функционала (пользователь)
        return
    await handle_goga_answer(message)


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
        await bot.send_message(message.chat.id, answer.text)
    if hasattr(answer, 'photo'):
        await bot.send_photo(message.chat.id, answer.photo)


async def run():
    """Запуск бота"""
    scheduler = AsyncIOScheduler()
    job = scheduler.add_job(
        func=say_about_daily_standup_leader,
        args=[bot],
        trigger=CronTrigger.from_crontab('0 8 * * mon-fri'),
    )
    scheduler.start()
    await dp.start_polling(bot)

