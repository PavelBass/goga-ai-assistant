"""Pydantic-схемы запросов и ответов HTTP API"""

import datetime as dt

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from goga.db.models import (
    MediaType,
    MessageDirection,
    NewsStatus,
)


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


class ChatOut(BaseModel):
    """Чат в ответе API истории

    Attributes:
        id: telegram id чата
        type: тип чата (private/group/supergroup/channel)
        title: название чата
        username: публичный username чата (без @)
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    title: str | None
    username: str | None


class MediaOut(BaseModel):
    """Медиавложение сообщения в ответе API

    Attributes:
        media_type: тип вложения
        file_unique_id: стабильный идентификатор файла (используется в url)
        url: ссылка на эндпоинт отдачи байтов файла (None, если не скачано)
        mime_type: MIME-тип
        file_name: исходное имя файла
        file_size: размер в байтах
        width: ширина
        height: высота
        duration: длительность в секундах
        downloaded: скачаны ли байты (если нет — байты по url недоступны)
    """

    model_config = ConfigDict(from_attributes=True)

    media_type: MediaType
    file_unique_id: str
    url: str | None = None
    mime_type: str | None = None
    file_name: str | None = None
    file_size: int | None = None
    width: int | None = None
    height: int | None = None
    duration: int | None = None
    downloaded: bool


class MessageOut(BaseModel):
    """Сообщение чата в ответе API

    Attributes:
        chat_id: telegram id чата
        tg_message_id: telegram message_id (курсор пагинации)
        direction: направление (входящее/исходящее)
        date: момент отправки
        edit_date: момент правки (None, если не редактировалось)
        sender_user_id: telegram id отправителя
        sender_username: username отправителя (снимок)
        sender_name: отображаемое имя отправителя (снимок)
        text: текст или подпись к медиа
        entities: форматирование (entities/caption_entities)
        reply_to_tg_message_id: tg_message_id сообщения-ответа
        forward_origin: источник пересланного сообщения
        forward_sender_name: отображаемое имя источника пересылки
        media_group_id: идентификатор альбома
        content_type: тип содержимого (значение aiogram ContentType)
        media: медиавложение (или None)
    """

    model_config = ConfigDict(from_attributes=True)

    chat_id: int
    tg_message_id: int
    direction: MessageDirection
    date: dt.datetime
    edit_date: dt.datetime | None
    sender_user_id: int | None
    sender_username: str | None
    sender_name: str | None
    text: str | None
    entities: list[dict] | None
    reply_to_tg_message_id: int | None
    forward_origin: dict | None
    forward_sender_name: str | None
    media_group_id: str | None
    content_type: str
    media: MediaOut | None = None


class MessagesPage(BaseModel):
    """Страница сообщений чата для отрисовки истории

    Сообщения отсортированы по времени (по возрастанию tg_message_id).

    Attributes:
        messages: сообщения страницы (в хронологическом порядке)
        has_more: есть ли более старые сообщения (для листания вверх)
        oldest_id: tg_message_id самого старого сообщения страницы (курсор before_id)
        newest_id: tg_message_id самого нового сообщения страницы (курсор after_id)
    """

    messages: list[MessageOut]
    has_more: bool
    oldest_id: int | None
    newest_id: int | None
