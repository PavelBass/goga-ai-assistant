from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from goga import config
from goga.ui.telegram.aiogram.bot import bot
from goga.ui.telegram.aiogram.dispatcher import dp
from goga.ui.telegram.tasks import say_about_daily_standup_leader


async def run_telegram_bot():
    """Запуск бота"""
    build_bot_messages()
    trigger = CronTrigger.from_crontab('*/1 * * * *')
    if config.CONFIG['general']['mode'] == 'production':
        trigger = CronTrigger.from_crontab('0 8 * * mon-fri')
    scheduler = AsyncIOScheduler()
    job = scheduler.add_job(
        func=say_about_daily_standup_leader,
        args=[bot],
        trigger=trigger,
    )
    scheduler.start()
    await dp.start_polling(bot)


def build_bot_messages():
    """Сборка обработчиков сообщений Telegramm"""
    #TODO: Переписать через методы регистрации обработчиков в dispatcher
    from goga.ui.telegram.aiogram.messages.commands import (
        send_welcome,
        show_dailydb,
    )
    from goga.ui.telegram.aiogram.messages.handlers import message

