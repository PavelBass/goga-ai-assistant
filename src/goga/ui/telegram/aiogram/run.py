import asyncio
import logging

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from goga import config
from goga.api.app import app as api_app
from goga.ui.telegram.aiogram.bot import bot
from goga.ui.telegram.aiogram.dispatcher import dp
from goga.ui.telegram.tasks import say_about_daily_standup_leader

logger = logging.getLogger('Goga run')

# Расписание ежедневной задачи в режиме разработки — каждую минуту
_DEV_DAILY_CRON = '*/1 * * * *'


def _build_daily_trigger() -> CronTrigger:
    """Строит триггер ежедневного объявления ведущего

    В продакшене расписание и таймзона берутся из config['schedule']
    (например, '0 8 * * mon-fri' в зоне 'Europe/Moscow'). В остальных режимах
    задача запускается каждую минуту для удобства отладки.
    """
    if config.CONFIG['general']['mode'] != 'production':
        return CronTrigger.from_crontab(_DEV_DAILY_CRON)
    schedule = config.CONFIG.get('schedule', {})
    return CronTrigger.from_crontab(
        schedule.get('daily_cron', '0 8 * * mon-fri'),
        timezone=schedule.get('timezone', 'Europe/Moscow'),
    )


def _register_history_middlewares() -> None:
    """Подключает сохранение истории чата, если оно не отключено в конфиге

    Входящие/правки ловятся outer-middleware на dp.message/dp.edited_message,
    исходящие — request-middleware на bot.session.

    По умолчанию включено: config.toml у каждого окружения свой (в .gitignore),
    поэтому не полагаемся на наличие секции. Отключить — chat_history.enabled = false.
    """
    if not config.CONFIG.get('chat_history', {}).get('enabled', True):
        logger.info('Сохранение истории чата отключено')
        return
    from goga.ui.telegram.aiogram.middlewares.history import (
        HistoryCaptureMiddleware,
        HistoryRequestMiddleware,
    )

    capture = HistoryCaptureMiddleware()
    dp.message.outer_middleware(capture)
    dp.edited_message.outer_middleware(capture)
    bot.session.middleware(HistoryRequestMiddleware())
    logger.info('Сохранение истории чата включено')


def _build_api_server() -> uvicorn.Server:
    """Строит сервер uvicorn для встраивания в общий event loop

    Обработчики сигналов отключаются: SIGTERM/SIGINT держит aiogram, а его
    завершение инициирует остановку API в run_telegram_bot.
    """
    api = config.CONFIG.get('api', {})
    server = uvicorn.Server(
        uvicorn.Config(
            api_app,
            host=api.get('host', '127.0.0.1'),
            port=api.get('port', 8080),
            log_level='info',
            loop='none',
        )
    )
    server.install_signal_handlers = lambda: None
    return server


async def run_telegram_bot():
    """Запуск бота, планировщика и (опционально) HTTP API в одном event loop

    Поллинг aiogram и сервер uvicorn работают параллельно. Завершение любого из
    них (например, по SIGTERM, который обрабатывает aiogram) корректно
    останавливает второй.
    """
    build_bot_messages()
    _register_history_middlewares()
    scheduler = AsyncIOScheduler()
    scheduler.add_job(func=say_about_daily_standup_leader, args=[bot], trigger=_build_daily_trigger())
    scheduler.start()

    tasks = [asyncio.create_task(dp.start_polling(bot), name='aiogram-polling')]
    server = None
    if config.CONFIG.get('api', {}).get('enabled', False):
        server = _build_api_server()
        tasks.append(asyncio.create_task(server.serve(), name='uvicorn-serve'))
        logger.info('HTTP API включён: %s:%s', server.config.host, server.config.port)

    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    logger.info('Останавливаюсь: завершены %s', [task.get_name() for task in done])
    if server is not None:
        server.should_exit = True
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)


def build_bot_messages():
    """Сборка обработчиков сообщений Telegramm"""
    # TODO: Переписать через методы регистрации обработчиков в dispatcher
    from goga.ui.telegram.aiogram.messages.commands import (
        send_welcome,
        show_dailydb,
    )
    from goga.ui.telegram.aiogram.messages.handlers import message
    from goga.ui.telegram.aiogram.messages.news import (
        add_news,
        delete_news,
        list_news,
    )
