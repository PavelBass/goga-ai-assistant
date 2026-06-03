"""ORM-модели данных Гоги"""

import datetime as dt
import enum

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from goga.db.engine import Base


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
