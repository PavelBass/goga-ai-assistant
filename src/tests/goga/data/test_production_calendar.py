"""Тесты производственного календаря РФ

Проверяются парсинг формата xmlcalendar.ru (включая рабочие субботы и
перенесённые выходные), хранение в репозитории, fallback на день недели при
отсутствии календаря и механизм обновления из открытых данных. Фикстуры —
реальные данные xmlcalendar.ru за 2024 и 2026 годы.
"""

import datetime as dt
import json

import pytest

from goga.data import production_calendar as pc

SOURCE_2024 = {
    'year': 2024,
    'months': [
        {'month': 1, 'days': '1,2,3,4,5,6,7,8,13,14,20,21,27,28'},
        {'month': 2, 'days': '3,4,10,11,17,18,22*,23,24,25'},
        {'month': 3, 'days': '2,3,7*,8,9,10,16,17,23,24,30,31'},
        {'month': 4, 'days': '6,7,13,14,20,21,28,29+,30+'},
        {'month': 5, 'days': '1,4,5,8*,9,10+,11,12,18,19,25,26'},
        {'month': 6, 'days': '1,2,8,9,11*,12,15,16,22,23,29,30'},
        {'month': 7, 'days': '6,7,13,14,20,21,27,28'},
        {'month': 8, 'days': '3,4,10,11,17,18,24,25,31'},
        {'month': 9, 'days': '1,7,8,14,15,21,22,28,29'},
        {'month': 10, 'days': '5,6,12,13,19,20,26,27'},
        {'month': 11, 'days': '2*,3,4,9,10,16,17,23,24,30'},
        {'month': 12, 'days': '1,7,8,14,15,21,22,29,30+,31+'},
    ],
    'transitions': [
        {'from': '04.27', 'to': '04.29'},
        {'from': '11.02', 'to': '04.30'},
        {'from': '01.06', 'to': '05.10'},
        {'from': '12.28', 'to': '12.30'},
        {'from': '01.07', 'to': '12.31'},
    ],
}

SOURCE_2026 = {
    'year': 2026,
    'months': [
        {'month': 1, 'days': '1,2,3,4,5,6,7,8,9+,10,11,17,18,24,25,31'},
        {'month': 2, 'days': '1,7,8,14,15,21,22,23,28'},
        {'month': 3, 'days': '1,7,8,9+,14,15,21,22,28,29'},
        {'month': 4, 'days': '4,5,11,12,18,19,25,26,30*'},
        {'month': 5, 'days': '1,2,3,8*,9,10,11+,16,17,23,24,30,31'},
        {'month': 6, 'days': '6,7,11*,12,13,14,20,21,27,28'},
        {'month': 7, 'days': '4,5,11,12,18,19,25,26'},
        {'month': 8, 'days': '1,2,8,9,15,16,22,23,29,30'},
        {'month': 9, 'days': '5,6,12,13,19,20,26,27'},
        {'month': 10, 'days': '3,4,10,11,17,18,24,25,31'},
        {'month': 11, 'days': '1,3*,4,7,8,14,15,21,22,28,29'},
        {'month': 12, 'days': '5,6,12,13,19,20,26,27,31+'},
    ],
    'transitions': [
        {'from': '01.03', 'to': '01.09'},
        {'from': '03.08', 'to': '03.09'},
        {'from': '05.09', 'to': '05.11'},
        {'from': '01.04', 'to': '12.31'},
    ],
}


@pytest.fixture
def calendar_2024():
    """Календарь 2024 года, разобранный из реальных данных источника"""
    return pc.parse_production_calendar(SOURCE_2024)


def test_new_year_holidays(calendar_2024):
    """Новогодние праздники нерабочие, первый рабочий день после них — рабочий"""
    assert not calendar_2024.is_workday(dt.date(2024, 1, 1))
    assert not calendar_2024.is_workday(dt.date(2024, 1, 8))
    assert calendar_2024.is_workday(dt.date(2024, 1, 9))


def test_working_saturday_from_transfer(calendar_2024):
    """27.04.2024 — рабочая суббота (перенос на 29.04), 29 и 30 — выходные"""
    assert calendar_2024.is_workday(dt.date(2024, 4, 27))
    assert not calendar_2024.is_workday(dt.date(2024, 4, 28))
    assert not calendar_2024.is_workday(dt.date(2024, 4, 29))
    assert not calendar_2024.is_workday(dt.date(2024, 4, 30))


def test_shortened_working_saturday(calendar_2024):
    """02.11.2024 — рабочая сокращённая суббота, 04.11 — праздник"""
    assert calendar_2024.is_workday(dt.date(2024, 11, 2))
    assert not calendar_2024.is_workday(dt.date(2024, 11, 4))


def test_december_working_saturday(calendar_2024):
    """28.12.2024 — рабочая суббота (перенос на 30.12), 30 и 31 — выходные"""
    assert calendar_2024.is_workday(dt.date(2024, 12, 28))
    assert not calendar_2024.is_workday(dt.date(2024, 12, 30))
    assert not calendar_2024.is_workday(dt.date(2024, 12, 31))


def test_regular_weekend_and_workday(calendar_2024):
    """Обычная суббота нерабочая, обычный понедельник рабочий"""
    assert not calendar_2024.is_workday(dt.date(2024, 7, 6))
    assert calendar_2024.is_workday(dt.date(2024, 7, 8))


def test_year_mismatch_raises(calendar_2024):
    """Дата другого года отклоняется"""
    with pytest.raises(ValueError):
        calendar_2024.is_workday(dt.date(2025, 1, 1))


def test_2026_transferred_days_off_and_no_working_weekends():
    """В 2026 перенесённые выходные нерабочие, рабочих суббот нет"""
    calendar = pc.parse_production_calendar(SOURCE_2026)
    assert not calendar.is_workday(dt.date(2026, 1, 9))
    assert not calendar.is_workday(dt.date(2026, 12, 31))
    assert not calendar.is_workday(dt.date(2026, 1, 3))
    assert not calendar.is_workday(dt.date(2026, 5, 9))
    assert calendar.is_workday(dt.date(2026, 1, 12))


def test_repository_round_trip(tmp_path):
    """Сохранённый календарь загружается без потерь"""
    repo = pc.ProductionCalendarRepository(tmp_path)
    calendar = pc.parse_production_calendar(SOURCE_2024)
    repo.save(calendar)

    loaded = repo.load(2024)
    assert loaded is not None
    assert loaded.year == 2024
    assert loaded.days_off == calendar.days_off
    assert (tmp_path / '2024.json').is_file()


def test_repository_load_missing(tmp_path):
    """Отсутствующий календарь возвращается как None"""
    repo = pc.ProductionCalendarRepository(tmp_path)
    assert repo.load(2024) is None


def test_is_workday_fallback_without_calendar(tmp_path):
    """Без календаря рабочий день определяется по дню недели"""
    repo = pc.ProductionCalendarRepository(tmp_path)
    assert pc.is_workday(dt.date(2024, 4, 29), repo)
    assert not pc.is_workday(dt.date(2024, 4, 27), repo)


def test_is_workday_uses_calendar(tmp_path):
    """С календарём рабочая суббота и перенесённый выходной учитываются"""
    repo = pc.ProductionCalendarRepository(tmp_path)
    repo.save(pc.parse_production_calendar(SOURCE_2024))
    assert pc.is_workday(dt.date(2024, 4, 27), repo)
    assert not pc.is_workday(dt.date(2024, 4, 29), repo)


def test_is_today_workday_delegates(tmp_path):
    """is_today_workday эквивалентна is_workday для сегодняшней даты"""
    repo = pc.ProductionCalendarRepository(tmp_path)
    assert pc.is_today_workday(repo) == pc.is_workday(dt.date.today(), repo)


def test_update_production_calendar_saves(mocker, tmp_path):
    """Команда update скачивает (мок), парсит и сохраняет календарь в репозиторий"""
    repo = pc.ProductionCalendarRepository(tmp_path)
    mocker.patch.object(pc, 'fetch_production_calendar', return_value=SOURCE_2024)

    calendar = pc.update_production_calendar(2024, repo)

    assert calendar.year == 2024
    loaded = repo.load(2024)
    assert loaded is not None
    assert loaded.days_off == calendar.days_off


def test_fetch_production_calendar_parses_json(mocker):
    """Функция fetch обращается к URL года и разбирает JSON-ответ"""
    payload = json.dumps(SOURCE_2024).encode('utf-8')
    urlopen = mocker.patch.object(pc.urllib.request, 'urlopen')
    urlopen.return_value.__enter__.return_value.read.return_value = payload

    data = pc.fetch_production_calendar(2024)

    assert data == SOURCE_2024
    assert urlopen.call_args.args[0] == pc.CALENDAR_URL_TEMPLATE.format(year=2024)


@pytest.mark.asyncio
async def test_refresh_production_calendar_ok(mocker):
    """Задача планировщика обновляет календарь на текущий год"""
    from goga.ui.telegram import tasks

    calendar = pc.parse_production_calendar(SOURCE_2024)
    update = mocker.patch.object(tasks, 'update_production_calendar', return_value=calendar)

    await tasks.refresh_production_calendar()

    update.assert_called_once_with(dt.date.today().year)


@pytest.mark.asyncio
async def test_refresh_production_calendar_swallows_errors(mocker):
    """Ошибка сети не роняет задачу планировщика"""
    from goga.ui.telegram import tasks

    mocker.patch.object(tasks, 'update_production_calendar', side_effect=OSError('network down'))

    await tasks.refresh_production_calendar()
