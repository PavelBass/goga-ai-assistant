"""Хранилище истории чата (PostgreSQL)

Репозиторий работает поверх переданной асинхронной сессии и НЕ выполняет commit
самостоятельно — управление транзакцией остаётся за вызывающей стороной
(``session_scope`` или FastAPI-зависимостью ``get_session``).

Сообщения идемпотентны по паре (chat_id, tg_message_id): повторная вставка того
же сообщения игнорируется, правка обновляет text/edit_date/entities/raw. Порядок
и keyset-пагинация строятся по tg_message_id (монотонно растёт в пределах чата).
"""

import datetime as dt
from collections.abc import Sequence

from sqlalchemy import (
    exists,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from goga.db.models import (
    Chat,
    MediaType,
    Message,
    MessageDirection,
    MessageMedia,
)


class ChatHistoryRepository:
    """Репозиторий истории чата поверх асинхронной сессии SQLAlchemy

    Attributes:
        session: асинхронная сессия, в рамках которой выполняются операции
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_chat(
        self,
        *,
        chat_id: int,
        chat_type: str,
        title: str | None = None,
        username: str | None = None,
    ) -> None:
        """Создаёт или обновляет запись чата (последнее известное состояние)

        Args:
            chat_id: telegram id чата
            chat_type: тип чата (private/group/supergroup/channel)
            title: название чата
            username: публичный username чата (без @)

        Raises:
            sqlalchemy.exc.SQLAlchemyError: при ошибке записи в БД
        """
        statement = pg_insert(Chat).values(id=chat_id, type=chat_type, title=title, username=username)
        statement = statement.on_conflict_do_update(
            index_elements=[Chat.id],
            set_={
                'type': statement.excluded.type,
                'title': statement.excluded.title,
                'username': statement.excluded.username,
                'updated_at': dt.datetime.now(dt.UTC),
            },
        )
        await self._session.execute(statement)

    async def save_message(
        self,
        *,
        chat_id: int,
        tg_message_id: int,
        direction: MessageDirection,
        date: dt.datetime,
        content_type: str,
        sender_user_id: int | None = None,
        sender_username: str | None = None,
        sender_name: str | None = None,
        edit_date: dt.datetime | None = None,
        text: str | None = None,
        entities: list | None = None,
        reply_to_tg_message_id: int | None = None,
        forward_origin: dict | None = None,
        forward_sender_name: str | None = None,
        media_group_id: str | None = None,
        raw: dict | None = None,
    ) -> int | None:
        """Сохраняет сообщение идемпотентно по (chat_id, tg_message_id)

        Args:
            chat_id: telegram id чата
            tg_message_id: telegram message_id
            direction: направление (входящее/исходящее)
            date: момент отправки
            content_type: тип содержимого (значение aiogram ContentType)
            sender_user_id: telegram id отправителя
            sender_username: username отправителя (снимок)
            sender_name: отображаемое имя отправителя (снимок)
            edit_date: момент правки, если применимо
            text: текст или подпись к медиа
            entities: форматирование (список dump'ов)
            reply_to_tg_message_id: tg_message_id сообщения-ответа
            forward_origin: источник пересланного сообщения (dump)
            forward_sender_name: отображаемое имя источника пересылки
            media_group_id: идентификатор альбома
            raw: полный JSON-дамп сообщения

        Returns:
            внутренний id вставленного сообщения, либо None, если сообщение с
            такой парой (chat_id, tg_message_id) уже существовало

        Raises:
            sqlalchemy.exc.SQLAlchemyError: при ошибке записи в БД
        """
        statement = (
            pg_insert(Message)
            .values(
                chat_id=chat_id,
                tg_message_id=tg_message_id,
                direction=direction,
                date=date,
                content_type=content_type,
                sender_user_id=sender_user_id,
                sender_username=sender_username,
                sender_name=sender_name,
                edit_date=edit_date,
                text=text,
                entities=entities,
                reply_to_tg_message_id=reply_to_tg_message_id,
                forward_origin=forward_origin,
                forward_sender_name=forward_sender_name,
                media_group_id=media_group_id,
                raw=raw,
            )
            .on_conflict_do_nothing(constraint='uq_messages_chat_tg_id')
            .returning(Message.id)
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def apply_edit(
        self,
        *,
        chat_id: int,
        tg_message_id: int,
        edit_date: dt.datetime | None,
        text: str | None = None,
        entities: list | None = None,
        raw: dict | None = None,
    ) -> bool:
        """Применяет правку к ранее сохранённому сообщению

        Args:
            chat_id: telegram id чата
            tg_message_id: telegram message_id
            edit_date: момент правки
            text: новый текст/подпись
            entities: новое форматирование
            raw: новый полный JSON-дамп

        Returns:
            True, если сообщение нашлось и было обновлено, иначе False

        Raises:
            sqlalchemy.exc.SQLAlchemyError: при ошибке записи в БД
        """
        result = await self._session.execute(
            update(Message)
            .where(Message.chat_id == chat_id, Message.tg_message_id == tg_message_id)
            .values(edit_date=edit_date, text=text, entities=entities, raw=raw)
        )
        return bool(result.rowcount)

    async def add_media(
        self,
        *,
        message_id: int,
        media_type: MediaType,
        file_id: str,
        file_unique_id: str,
        file_name: str | None = None,
        mime_type: str | None = None,
        file_size: int | None = None,
        width: int | None = None,
        height: int | None = None,
        duration: int | None = None,
        downloaded: bool = False,
        download_error: str | None = None,
    ) -> int:
        """Добавляет метаданные медиавложения к сообщению

        Args:
            message_id: внутренний id сообщения
            media_type: тип вложения
            file_id: telegram file_id
            file_unique_id: стабильный идентификатор файла
            file_name: исходное имя файла
            mime_type: MIME-тип
            file_size: размер в байтах
            width: ширина
            height: высота
            duration: длительность в секундах
            downloaded: скачаны ли байты
            download_error: причина, по которой байты не скачаны

        Returns:
            id созданной записи медиа

        Raises:
            sqlalchemy.exc.SQLAlchemyError: при ошибке записи в БД
        """
        media = MessageMedia(
            message_id=message_id,
            media_type=media_type,
            file_id=file_id,
            file_unique_id=file_unique_id,
            file_name=file_name,
            mime_type=mime_type,
            file_size=file_size,
            width=width,
            height=height,
            duration=duration,
            downloaded=downloaded,
            download_error=download_error,
        )
        self._session.add(media)
        await self._session.flush()
        return media.id

    async def mark_media_downloaded(self, media_id: int, *, storage_path: str) -> None:
        """Помечает медиа скачанным и сохраняет путь к файлу

        Args:
            media_id: id записи медиа
            storage_path: относительный путь к скачанному файлу

        Raises:
            sqlalchemy.exc.SQLAlchemyError: при ошибке записи в БД
        """
        await self._session.execute(
            update(MessageMedia)
            .where(MessageMedia.id == media_id)
            .values(downloaded=True, storage_path=storage_path, download_error=None)
        )

    async def mark_media_failed(self, media_id: int, *, error: str) -> None:
        """Помечает медиа нескачанным с указанием причины

        Args:
            media_id: id записи медиа
            error: причина (например, too_large или текст ошибки)

        Raises:
            sqlalchemy.exc.SQLAlchemyError: при ошибке записи в БД
        """
        await self._session.execute(
            update(MessageMedia).where(MessageMedia.id == media_id).values(downloaded=False, download_error=error)
        )

    async def get_message(self, chat_id: int, tg_message_id: int) -> Message | None:
        """Возвращает сообщение по паре (chat_id, tg_message_id) вместе с media

        Используется живой лентой для сериализации только что сохранённого
        сообщения. Связанное media подгружается через selectin (см. модель).

        Args:
            chat_id: telegram id чата
            tg_message_id: telegram message_id

        Raises:
            sqlalchemy.exc.SQLAlchemyError: при ошибке чтения из БД
        """
        result = await self._session.execute(
            select(Message).where(Message.chat_id == chat_id, Message.tg_message_id == tg_message_id)
        )
        return result.scalar_one_or_none()

    async def list_chats(self) -> Sequence[Chat]:
        """Возвращает все известные чаты

        Raises:
            sqlalchemy.exc.SQLAlchemyError: при ошибке чтения из БД
        """
        result = await self._session.execute(select(Chat).order_by(Chat.id))
        return result.scalars().all()

    async def latest(self, chat_id: int, limit: int) -> Sequence[Message]:
        """Возвращает последние сообщения чата в хронологическом порядке

        Args:
            chat_id: telegram id чата
            limit: максимум сообщений

        Raises:
            sqlalchemy.exc.SQLAlchemyError: при ошибке чтения из БД
        """
        result = await self._session.execute(
            select(Message).where(Message.chat_id == chat_id).order_by(Message.tg_message_id.desc()).limit(limit)
        )
        return list(reversed(result.scalars().all()))

    async def messages_before(self, chat_id: int, before_id: int, limit: int) -> Sequence[Message]:
        """Возвращает сообщения чата перед заданным (листание вверх)

        Args:
            chat_id: telegram id чата
            before_id: tg_message_id, перед которым берутся сообщения (не включая)
            limit: максимум сообщений

        Raises:
            sqlalchemy.exc.SQLAlchemyError: при ошибке чтения из БД
        """
        result = await self._session.execute(
            select(Message)
            .where(Message.chat_id == chat_id, Message.tg_message_id < before_id)
            .order_by(Message.tg_message_id.desc())
            .limit(limit)
        )
        return list(reversed(result.scalars().all()))

    async def messages_after(self, chat_id: int, after_id: int, limit: int) -> Sequence[Message]:
        """Возвращает сообщения чата после заданного (догрузка новых)

        Args:
            chat_id: telegram id чата
            after_id: tg_message_id, после которого берутся сообщения (не включая)
            limit: максимум сообщений

        Raises:
            sqlalchemy.exc.SQLAlchemyError: при ошибке чтения из БД
        """
        result = await self._session.execute(
            select(Message)
            .where(Message.chat_id == chat_id, Message.tg_message_id > after_id)
            .order_by(Message.tg_message_id.asc())
            .limit(limit)
        )
        return result.scalars().all()

    async def has_before(self, chat_id: int, tg_message_id: int) -> bool:
        """Есть ли в чате сообщения старше заданного (для флага has_more)

        Args:
            chat_id: telegram id чата
            tg_message_id: граничный tg_message_id

        Raises:
            sqlalchemy.exc.SQLAlchemyError: при ошибке чтения из БД
        """
        result = await self._session.execute(
            select(exists().where(Message.chat_id == chat_id, Message.tg_message_id < tg_message_id))
        )
        return bool(result.scalar())

    async def get_media(self, chat_id: int, file_unique_id: str) -> MessageMedia | None:
        """Возвращает медиавложение чата по стабильному идентификатору файла

        Args:
            chat_id: telegram id чата (область видимости)
            file_unique_id: стабильный идентификатор файла

        Raises:
            sqlalchemy.exc.SQLAlchemyError: при ошибке чтения из БД
        """
        result = await self._session.execute(
            select(MessageMedia)
            .join(Message, MessageMedia.message_id == Message.id)
            .where(Message.chat_id == chat_id, MessageMedia.file_unique_id == file_unique_id)
            .limit(1)
        )
        return result.scalar_one_or_none()
