import datetime as dt
import json
import random
import time
from collections import deque
from collections.abc import Iterable
from functools import cached_property
from pathlib import Path


class DailyState:
    """Состояние списка ведущих дейли"""

    def __init__(
            self,
            pretendents: Iterable[str] | None = None,
            increased_at: float | None = None,
            decreased_at: float | None = None,
    ) -> None:
        """Инициализация класса Pretendents"""
        if pretendents is not None:
            if not all([increased_at, decreased_at]):
                raise ValueError('Both increased_at and decreased_at must be provided for pretendents')
        self._pretendents = deque(pretendents) if pretendents else deque()
        now = time.time
        self._increased_at = increased_at or now
        self._decreased_at = decreased_at or now

    @property
    def increased_at(self) -> float:
        """Время последнего увеличения списка ведущих дейли"""
        return self._increased_at

    @property
    def decreased_at(self) -> float:
        """Время последнего уменьшения списка ведущих дейли"""
        return self._decreased_at

    @property
    def has_members(self) -> bool:
        """Есть ли участники в списке ведущих дейли"""
        return bool(self)

    def add_member(self, member: str) -> None:
        """Добавить претенденда"""
        self._pretendents.append(member)
        self._increased_at = time.time()

    def add_members(self, members: Iterable[str], *, shuffle: bool = True) -> None:
        """Добавить несколько претендентов"""
        members = list(members)
        if not members:
            return
        if shuffle:
            random.shuffle(members)
            if self.current_pretendent and len(members) > 1:
                while members[0] == self.current_pretendent:
                    random.shuffle(members)
        self._pretendents.extend(members)
        self._increased_at = time.time()

    @property
    def current_pretendent(self) -> str | None:
        """Ближайший претендент"""
        return self._pretendents[0] if self._pretendents else None

    @property
    def next_pretendent(self) -> str | None:
        """Следующий претендент"""
        return self._pretendents[1] if len(self._pretendents) > 1 else None

    def __bool__(self):
        """Приведение списка претендентов на роль ведущего дейли к булевому типу"""
        return bool(self._pretendents)

    def __repr__(self):
        """Однозначное строковое представление"""
        return f'Pretendents(participants={self._pretendents}, increased_at={self._increased_at}, decreased_at={self._decreased_at})'

    def pop(self) -> str | None:
        """Извлечь ближайшего претендента"""
        pretendent = None
        if self._pretendents:
            pretendent = self._pretendents.popleft()
            self._decreased_at = time.time()
        return pretendent

    def as_dict(self) -> dict:
        """Преобразование в словарь"""
        return {
            'pretendents': list(self._pretendents),
            'increased_at': self._increased_at,
            'decreased_at': self._decreased_at,
        }

    @classmethod
    def from_dict(cls, data: dict):
        """Инициализация из словаря"""
        return cls(
            pretendents=data['pretendents'],
            increased_at=data['increased_at'],
            decreased_at=data['decreased_at'],
        )

class Daily:
    """Дейли"""

    def __init__(self, state: DailyState | None = None) -> None:
        self._state = state or DailyState()
        self._participants = set()

    def add_participants(self, participants: list[str]) -> None:
        """Добавить участников дейли"""
        self._participants.update(participants)

    def get_all_participants(self) -> set[str]:
        """Получить всех участников дейли"""
        return self._participants.copy()

    def garantee_pretendents_fullness(self) -> None:
        """Обеспечить полноту списка ведущих дейли"""
        if not self._state.next_pretendent:
            self._state.add_members(self._participants, shuffle=True)

    def change_daily_standup_moderator(self) -> None:
        """Сменить ведущего дейли"""
        self.garantee_pretendents_fullness()
        self._state.pop()
        self.garantee_pretendents_fullness()

    @property
    def is_moderator_chosen_today(self) -> bool:
        """Выбран ли ведущий дейли в сегодняшний день"""
        if not self._state.has_members:
            return False
        moderator_is_chosen_at = dt.datetime.fromtimestamp(self._state.decreased_at)
        today = dt.datetime.now()
        return (
                moderator_is_chosen_at.day == today.day
                and moderator_is_chosen_at.month == today.month
                and moderator_is_chosen_at.year == today.year
        )

    @property
    def daily_standup_moderator(self) -> str | None:
        """Ведущий дейли"""
        return self._state.current_pretendent

    def as_dict(self):
        """Преобразование в словарь"""
        return {
            'participants': list(self._participants),
            'state': self._state.as_dict(),
        }

    def as_json(self):
        """Преобразование в JSON"""
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, data: dict):
        """Инициализация из словаря"""
        instance = cls(state=DailyState.from_dict(data['state']))
        instance.add_participants(data['participants'])
        return instance


class DailyRepository:
    """Репозиторий данных участников дейли"""

    def __init__(self, file_path: str | Path = 'dailydb.json') -> None:
        """Инициализация класса DailyStandupParticipantsRepository

        Args:
            file_path: Путь к базе данных (JSON-файлу) участников дейли
        """
        self._path = Path(file_path)

    def __repr__(self) -> str:
        """Однозначное строковое представление"""
        return f'DailyStandupParticipantsRepository(file_path="{self._path}", data={self.data})'

    @cached_property
    def data(self) -> Daily:
        """Данные участников дейли"""
        if not self._path.is_file():
            self._initiate_data()
        text = self._path.read_text()
        data = json.loads(text or '{}')
        return Daily.from_dict(data)

    def _initiate_data(self) -> None:
        """Инициализация базы данных участников дейли"""
        json_data = Daily().as_json()
        try:
            with open(self._path, 'w') as data_file:
                data_file.write(json_data)
        except:  # noqa
            self._path.unlink(missing_ok=True)

    def _save_data(self) -> None:
        """Сохранить данные участников дейли в файл"""
        with open(self._path, 'w') as data_file:
            data_file.write(self.data.as_json())

    def add_participants(self, participants: list[str]) -> None:
        """Добавить участников дейли"""
        self.data.add_participants(participants)
        self._save_data()

    def get_all_participants(self) -> set[str]:
        """Получить всех участников дейли"""
        return self.data.get_all_participants()

    @property
    def today_daily_standup_moderator(self) -> str:
        """Сегодняшний ведущий Daily Standup"""
        if not self.data.is_moderator_chosen_today:
            self.force_change_today_daily_standup_moderator()
        return self.data.daily_standup_moderator  # type: ignore
    
    def force_change_today_daily_standup_moderator(self) -> None:
        """Принудительно меняет назначенного ранее ведущего Daily Standup на сегодня"""
        self.data.change_daily_standup_moderator()
        self._save_data()

