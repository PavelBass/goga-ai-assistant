import datetime as dt
import json
import time
from collections.abc import Iterable
from functools import cached_property
from pathlib import Path
from random import shuffle

from pydantic import (
    BaseModel,
    Field,
)


class DailyState(BaseModel):
    """Состояние назначений ведущих дейли"""

    left: list[str] = Field(default_factory=list)
    changed_at: float = Field(default_factory=time.time)

    def set_left(self, participants: Iterable[str]) -> None:
        """Установить список выбора ведущих дейли"""
        self.left = list(participants)
        shuffle(self.left)
        self.changed_at = time.time()


class Daily(BaseModel):
    """Участники дейли"""

    participants: set[str] = Field(default_factory=set)
    state: DailyState = Field(default_factory=DailyState)

    def add_participants(self, participants: list[str]) -> None:
        """Добавить участников дейли"""
        self.participants.update(participants)

    def change_random_participant(self):
        """Сменить ведущего дейли"""
        if not self.state.left:
            self.state.set_left(self.participants)
        else:
            self.state.left.pop()

    @property
    def random_participant(self) -> str | None:
        """Случайный ведущий дейли"""
        return self.state.left[-1] if self.state.left else None


class DailyStandupParticipantsRepository:
    """Репозиторий данных участников дейли"""

    def __init__(self, file_path: str = 'dailydb.json') -> None:
        self._path = Path(file_path)

    def __repr__(self) -> str:
        return f'DailyStandupParticipantsRepository(file_path="{self._path}", data={self.data})'

    @cached_property
    def data(self) -> Daily:
        """Данные участников дейли"""
        if not self._path.is_file():
            self._initiate_data()
        text = self._path.read_text()
        data = json.loads(text)
        return Daily(**data)

    def _initiate_data(self) -> None:
        try:
            with open(self._path, 'w') as data_file:
                data_file.write(Daily().model_dump_json())
        except:
            self._path.unlink(missing_ok=True)

    def _save_data(self) -> None:
        with open(self._path, 'w') as data_file:
            data_file.write(self.data.model_dump_json())

    def add_participants(self, participants: list[str]) -> None:
        """Добавить участников дейли"""
        self.data.add_participants(participants)
        self._save_data()

    def get_all_participants(self) -> set[str]:
        """Получить всех участников дейли"""
        return self.data.participants.copy()

    @property
    def today_random_participant(self) -> str:
        """Случайный ведущий дейли на сегодня"""
        if not self.data.random_participant:
            self.data.change_random_participant()
            self._save_data()
        last_random_at = dt.datetime.fromtimestamp(self.data.state.changed_at)
        today = dt.datetime.now()
        if last_random_at.day != today.day:
            self.data.change_random_participant()
            self._save_data()
        return self.data.random_participant
    
    def force_change_today_random_participant(self) -> None:
        """Сменить случайного ведущего дейли на сегодня"""
        self.data.change_random_participant()
        self._save_data()
    
