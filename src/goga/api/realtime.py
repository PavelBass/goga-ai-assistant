"""Живая лента чата: внутрипроцессный pub/sub новых сообщений

HTTP API поднимается в том же процессе и event loop, что и поллинг aiogram (см.
``goga.ui.telegram.aiogram.run``). Поэтому брокер не нужен: продьюсеры (middleware
сохранения истории) и подписчики (WebSocket-соединения) живут в одном loop, и
обмен идёт через ``asyncio.Queue`` без блокировок и внешних зависимостей.

Поток данных: сообщение сохранено в БД → ``publish_message`` подгружает его и
кладёт событие в очереди всех подписчиков чата → WebSocket-эндпоинт отдаёт
событие клиенту. Если чат никто не слушает — обращения к БД не происходит.
"""

import asyncio
import logging

from goga.api.serializers import message_to_out
from goga.data.chat_history import ChatHistoryRepository
from goga.db.engine import session_scope

logger = logging.getLogger('Goga realtime')

# Потолок очереди подписчика: при переполнении (медленный клиент) новые события
# дропаются — клиент добирает пропуск при реконнекте через after_id.
_QUEUE_MAXSIZE = 1000


class ChatHub:
    """Реестр подписчиков живой ленты по чатам (внутри одного event loop)

    Без блокировок: все операции выполняются в одном loop. Подписчик — это
    ``asyncio.Queue``, в которую кладутся события для одного WebSocket-соединения.

    Attributes:
        _subscribers: отображение chat_id -> множество очередей подписчиков
    """

    def __init__(self) -> None:
        self._subscribers: dict[int, set[asyncio.Queue]] = {}

    def subscribe(self, chat_id: int) -> asyncio.Queue:
        """Регистрирует нового подписчика чата и возвращает его очередь

        Args:
            chat_id: telegram id чата
        """
        queue: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
        self._subscribers.setdefault(chat_id, set()).add(queue)
        return queue

    def unsubscribe(self, chat_id: int, queue: asyncio.Queue) -> None:
        """Снимает подписчика; убирает пустую запись чата

        Args:
            chat_id: telegram id чата
            queue: очередь, возвращённая ранее из subscribe
        """
        subscribers = self._subscribers.get(chat_id)
        if subscribers is None:
            return
        subscribers.discard(queue)
        if not subscribers:
            self._subscribers.pop(chat_id, None)

    def has_subscribers(self, chat_id: int) -> bool:
        """Есть ли хотя бы один слушатель чата (для short-circuit без БД)

        Args:
            chat_id: telegram id чата
        """
        return bool(self._subscribers.get(chat_id))

    def publish(self, chat_id: int, event: dict) -> None:
        """Кладёт событие в очереди всех подписчиков чата (без блокировки)

        При переполнении очереди подписчика событие для него дропается — продьюсер
        не должен ждать медленного клиента.

        Args:
            chat_id: telegram id чата
            event: JSON-совместимое событие (кадр сервер -> клиент)
        """
        for queue in tuple(self._subscribers.get(chat_id, ())):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning('Очередь подписчика чата %s переполнена — событие дропнуто', chat_id)


# Единственный на процесс хаб подписок живой ленты.
hub = ChatHub()


async def publish_message(chat_id: int, tg_message_id: int, event_type: str) -> None:
    """Публикует сохранённое сообщение подписчикам живой ленты чата

    Подгружает сообщение из БД (вместе с media) и рассылает его как событие
    ``event_type``. Если чат никто не слушает — выходит сразу, не трогая БД.

    Args:
        chat_id: telegram id чата
        tg_message_id: telegram message_id сохранённого сообщения
        event_type: тип события (``message.new`` или ``message.edited``)

    Raises:
        sqlalchemy.exc.SQLAlchemyError: при ошибке чтения сообщения из БД
    """
    if not hub.has_subscribers(chat_id):
        return
    async with session_scope() as session:
        message = await ChatHistoryRepository(session).get_message(chat_id, tg_message_id)
    if message is None:
        return
    payload = message_to_out(message).model_dump(mode='json')
    hub.publish(chat_id, {'type': event_type, 'message': payload})
