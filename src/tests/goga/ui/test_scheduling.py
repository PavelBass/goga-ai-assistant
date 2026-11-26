"""Тесты планирования джобов с учётом производственного календаря

Декоратор workday_only пропускает джобу в нерабочий день и исполняет в
рабочий; workday_cron_trigger срабатывает каждый день (день недели не
ограничивается), сохраняя заданное время.
"""

import pytest

from goga.ui.telegram import scheduling


@pytest.fixture
def job(mocker):
    """Асинхронная джоба-счётчик вызовов с именем для functools.wraps"""
    fake = mocker.AsyncMock(return_value='ok')
    fake.__name__ = 'test_job'
    return fake


@pytest.mark.asyncio
async def test_workday_only_runs_on_workday(mocker, job):
    """В рабочий день джоба исполняется и возвращает результат"""
    mocker.patch.object(scheduling, 'is_today_workday', return_value=True)
    wrapped = scheduling.workday_only(job)

    result = await wrapped('arg', key='value')

    assert result == 'ok'
    job.assert_awaited_once_with('arg', key='value')


@pytest.mark.asyncio
async def test_workday_only_skips_on_day_off(mocker, job):
    """В нерабочий день джоба не вызывается и возвращает None"""
    mocker.patch.object(scheduling, 'is_today_workday', return_value=False)
    wrapped = scheduling.workday_only(job)

    result = await wrapped()

    assert result is None
    job.assert_not_awaited()


@pytest.mark.asyncio
async def test_workday_only_preserves_name(mocker, job):
    """Декоратор сохраняет имя функции (functools.wraps)"""
    mocker.patch.object(scheduling, 'is_today_workday', return_value=True)
    wrapped = scheduling.workday_only(job)
    assert wrapped.__name__ == 'test_job'


def test_workday_cron_trigger_everyday():
    """День недели из mon-fri заменяется на '*', время сохраняется"""
    trigger = scheduling.workday_cron_trigger('0 8 * * mon-fri')
    fields = {field.name: str(field) for field in trigger.fields}
    assert fields['day_of_week'] == '*'
    assert fields['hour'] == '8'
    assert fields['minute'] == '0'


def test_workday_cron_trigger_keeps_time():
    """Произвольное время сохраняется, день недели всегда '*'"""
    trigger = scheduling.workday_cron_trigger('30 9 * * 1-5', timezone='Europe/Moscow')
    fields = {field.name: str(field) for field in trigger.fields}
    assert fields['day_of_week'] == '*'
    assert fields['hour'] == '9'
    assert fields['minute'] == '30'
