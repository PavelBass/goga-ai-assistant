"""Обработка сообщений Telegramm"""
import logging

import rich
from aiogram import types

from goga import config
from goga.ui.telegram.aiogram.dispatcher import dp
from goga.ui.telegram.aiogram.messages.goga import handle_goga_answer

logger = logging.getLogger('Goga aiogram')

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
    if config.CONFIG['general']['mode'] != 'production':
        if message.chat.id not in config.CONFIG['chats']['development']:
            logger.debug(f'Got message from chat {message.chat.full_name} in development mode. Skip message.')
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

