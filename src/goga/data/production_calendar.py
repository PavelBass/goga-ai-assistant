"""Производственный календарь РФ: определение рабочих дней и загрузка из открытых данных

Рабочие дни в России определяются производственным календарём, который
утверждается на предыдущий год. Модуль хранит календарь как полный набор
нерабочих дней года (выходные, праздники и перенесённые выходные) и считает
день рабочим, если его нет в этом наборе. Если календаря на нужный год нет,
рабочий/нерабочий день определяется по дню недели (суббота и воскресенье —
выходные).

Источник открытых данных — xmlcalendar.ru
(https://xmlcalendar.ru/data/ru/{год}/calendar.json). Формат источника: в
``months[].days`` перечислены нерабочие дни (без маркера и с ``+`` —
перенесённые выходные) и сокращённые рабочие дни (``*``). Рабочие выходные без
сокращения (например, суббота 27.04.2024) в список не попадают и
восстанавливаются из ``transitions``.
"""

import datetime as dt
import json
import urllib.request
from collections.abc import Iterable
from pathlib import Path

from goga.utils import get_data_directory

CALENDAR_URL_TEMPLATE = 'https://xmlcalendar.ru/data/ru/{year}/calendar.json'
FETCH_TIMEOUT_SECONDS = 30


class ProductionCalendar:
    """Производственный календарь на один год

    Attributes:
        year: год календаря
        days_off: полный набор нерабочих дней года (выходные, праздники и
            перенесённые выходные)
    """

    def __init__(self, year: int, days_off: Iterable[dt.date]) -> None:
        """Инициализация календаря

        Args:
            year: год календаря
            days_off: нерабочие дни года
        """
        self.year = year
        self.days_off = frozenset(days_off)

    def is_workday(self, day: dt.date) -> bool:
        """Является ли день рабочим по календарю

        Args:
            day: проверяемая дата того же года, что и календарь

        Returns:
            True, если день рабочий

        Raises:
            ValueError: если дата относится к другому году
        """
        if day.year != self.year:
            raise ValueError(f'Дата {day} не относится к году календаря {self.year}')
        return day not in self.days_off

    def as_dict(self) -> dict:
        """Преобразование в словарь для JSON-сериализации"""
        return {
            'year': self.year,
            'days_off': [day.isoformat() for day in sorted(self.days_off)],
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'ProductionCalendar':
        """Инициализация из словаря

        Args:
            data: словарь с ключами year и days_off (список ISO-дат)

        Returns:
            производственный календарь

        Raises:
            ValueError: если дата в days_off некорректна
        """
        return cls(
            year=data['year'],
            days_off=[dt.date.fromisoformat(value) for value in data['days_off']],
        )

    def as_json(self) -> str:
        """Преобразование в JSON"""
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2)


def _parse_source_day(year: int, month: int, token: str) -> tuple[dt.date, bool]:
    """Разбирает один элемент списка days источника

    Args:
        year: год календаря
        month: номер месяца
        token: элемент списка days, например '9', '9+' или '30*'

    Returns:
        кортеж (дата, признак сокращённого рабочего дня)

    Raises:
        ValueError: если токен не содержит корректный номер дня
    """
    shortened = token.endswith('*')
    day = int(token.rstrip('*+'))
    return dt.date(year, month, day), shortened


def _listed_days_off(year: int, months: list[dict]) -> set[dt.date]:
    """Нерабочие дни, явно перечисленные в источнике (без маркера и с '+')

    Args:
        year: год календаря
        months: список месяцев источника с полями month и days

    Returns:
        набор нерабочих дат (сокращённые рабочие дни '*' исключаются)

    Raises:
        ValueError: если номер дня в списке days некорректен
    """
    days_off: set[dt.date] = set()
    for month in months:
        for token in month['days'].split(','):
            token = token.strip()
            if not token:
                continue
            day, shortened = _parse_source_day(year, month['month'], token)
            if not shortened:
                days_off.add(day)
    return days_off


def _parse_transition_date(year: int, value: str) -> dt.date:
    """Разбирает дату переноса источника в формате ММ.ДД

    Args:
        year: год календаря
        value: дата вида '04.27' (месяц.день)

    Returns:
        дата переноса

    Raises:
        ValueError: если дата некорректна
    """
    month, day = (int(part) for part in value.split('.'))
    return dt.date(year, month, day)


def _working_weekends(year: int, transitions: list[dict], listed_off: set[dt.date]) -> set[dt.date]:
    """Рабочие выходные, полученные переносом выходного дня

    Перенос ``from`` делает исходный выходной рабочим. Если исходная дата —
    праздник (явно перечислена как нерабочая), она остаётся нерабочей.

    Args:
        year: год календаря
        transitions: список переносов источника с полями from и to
        listed_off: явно перечисленные нерабочие дни

    Returns:
        набор суббот/воскресений, ставших рабочими

    Raises:
        ValueError: если дата переноса некорректна
    """
    working: set[dt.date] = set()
    for transition in transitions:
        day = _parse_transition_date(year, transition['from'])
        if day.weekday() >= 5 and day not in listed_off:
            working.add(day)
    return working


def _weekend_days(year: int) -> set[dt.date]:
    """Все субботы и воскресенья года

    Args:
        year: год календаря

    Returns:
        набор выходных дат
    """
    days: set[dt.date] = set()
    day = dt.date(year, 1, 1)
    while day.year == year:
        if day.weekday() >= 5:
            days.add(day)
        day += dt.timedelta(days=1)
    return days


def parse_production_calendar(data: dict) -> ProductionCalendar:
    """Преобразует календарь источника xmlcalendar.ru в формат модуля

    Нерабочие дни — это все выходные года плюс явно перечисленные праздники и
    перенесённые выходные, минус рабочие выходные, полученные переносом.

    Args:
        data: словарь календаря источника (year, months, transitions)

    Returns:
        производственный календарь с полным набором нерабочих дней

    Raises:
        ValueError: если данные источника содержат некорректные даты
    """
    year = data['year']
    listed_off = _listed_days_off(year, data['months'])
    working_weekends = _working_weekends(year, data.get('transitions', []), listed_off)
    days_off = (_weekend_days(year) | listed_off) - working_weekends
    return ProductionCalendar(year=year, days_off=days_off)


class ProductionCalendarRepository:
    """Репозиторий производственных календарей (по JSON-файлу на год)

    Attributes:
        directory: каталог с файлами календарей {год}.json
    """

    def __init__(self, directory: Path | str | None = None) -> None:
        """Инициализация репозитория

        Args:
            directory: каталог с файлами календарей; по умолчанию
                data/production_calendar проекта
        """
        self.directory = Path(directory) if directory is not None else get_data_directory() / 'production_calendar'

    def _path(self, year: int) -> Path:
        """Путь к файлу календаря года

        Args:
            year: год календаря

        Returns:
            путь к JSON-файлу календаря
        """
        return self.directory / f'{year}.json'

    def load(self, year: int) -> ProductionCalendar | None:
        """Загружает календарь года

        Args:
            year: год календаря

        Returns:
            календарь года или None, если файл отсутствует

        Raises:
            json.JSONDecodeError: если файл повреждён
            OSError: при ошибке чтения файла
        """
        path = self._path(year)
        if not path.is_file():
            return None
        return ProductionCalendar.from_dict(json.loads(path.read_text()))

    def save(self, calendar: ProductionCalendar) -> None:
        """Сохраняет календарь в файл {год}.json

        Args:
            calendar: сохраняемый календарь

        Raises:
            OSError: при ошибке создания каталога или записи файла
        """
        self.directory.mkdir(parents=True, exist_ok=True)
        self._path(calendar.year).write_text(calendar.as_json())


def fetch_production_calendar(year: int) -> dict:
    """Скачивает календарь года из открытых данных xmlcalendar.ru

    Args:
        year: год календаря

    Returns:
        словарь календаря источника (year, months, transitions)

    Raises:
        urllib.error.URLError: при ошибке сети (включая HTTP-ошибки)
        TimeoutError: при превышении таймаута запроса
        json.JSONDecodeError: если ответ не является корректным JSON
    """
    url = CALENDAR_URL_TEMPLATE.format(year=year)
    # Схема ссылки фиксирована (https), год — целое число; пользовательский
    # ввод в URL не попадает, поэтому urlopen безопасен.
    with urllib.request.urlopen(url, timeout=FETCH_TIMEOUT_SECONDS) as response:  # noqa: S310
        return json.loads(response.read().decode('utf-8'))


def update_production_calendar(
    year: int,
    repository: ProductionCalendarRepository | None = None,
) -> ProductionCalendar:
    """Скачивает календарь года из открытых данных и сохраняет в репозиторий

    Args:
        year: год календаря
        repository: репозиторий календарей; по умолчанию data/production_calendar

    Returns:
        сохранённый производственный календарь

    Raises:
        urllib.error.URLError: при ошибке сети
        TimeoutError: при превышении таймаута запроса
        json.JSONDecodeError: если ответ источника некорректен
        OSError: при ошибке записи файла
    """
    repository = repository if repository is not None else ProductionCalendarRepository()
    calendar = parse_production_calendar(fetch_production_calendar(year))
    repository.save(calendar)
    return calendar


def is_workday(day: dt.date, repository: ProductionCalendarRepository | None = None) -> bool:
    """Определяет, является ли день рабочим в России

    Использует производственный календарь года из репозитория. Если календаря
    на год даты нет, рабочий/нерабочий день определяется по дню недели
    (суббота и воскресенье — выходные).

    Args:
        day: проверяемая дата
        repository: репозиторий календарей; по умолчанию data/production_calendar

    Returns:
        True, если день рабочий

    Raises:
        json.JSONDecodeError: если файл календаря повреждён
        OSError: при ошибке чтения файла календаря
    """
    repository = repository if repository is not None else ProductionCalendarRepository()
    calendar = repository.load(day.year)
    if calendar is None:
        return day.weekday() < 5
    return calendar.is_workday(day)


def is_today_workday(repository: ProductionCalendarRepository | None = None) -> bool:
    """Определяет, является ли сегодняшний день рабочим в России

    Args:
        repository: репозиторий календарей; по умолчанию data/production_calendar

    Returns:
        True, если сегодня рабочий день

    Raises:
        json.JSONDecodeError: если файл календаря повреждён
        OSError: при ошибке чтения файла календаря
    """
    return is_workday(dt.date.today(), repository)
