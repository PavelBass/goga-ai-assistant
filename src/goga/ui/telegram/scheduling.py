"""Планирование джобов с учётом производственного календаря РФ

Джоба запускается ежедневным cron в одно и то же время, а декоратор
workday_only пропускает её в нерабочие дни по производственному календарю
(праздники и перенесённые выходные) и исполняет в рабочие субботы. День
недели в cron намеренно не ограничивается: решение принимает календарь, а не
правило mon-fri.
"""

import functools
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from apscheduler.triggers.cron import CronTrigger

from goga.data.production_calendar import is_today_workday

logger = logging.getLogger('Goga scheduling')


def workday_only(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    """Декоратор: выполняет асинхронную джобу только в рабочий день в России

    При вызове проверяет is_today_workday() по производственному календарю
    (при отсутствии календаря на год — по дню недели) и пропускает джобу в
    нерабочий день. Рассчитан на джобу планировщика, запускаемую ежедневным
    cron в одно время (см. workday_cron_trigger).

    Args:
        func: асинхронная функция-джоба

    Returns:
        обёрнутая асинхронная функция, пропускающая нерабочие дни
    """

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        """Пропускает джобу в нерабочий день, иначе исполняет её"""
        if not is_today_workday():
            logger.info('Нерабочий день — джоба %s пропущена', func.__name__)
            return None
        return await func(*args, **kwargs)

    return wrapper


def workday_cron_trigger(cron: str, timezone: str = 'Europe/Moscow') -> CronTrigger:
    """Cron-триггер, срабатывающий каждый день в заданное время

    День недели из cron-выражения заменяется на '*': рабочие и выходные дни
    определяет производственный календарь (включая рабочие субботы и
    праздники), а не правило mon-fri. Минуты, часы, день и месяц сохраняются.

    Args:
        cron: cron-выражение из пяти полей (минута час день месяц день_недели)
        timezone: таймзона расписания

    Returns:
        ежедневный cron-триггер без ограничения дня недели

    Raises:
        ValueError: если cron-выражение некорректно
    """
    minute, hour, day, month, _ = cron.split()
    return CronTrigger.from_crontab(f'{minute} {hour} {day} {month} *', timezone=timezone)
