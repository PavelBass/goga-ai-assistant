"""Сохранение истории чата: перехват входящих и исходящих сообщений

Подход вписан в aiogram и не конфликтует с обработчиками:

- Входящие/правки ловятся outer-middleware на ``dp.message`` и
  ``dp.edited_message`` — он срабатывает на каждое событие до резолва хендлеров.
- Исходящие (ответы Гоги, анонсы, подтверждения команд) ловятся
  request-middleware на ``bot.session``: после успешного API-вызова берётся
  возвращённый ``Message`` (или список) и сохраняется как исходящее.

Сообщение сохраняется идемпотентно по (chat_id, tg_message_id); правка
обновляет существующую запись. Медиа: метаданные пишутся сразу, байты
скачиваются фоновой задачей (чтобы не замедлять обработку) и только если файл
не превышает лимит Bot API (20 МБ).
"""

import asyncio
import json
import logging
import mimetypes
from collections.abc import Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.client.session.middlewares.base import BaseRequestMiddleware
from aiogram.types import Message

from goga import config
from goga.api.realtime import publish_message
from goga.data.chat_history import ChatHistoryRepository
from goga.db.engine import session_scope
from goga.db.models import (
    MediaType,
    MessageDirection,
)
from goga.utils import (
    get_data_directory,
    get_media_directory,
)

logger = logging.getLogger('Goga history')

# Расширения по умолчанию, если их не удаётся вывести из имени файла или MIME
_DEFAULT_EXTENSIONS = {
    MediaType.Photo: '.jpg',
    MediaType.Video: '.mp4',
    MediaType.Animation: '.mp4',
    MediaType.Audio: '.mp3',
    MediaType.Voice: '.ogg',
    MediaType.VideoNote: '.mp4',
    MediaType.Sticker: '.webp',
    MediaType.Document: '',
}

# Необязательные атрибуты, переносимые из медиаобъекта в метаданные «как есть»
_OPTIONAL_MEDIA_ATTRS = ('mime_type', 'file_name', 'duration', 'width', 'height')

# Типы медиа, кроме фото: атрибут сообщения -> тип
_NON_PHOTO_MEDIA = (
    ('video', MediaType.Video),
    ('animation', MediaType.Animation),
    ('document', MediaType.Document),
    ('audio', MediaType.Audio),
    ('voice', MediaType.Voice),
    ('video_note', MediaType.VideoNote),
    ('sticker', MediaType.Sticker),
)

# Сильные ссылки на фоновые задачи скачивания, чтобы их не собрал GC
_BACKGROUND_TASKS: set[asyncio.Task] = set()


def _schedule(coro) -> None:
    """Запускает корутину фоновой задачей, удерживая ссылку на неё

    Args:
        coro: корутина для запуска
    """
    task = asyncio.create_task(coro)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


def _history_settings() -> dict:
    """Возвращает секцию конфига [chat_history] (или пустой dict)"""
    return (config.CONFIG or {}).get('chat_history', {})


def _store_raw() -> bool:
    """Сохранять ли полный JSON-дамп сообщения"""
    return bool(_history_settings().get('store_raw', True))


def _max_download_bytes() -> int:
    """Максимальный размер скачиваемого медиа в байтах (лимит Bot API)"""
    return int(_history_settings().get('max_download_bytes', 20 * 1024 * 1024))


def _should_capture(chat_id: int) -> bool:
    """Сохраняем ли историю этого чата

    Логика совпадает с гейтингом групповых сообщений: чат должен быть в
    списках development/production, а в не-продакшн режиме — только в development.

    Args:
        chat_id: telegram id чата
    """
    chats = (config.CONFIG or {}).get('chats', {})
    development = set(chats.get('development', []))
    monitored = development | set(chats.get('production', []))
    if chat_id not in monitored:
        return False
    if (config.CONFIG or {}).get('general', {}).get('mode') != 'production' and chat_id not in development:
        return False
    return True


def _content_type(message: Message) -> str:
    """Возвращает строковое значение типа содержимого сообщения"""
    value = message.content_type
    return getattr(value, 'value', str(value))


def _json_safe(model: Any) -> Any:
    """Сериализует модель aiogram в JSON-совместимый объект

    Прямой ``model_dump(mode='json')`` падает на sentinel'ах aiogram
    (``aiogram.client.default.Default`` в полях привязанной к боту модели) —
    поэтому дампим в python-объекты и приводим неизвестные типы (Default,
    datetime) к строке через ``json.dumps(default=str)``.

    Args:
        model: pydantic-модель aiogram (Message, MessageEntity, MessageOrigin)

    Raises:
        TypeError: при невозможности привести объект к JSON даже через str
    """
    raw = model.model_dump(mode='python', exclude_none=True)
    return json.loads(json.dumps(raw, default=str, ensure_ascii=False))


def _forward_sender_name(origin: Any) -> str | None:
    """Извлекает отображаемое имя источника пересланного сообщения

    Args:
        origin: объект MessageOrigin (или None)
    """
    if origin is None:
        return None
    user = getattr(origin, 'sender_user', None)
    if user is not None:
        return user.full_name
    hidden = getattr(origin, 'sender_user_name', None)
    if hidden:
        return hidden
    chat = getattr(origin, 'sender_chat', None) or getattr(origin, 'chat', None)
    if chat is not None:
        return chat.title or getattr(chat, 'full_name', None)
    return None


def _sender_name(message: Message) -> str | None:
    """Отображаемое имя отправителя (пользователь или чат-отправитель)"""
    if message.from_user is not None:
        return message.from_user.full_name
    if message.sender_chat is not None:
        return message.sender_chat.title or getattr(message.sender_chat, 'full_name', None)
    return None


def extract_message_fields(message: Message, *, store_raw: bool) -> dict:
    """Извлекает поля сообщения для сохранения в историю

    Чистая функция без обращений к сети/БД — удобно тестировать.

    Args:
        message: сообщение aiogram
        store_raw: сохранять ли полный JSON-дамп сообщения

    Returns:
        словарь именованных аргументов для ChatHistoryRepository.save_message
        (без direction)
    """
    entities = message.entities or message.caption_entities
    origin = message.forward_origin
    return {
        'chat_id': message.chat.id,
        'tg_message_id': message.message_id,
        'date': message.date,
        'edit_date': message.edit_date,
        'content_type': _content_type(message),
        'sender_user_id': message.from_user.id if message.from_user else None,
        'sender_username': message.from_user.username if message.from_user else None,
        'sender_name': _sender_name(message),
        'text': message.text or message.caption,
        'entities': [_json_safe(entity) for entity in entities] if entities else None,
        'reply_to_tg_message_id': message.reply_to_message.message_id if message.reply_to_message else None,
        'forward_origin': _json_safe(origin) if origin else None,
        'forward_sender_name': _forward_sender_name(origin),
        'media_group_id': message.media_group_id,
        'raw': _json_safe(message) if store_raw else None,
    }


def _media_metadata(media_object: Any, media_type: MediaType) -> dict:
    """Собирает метаданные медиа (кроме фото) из объекта aiogram

    Переносит общие поля и необязательные атрибуты, если они есть. Для
    видеосообщения-кружка ширина и высота берутся из length (квадрат).

    Args:
        media_object: объект медиа (Video/Animation/Document/Audio/Voice/…)
        media_type: тип медиа
    """
    data = {
        'media_type': media_type,
        'file_id': media_object.file_id,
        'file_unique_id': media_object.file_unique_id,
        'file_size': media_object.file_size,
    }
    for attribute in _OPTIONAL_MEDIA_ATTRS:
        value = getattr(media_object, attribute, None)
        if value is not None:
            data[attribute] = value
    length = getattr(media_object, 'length', None)
    if length is not None:
        data['width'] = data['height'] = length
    return data


def extract_media(message: Message) -> dict | None:
    """Извлекает метаданные медиавложения сообщения

    Для фото берётся самый крупный размер. Возвращает None, если медиа нет.

    Args:
        message: сообщение aiogram

    Returns:
        словарь именованных аргументов для ChatHistoryRepository.add_media
        (media_type, file_id, file_unique_id и метаданные), либо None
    """
    if message.photo:
        photo = message.photo[-1]
        return {
            'media_type': MediaType.Photo,
            'file_id': photo.file_id,
            'file_unique_id': photo.file_unique_id,
            'file_size': photo.file_size,
            'width': photo.width,
            'height': photo.height,
        }
    for attribute, media_type in _NON_PHOTO_MEDIA:
        media_object = getattr(message, attribute)
        if media_object is not None:
            return _media_metadata(media_object, media_type)
    return None


def _guess_extension(media: dict) -> str:
    """Подбирает расширение файла по имени, MIME или типу медиа

    Args:
        media: метаданные медиа (как из extract_media)
    """
    file_name = media.get('file_name')
    if file_name and '.' in file_name:
        return '.' + file_name.rsplit('.', 1)[1]
    mime_type = media.get('mime_type')
    if mime_type:
        guessed = mimetypes.guess_extension(mime_type)
        if guessed:
            return guessed
    return _DEFAULT_EXTENSIONS.get(media['media_type'], '')


async def _download_media(
    media_id: int, chat_id: int, tg_message_id: int, file_id: str, file_unique_id: str, extension: str
) -> None:
    """Фоновая задача: скачивает медиа на диск и обновляет запись

    Ошибки (в т.ч. файл больше лимита Bot API) перехватываются и фиксируются в
    download_error — отправка/обработка сообщений при этом не страдает. После
    успешного скачивания сообщение перерассылается в живую ленту как
    ``message.edited`` — у медиа появляется url, и страница обновляет вложение.

    Args:
        media_id: id записи медиа
        chat_id: telegram id чата (для каталога)
        tg_message_id: telegram message_id сообщения (для оповещения живой ленты)
        file_id: telegram file_id для скачивания
        file_unique_id: стабильный идентификатор файла (имя файла на диске)
        extension: расширение файла
    """
    from goga.ui.telegram.aiogram.bot import bot

    try:
        directory = get_media_directory() / str(chat_id)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f'{file_unique_id}{extension}'
        await bot.download(file_id, destination=path)
        relative_path = path.relative_to(get_data_directory())
        async with session_scope() as session:
            await ChatHistoryRepository(session).mark_media_downloaded(media_id, storage_path=str(relative_path))
        logger.info('Медиа сохранено: %s', relative_path)
        await publish_message(chat_id, tg_message_id, 'message.edited')
    # Любая ошибка скачивания (в т.ч. файл больше лимита) не должна ломать бота
    except Exception as error:
        logger.warning('Не удалось скачать медиа %s: %s', file_unique_id, error)
        try:
            async with session_scope() as session:
                await ChatHistoryRepository(session).mark_media_failed(media_id, error=str(error)[:500])
        except Exception:
            logger.exception('Не удалось зафиксировать ошибку скачивания медиа')


async def _store(
    *,
    message: Message,
    direction: MessageDirection,
    fields: dict,
    media: dict | None,
    too_large: bool,
) -> tuple[str | None, int | None]:
    """Сохраняет сообщение/правку в БД и сообщает, что произошло

    Медиа добавляется только при первичной вставке.

    Args:
        message: сообщение aiogram (источник данных чата)
        direction: направление (входящее/исходящее)
        fields: поля сообщения (из extract_message_fields)
        media: метаданные медиа (из extract_media) или None
        too_large: превышает ли медиа лимит скачивания Bot API

    Returns:
        кортеж (тип события для живой ленты, id записи медиа). Тип события:
        ``message.new`` при вставке, ``message.edited`` при применённой правке,
        None если сообщение-дубликат без изменений. Id медиа — только при вставке
        нового медиа, иначе None.

    Raises:
        sqlalchemy.exc.SQLAlchemyError: при ошибке записи в БД
    """
    async with session_scope() as session:
        repository = ChatHistoryRepository(session)
        chat = message.chat
        await repository.upsert_chat(chat_id=chat.id, chat_type=chat.type, title=chat.title, username=chat.username)
        inserted_id = await repository.save_message(direction=direction, **fields)
        if inserted_id is None:
            if fields['edit_date'] is None:
                return None, None
            updated = await repository.apply_edit(
                chat_id=fields['chat_id'],
                tg_message_id=fields['tg_message_id'],
                edit_date=fields['edit_date'],
                text=fields['text'],
                entities=fields['entities'],
                raw=fields['raw'],
            )
            return ('message.edited' if updated else None), None
        media_id = None
        if media is not None:
            media_id = await repository.add_media(
                message_id=inserted_id,
                downloaded=False,
                download_error='too_large' if too_large else None,
                **media,
            )
        return 'message.new', media_id


async def persist_message(message: Message, direction: MessageDirection) -> None:
    """Сохраняет сообщение в историю, планирует скачивание медиа и шлёт в ленту

    Новое сообщение вставляется; для уже сохранённого с проставленным edit_date
    применяется правка. Сохранённое/изменённое сообщение рассылается подписчикам
    живой ленты чата (publish_message сам ничего не делает, если чат не слушают).

    Args:
        message: сообщение aiogram
        direction: направление (входящее/исходящее)

    Raises:
        sqlalchemy.exc.SQLAlchemyError: при ошибке записи в БД
    """
    fields = extract_message_fields(message, store_raw=_store_raw())
    media = extract_media(message)
    too_large = bool(media and media.get('file_size') and media['file_size'] > _max_download_bytes())

    event_type, media_id = await _store(
        message=message, direction=direction, fields=fields, media=media, too_large=too_large
    )

    if media_id is not None and media is not None and not too_large:
        _schedule(
            _download_media(
                media_id,
                message.chat.id,
                fields['tg_message_id'],
                media['file_id'],
                media['file_unique_id'],
                _guess_extension(media),
            )
        )

    if event_type is not None:
        await publish_message(fields['chat_id'], fields['tg_message_id'], event_type)


class HistoryCaptureMiddleware(BaseMiddleware):
    """Outer-middleware: сохраняет входящие сообщения и правки в историю"""

    async def __call__(
        self,
        handler: Callable,
        event: Message,
        data: dict,
    ) -> Any:
        """Сохраняет событие-сообщение и передаёт управление дальше

        Args:
            handler: следующий обработчик в цепочке
            event: событие (ожидается Message)
            data: контекст aiogram

        Returns:
            результат вызова следующего обработчика
        """
        try:
            if isinstance(event, Message) and _should_capture(event.chat.id):
                await persist_message(event, MessageDirection.Incoming)
        # Сохранение истории не должно ломать обработку сообщения
        except Exception:
            logger.exception('Ошибка сохранения входящего сообщения в историю')
        return await handler(event, data)


class HistoryRequestMiddleware(BaseRequestMiddleware):
    """Request-middleware: сохраняет исходящие сообщения Гоги в историю"""

    async def __call__(
        self,
        make_request: Callable,
        bot: Any,
        method: Any,
    ) -> Any:
        """Выполняет API-вызов и сохраняет возвращённые сообщения

        Args:
            make_request: следующий вызов в цепочке (возвращает результат метода)
            bot: экземпляр бота
            method: метод Telegram API

        Returns:
            результат вызова API (как и без middleware)
        """
        result = await make_request(bot, method)
        try:
            items = result if isinstance(result, list) else [result]
            for item in items:
                if isinstance(item, Message) and _should_capture(item.chat.id):
                    await persist_message(item, MessageDirection.Outgoing)
        # Сохранение истории не должно ломать отправку сообщения
        except Exception:
            logger.exception('Ошибка сохранения исходящего сообщения в историю')
        return result
