"""Юнит-тесты извлечения полей сообщения для истории чата (без БД и сети)"""

import datetime as dt

from aiogram.types import (
    Chat,
    Message,
    MessageEntity,
    PhotoSize,
    User,
)

from goga.db.models import MediaType
from goga.ui.telegram.aiogram.middlewares.history import (
    extract_media,
    extract_message_fields,
)

_CHAT_ID = -1009999000111


def _text_message() -> Message:
    """Текстовое сообщение с форматированием и ответом"""
    replied = Message(
        message_id=10,
        date=dt.datetime(2026, 6, 3, 11, 0, tzinfo=dt.UTC),
        chat=Chat(id=_CHAT_ID, type='supergroup', title='Команда'),
        from_user=User(id=1, is_bot=False, first_name='Алексей'),
        text='Исходное',
    )
    return Message(
        message_id=11,
        date=dt.datetime(2026, 6, 3, 12, 0, tzinfo=dt.UTC),
        chat=Chat(id=_CHAT_ID, type='supergroup', title='Команда', username='team'),
        from_user=User(id=2, is_bot=False, first_name='Игорь', last_name='С', username='igor'),
        text='Привет Гога',
        entities=[MessageEntity(type='bold', offset=0, length=6)],
        reply_to_message=replied,
    )


def test_extract_text_message_fields():
    """Извлечение текста, отправителя, форматирования и reply без сети"""
    fields = extract_message_fields(_text_message(), store_raw=False)
    assert fields['chat_id'] == _CHAT_ID
    assert fields['tg_message_id'] == 11
    assert fields['text'] == 'Привет Гога'
    assert fields['sender_user_id'] == 2
    assert fields['sender_username'] == 'igor'
    assert fields['sender_name'] == 'Игорь С'
    assert fields['entities'] == [{'type': 'bold', 'offset': 0, 'length': 6}]
    assert fields['reply_to_tg_message_id'] == 10
    assert fields['raw'] is None


def test_extract_message_fields_store_raw():
    """При store_raw=True сохраняется полный дамп сообщения"""
    fields = extract_message_fields(_text_message(), store_raw=True)
    assert isinstance(fields['raw'], dict)
    assert fields['raw']['message_id'] == 11


def test_extract_media_photo():
    """Для фото берётся самый крупный размер и тип Photo; подпись идёт в text"""
    message = Message(
        message_id=12,
        date=dt.datetime(2026, 6, 3, 12, 5, tzinfo=dt.UTC),
        chat=Chat(id=_CHAT_ID, type='supergroup'),
        from_user=User(id=2, is_bot=False, first_name='Игорь'),
        caption='Скрин',
        photo=[
            PhotoSize(file_id='small', file_unique_id='us', width=90, height=90, file_size=100),
            PhotoSize(file_id='big', file_unique_id='ub', width=900, height=900, file_size=10000),
        ],
    )
    media = extract_media(message)
    assert media is not None
    assert media['media_type'] == MediaType.Photo
    assert media['file_id'] == 'big'
    assert media['file_unique_id'] == 'ub'
    assert media['file_size'] == 10000
    assert extract_message_fields(message, store_raw=False)['text'] == 'Скрин'


def test_extract_media_none_for_text():
    """У текстового сообщения медиа нет"""
    assert extract_media(_text_message()) is None
