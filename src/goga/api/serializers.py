"""Преобразование ORM-объектов истории чата в схемы ответа API

Вынесено отдельно, чтобы один и тот же формат сообщения использовали и REST
(``GET /api/v1/chats/{chat_id}/messages``), и WebSocket живой ленты — клиент
получает байт-в-байт одинаковый ``MessageOut`` по обоим каналам.
"""

from goga.api.schemas import MessageOut
from goga.db.models import Message


def message_to_out(message: Message) -> MessageOut:
    """Преобразует ORM-сообщение в схему ответа, проставляя ссылку на медиа

    Ссылка на байты медиа проставляется только для скачанных вложений; иначе
    ``url`` остаётся ``None`` (байты ещё качаются или скачать не удалось).

    Args:
        message: ORM-объект сообщения (со связанным media)
    """
    out = MessageOut.model_validate(message)
    if out.media is not None:
        if out.media.downloaded:
            out.media.url = f'/api/v1/chats/{message.chat_id}/media/{out.media.file_unique_id}'
        else:
            out.media.url = None
    return out
