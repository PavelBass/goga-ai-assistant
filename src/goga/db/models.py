"""ORM-модели данных Гоги"""

import datetime as dt
import enum

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from goga.db.engine import Base


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    """Возвращает значения членов перечисления для хранения в БД (lowercase)

    Args:
        enum_cls: класс перечисления

    Raises:
        AttributeError: если у членов нет атрибута value
    """
    return [member.value for member in enum_cls]


class NewsStatus(enum.Enum):
    """Статус новости в жизненном цикле показа

    Attributes:
        Pending: новость добавлена, но не запланирована и не показана
        Scheduled: новость запланирована на конкретный день показа
        Shown: новость показана команде (вместо удаления записи)
        Archived: новость убрана из показа вручную
    """

    Pending = 'pending'
    Scheduled = 'scheduled'
    Shown = 'shown'
    Archived = 'archived'


class News(Base):
    """Новость для ежедневного сообщения команде

    Вместо удаления показанные новости помечаются статусом Shown и временем
    показа shown_at. Поля scheduled_for и position задают план показа на
    ближайшие дни и порядок новостей в пределах одного дня.

    Attributes:
        id: первичный ключ
        title: заголовок новости
        description: краткий анонс (тело новости)
        url: ссылка на оригинальную статью
        source_date: дата публикации оригинала
        status: статус показа (см. NewsStatus)
        scheduled_for: день, на который запланирован показ
        position: порядок показа в пределах дня
        created_at: момент добавления
        shown_at: момент показа (заполняется при пометке показанной)
        created_by: источник добавления (telegram username или имя сервиса)
    """

    __tablename__ = 'news'
    __table_args__ = (
        Index('ix_news_status', 'status'),
        Index('ix_news_schedule', 'scheduled_for', 'position'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default='')
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    status: Mapped[NewsStatus] = mapped_column(
        Enum(NewsStatus, name='news_status', values_callable=lambda enum_cls: [member.value for member in enum_cls]),
        nullable=False,
        default=NewsStatus.Pending,
    )
    scheduled_for: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    shown_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    def __repr__(self) -> str:
        """Однозначное строковое представление"""
        return f'News(id={self.id}, title={self.title!r}, status={self.status.value})'


class ApiToken(Base):
    """Сервисный токен доступа к HTTP API, выпускаемый Гогой

    Полный токен показывается один раз при выпуске и в БД не хранится —
    хранится только его SHA-256 хеш. Отзыв выполняется проставлением
    revoked_at (без удаления записи).

    Attributes:
        id: первичный ключ
        name: уникальное имя сервиса-потребителя
        token_prefix: открытый префикс токена для опознания (не секрет)
        token_hash: SHA-256 хеш полного токена в hex
        created_at: момент выпуска
        last_used_at: момент последнего успешного использования
        revoked_at: момент отзыва (None, если токен активен)
    """

    __tablename__ = 'api_tokens'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    token_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_used_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def is_active(self) -> bool:
        """Активен ли токен (не отозван)"""
        return self.revoked_at is None

    def __repr__(self) -> str:
        """Однозначное строковое представление"""
        return f'ApiToken(id={self.id}, name={self.name!r}, active={self.is_active})'


class MessageDirection(enum.Enum):
    """Направление сообщения относительно бота

    Attributes:
        Incoming: сообщение пришло в чат (от пользователя или другого бота)
        Outgoing: сообщение отправил сам Гога
    """

    Incoming = 'incoming'
    Outgoing = 'outgoing'


class MediaType(enum.Enum):
    """Тип медиавложения сообщения

    Attributes:
        Photo: фотография
        Video: видео
        Animation: анимация (GIF/беззвучное видео)
        Document: документ/файл
        Audio: аудиофайл (музыка)
        Voice: голосовое сообщение
        VideoNote: видеосообщение (кружок)
        Sticker: стикер
    """

    Photo = 'photo'
    Video = 'video'
    Animation = 'animation'
    Document = 'document'
    Audio = 'audio'
    Voice = 'voice'
    VideoNote = 'video_note'
    Sticker = 'sticker'


class Chat(Base):
    """Телеграм-чат, история которого сохраняется

    Хранит последнее известное состояние чата: апсертится при каждом
    сохранённом сообщении. Используется API для списка чатов и заголовков.

    Attributes:
        id: telegram chat id (первичный ключ, задаётся Telegram, не автоинкремент)
        type: тип чата (private/group/supergroup/channel)
        title: название чата (для групп/каналов)
        username: публичный username чата (без @), если есть
        updated_at: момент последнего обновления записи
    """

    __tablename__ = 'chats'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        """Однозначное строковое представление"""
        return f'Chat(id={self.id}, type={self.type!r}, title={self.title!r})'


class Message(Base):
    """Сообщение чата для истории

    Записи идемпотентны по паре (chat_id, tg_message_id): повторная вставка
    того же сообщения игнорируется, правка обновляет text/edit_date/entities.
    Порядок и keyset-пагинация строятся по tg_message_id — он монотонно растёт
    в пределах чата. Полный снимок сообщения хранится в raw (страховка верности
    отображения), если включено в конфиге.

    Attributes:
        id: внутренний автоинкрементный первичный ключ
        chat_id: telegram id чата
        tg_message_id: telegram message_id (уникален в пределах чата)
        sender_user_id: telegram id отправителя (None у сервисных/канальных)
        sender_username: username отправителя на момент отправки (снимок)
        sender_name: отображаемое имя отправителя на момент отправки (снимок)
        direction: направление (входящее/исходящее, см. MessageDirection)
        date: момент отправки сообщения
        edit_date: момент последней правки (None, если не редактировалось)
        text: текст сообщения или подпись к медиа (caption)
        entities: форматирование (entities/caption_entities) как список dump'ов
        reply_to_tg_message_id: tg_message_id сообщения, на которое дан ответ
        forward_origin: источник пересланного сообщения (MessageOrigin dump)
        forward_sender_name: отображаемое имя источника пересылки
        media_group_id: идентификатор альбома (для сгруппированных медиа)
        content_type: тип содержимого (значение aiogram ContentType)
        raw: полный JSON-дамп сообщения (страховка верности отображения)
        created_at: момент сохранения записи
        media: связанное медиавложение (0..1)
    """

    __tablename__ = 'messages'
    __table_args__ = (
        UniqueConstraint('chat_id', 'tg_message_id', name='uq_messages_chat_tg_id'),
        Index('ix_messages_media_group', 'media_group_id'),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tg_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sender_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sender_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sender_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    direction: Mapped[MessageDirection] = mapped_column(
        Enum(MessageDirection, name='message_direction', values_callable=_enum_values),
        nullable=False,
    )
    date: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    edit_date: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    entities: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    reply_to_tg_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    forward_origin: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    forward_sender_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_group_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    content_type: Mapped[str] = mapped_column(String(32), nullable=False)
    raw: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    media: Mapped['MessageMedia | None'] = relationship(
        back_populates='message',
        uselist=False,
        cascade='all, delete-orphan',
        lazy='selectin',
    )

    def __repr__(self) -> str:
        """Однозначное строковое представление"""
        return f'Message(chat_id={self.chat_id}, tg_message_id={self.tg_message_id}, direction={self.direction.value})'


class MessageMedia(Base):
    """Медиавложение сообщения (0..1 на сообщение)

    Байты файла хранятся на диске (storage_path); в БД — только метаданные.
    Если файл крупнее лимита Bot API (20 МБ) или скачать не удалось,
    downloaded=False, а причина — в download_error; запись при этом сохраняется
    (file_id/file_unique_id и метаданные остаются).

    Attributes:
        id: внутренний автоинкрементный первичный ключ
        message_id: ссылка на сообщение (уникальна, 1:1)
        media_type: тип вложения (см. MediaType)
        file_id: telegram file_id (привязан к боту, может меняться)
        file_unique_id: стабильный идентификатор файла (для адресации в API)
        file_name: исходное имя файла (для документов)
        mime_type: MIME-тип содержимого
        file_size: размер файла в байтах (если известен)
        width: ширина (фото/видео)
        height: высота (фото/видео)
        duration: длительность в секундах (аудио/видео/голос)
        storage_path: относительный путь к скачанному файлу на диске
        downloaded: скачаны ли байты файла
        download_error: причина, по которой байты не скачаны (None при успехе)
        message: связанное сообщение
    """

    __tablename__ = 'message_media'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    message_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey('messages.id', ondelete='CASCADE'), nullable=False, unique=True
    )
    media_type: Mapped[MediaType] = mapped_column(
        Enum(MediaType, name='media_type', values_callable=_enum_values),
        nullable=False,
    )
    file_id: Mapped[str] = mapped_column(Text, nullable=False)
    file_unique_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    file_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    downloaded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    download_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    message: Mapped['Message'] = relationship(back_populates='media')

    def __repr__(self) -> str:
        """Однозначное строковое представление"""
        return f'MessageMedia(message_id={self.message_id}, type={self.media_type.value}, downloaded={self.downloaded})'
