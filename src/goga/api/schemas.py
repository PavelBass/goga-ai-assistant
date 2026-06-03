"""Pydantic-схемы запросов и ответов HTTP API"""

import datetime as dt

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from goga.db.models import NewsStatus


class NewsCreate(BaseModel):
    """Тело запроса на создание новости

    Attributes:
        title: заголовок новости
        description: краткий анонс (тело новости)
        url: ссылка на оригинальную статью
        source_date: дата публикации оригинала
        scheduled_for: день, на который запланирован показ
        position: порядок показа в пределах дня
        status: явный статус показа (по умолчанию выбирается автоматически)
    """

    title: str = Field(min_length=1)
    description: str = ''
    url: str | None = None
    source_date: dt.date | None = None
    scheduled_for: dt.date | None = None
    position: int | None = None
    status: NewsStatus | None = None


class NewsUpdate(BaseModel):
    """Тело запроса на изменение новости (все поля необязательны)

    Attributes:
        title: новый заголовок
        description: новый анонс
        url: новая ссылка
        source_date: новая дата публикации
        scheduled_for: новый день показа (перенос плана)
        position: новый порядок в пределах дня
        status: новый статус показа
    """

    title: str | None = Field(default=None, min_length=1)
    description: str | None = None
    url: str | None = None
    source_date: dt.date | None = None
    scheduled_for: dt.date | None = None
    position: int | None = None
    status: NewsStatus | None = None


class NewsOut(BaseModel):
    """Представление новости в ответе API

    Attributes:
        id: идентификатор новости
        title: заголовок
        description: анонс
        url: ссылка на оригинал
        source_date: дата публикации оригинала
        status: статус показа
        scheduled_for: запланированный день показа
        position: порядок показа в пределах дня
        created_at: момент добавления
        shown_at: момент показа
        created_by: источник добавления
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    url: str | None
    source_date: dt.date | None
    status: NewsStatus
    scheduled_for: dt.date | None
    position: int | None
    created_at: dt.datetime
    shown_at: dt.datetime | None
    created_by: str | None


class ModeratorOut(BaseModel):
    """Ведущий Daily Standup

    Attributes:
        username: telegram username ведущего (без @)
        name: имя участника, если известно
    """

    username: str
    name: str | None = None


class ParticipantOut(BaseModel):
    """Участник Daily Standup

    Attributes:
        username: telegram username (без @)
        name: имя участника
    """

    username: str
    name: str
