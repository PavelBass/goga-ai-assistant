import datetime as dt
import json
import time
from collections.abc import Iterable
from functools import cached_property
from pathlib import Path
from random import shuffle
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    GetPydanticSchema,
)
from pydantic_core import (
    CoreSchema,
    PydanticCustomError,
    core_schema,
)


class Pretendents:
    """Список ведущих дейли"""

    def __init__(
            self,
            participants: Iterable[str] | None = None,
            changed_at: float | None = None,
            * ,
            is_shuffled: bool = False
    ):
        """Инициализация класса Pretendents

        Args:
            participants: Список ведущих дейли
            changed_at: Timestamp изменения списка ведущих дейли
        """
        self._participants = list(participants or [])
        self._changed_at = changed_at
        self._is_shuffled = is_shuffled

    @property
    def changed_at(self) -> float | None:
        """Timestamp изменения списка ведущих дейли"""
        return self._changed_at

    @property
    def is_shuffled(self) -> bool:
        """Был ли список ведущих дейли перемешан"""
        return self._is_shuffled

    @property
    def leader(self) -> str | None:
        """Ведущий дейли"""
        return self._participants[-1] if self._participants else None

    def __iter__(self):
        """Итератор списка ведущих дейли"""
        return iter(self._participants)

    def __len__(self):
        """Длина списка ведущих дейли"""
        return len(self._participants)

    def __bool__(self):
        """Приведение списка ведущих дейли к булевому типу"""
        return bool(self._participants)

    def __repr__(self):
        """Однозначное строковое представление"""
        return f'Pretendents(participants={self._participants}, '\
            f'changed_at={self._changed_at}, is_shuffled={self._is_shuffled})'

    def pop(self):
        """Удалить последнего ведущего дейли"""
        participant = self._participants.pop()
        self._changed_at = time.time()
        return participant

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetPydanticSchema
    ) -> CoreSchema:
        def validate_pretendents(value: Any) -> Pretendents:
            if isinstance(value, Pretendents):
                return value
            if isinstance(value, dict):
                return Pretendents(
                    participants=value.get('participants'),
                    changed_at=value.get('changed_at'),
                    is_shuffled=value.get('is_shuffled', False)
                )
            raise PydanticCustomError(
                'pretendents_type', f'Input should be a list, tuple, set, or FrozenList, got {type(value)}',
                {'kind': 'ValueError'}
            )

        return core_schema.no_info_after_validator_function(
            validate_pretendents,
            core_schema.dict_schema(),  # Initial schema to pass to the validator
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda obj: {'participants': list(obj), 'changed_at': obj.changed_at, 'is_shuffled': obj.is_shuffled}
            ),
        )


class DailyState(BaseModel):
    """Состояние назначений ведущих дейли"""

    pretendents: Pretendents = Field(default_factory=Pretendents)
    changed_at: float = Field(default_factory=time.time)

    def set_pretendents(self, participants: Iterable[str]) -> None:
        """Установить список претендентов на роль ведущего дейли"""
        self.pretendents = Pretendents(participants)
    
    model_config = ConfigDict(
        json_encoders={
            Pretendents: lambda obj: {
                'participants': list(obj),
                'changed_at': obj.changed_at,
                'is_shuffled': obj.is_shuffled
            }
        }
    )



class Daily(BaseModel):
    """Участники дейли"""

    participants: set[str] = Field(default_factory=set)
    state: DailyState = Field(default_factory=DailyState)

    def add_participants(self, participants: list[str]) -> None:
        """Добавить участников дейли"""
        self.participants.update(participants)

    def change_daily_standup_leader(self) -> None:
        """Сменить ведущего дейли"""
        if not self.state.pretendents:
            self.state.set_pretendents(self.participants)
        else:
            self.state.pretendents.pop()

    @property
    def is_leader_chosen_today(self) -> bool:
        """Выбран ли ведущий дейли в сегодняшний день"""
        leader_is_chosen_at = dt.datetime.fromtimestamp(self.state.changed_at)
        today = dt.datetime.now()
        return leader_is_chosen_at.day == today.day

    @property
    def daily_standup_leader(self) -> str | None:
        """Ведущий дейли"""
        return self.state.pretendents.leader


class DailyStandupParticipantsRepository:
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
        data = json.loads(text)
        return Daily(**data)

    def _initiate_data(self) -> None:
        """Инициализация базы данных участников дейли"""
        json_data = Daily().model_dump_json()
        try:
            with open(self._path, 'w') as data_file:
                data_file.write(json_data)
        except:  # noqa
            self._path.unlink(missing_ok=True)

    def _save_data(self) -> None:
        """Сохранить данные участников дейли в файл"""
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
    def today_dayly_standup_leader(self) -> str:
        """Сегодняшний ведущий дейли"""
        if not self.data.daily_standup_leader:
            self.data.change_daily_standup_leader()
            self._save_data()
        if not self.data.is_leader_chosen_today:
            self.data.change_daily_standup_leader()
            self._save_data()
        return self.data.daily_standup_leader  # type: ignore
    
    def force_change_today_random_participant(self) -> None:
        """Сменить случайного ведущего дейли на сегодня"""
        self.data.change_daily_standup_leader()
        self._save_data()

