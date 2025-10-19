"""Периодические задачи"""
from aiogram import Bot
from aiogram.enums import ParseMode

from goga import config
from goga.gigachat.agents import get_goga_answer
from goga.gigachat.tools import get_or_create_repository


async def say_about_daily_standup_leader(bot: Bot):
    """Сказать кто сегодня ведущий Daily Standup"""
    repository = get_or_create_repository()
    leader = repository.today_random_participant
    prompt = 'Гога, необходимо в 8 часов утра, за два часа до Daily Standup, который начинается в 10:00, '
    prompt += 'рассказывать команде о том кто ведущий сегодняшнего Daily Standup в командном чате. '
    prompt += 'Представь, что сейчас утро, 8:00, и твоя очередь сказать команде, '
    prompt += f'что **{leader}** сегодня ведёт Daily Standup. '
    prompt += 'Будь вежливым, позитивным и вдохновляющим. Начни с пожелания коллегам доброго дня. Не забудь в конце '
    prompt += 'рассказать интересный факт о любой технологии связанной с '
    prompt += 'искусственным интеллектом.'
    prompt += 'Имя ведущего необходимо выделить жирным шрифтом в markdown.'
    answer = await get_goga_answer(config.CONFIG['chats']['production'][0], prompt)
    for chat_id in config.CONFIG['chats']['development']:
        await bot.send_message(chat_id, answer, parse_mode=ParseMode.MARKDOWN)

