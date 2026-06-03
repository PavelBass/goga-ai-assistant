"""WebSocket-эндпоинт живой ленты чата

Отдаёт командному сайту новые сообщения чата в реальном времени. Формат
сообщения в кадре совпадает с REST (``MessageOut``) — см. ``docs/chat-stream-ws.md``.

Авторизация — тем же сервисным Bearer-токеном, что и REST, но токен берётся из
query-параметра ``token`` (браузерный WebSocket не умеет ставить заголовки) либо
из заголовка ``Authorization`` (серверный прокси). Маршрут вынесен в отдельный
роутер без роутерной Bearer-зависимости REST — у WebSocket своя проверка.
"""

import asyncio
import logging

from fastapi import (
    APIRouter,
    WebSocket,
    WebSocketDisconnect,
)

from goga.api.realtime import hub
from goga.api.serializers import message_to_out
from goga.api.tokens import verify_token
from goga.data.chat_history import ChatHistoryRepository
from goga.db.engine import session_scope

logger = logging.getLogger('Goga stream')

router = APIRouter(prefix='/api/v1/chats', tags=['chat stream'])

# Интервал heartbeat-кадра при простое (короче nginx proxy_read_timeout).
_PING_INTERVAL_SECONDS = 25.0
# Максимум сообщений добора по after_id, чтобы не залить клиента при большой дыре.
_BACKFILL_LIMIT = 200
# Код закрытия «не авторизован» (4000-4999 — прикладные коды WebSocket).
_CLOSE_UNAUTHORIZED = 4401


async def _extract_token(websocket: WebSocket, token: str | None) -> str | None:
    """Достаёт сервисный токен из query-параметра или заголовка Authorization

    Args:
        websocket: соединение (источник заголовков)
        token: значение query-параметра ``token`` (или None)
    """
    if token:
        return token
    header = websocket.headers.get('authorization')
    if header and header.lower().startswith('bearer '):
        return header[len('bearer ') :].strip() or None
    return None


async def _is_authorized(websocket: WebSocket, token: str | None) -> bool:
    """Проверяет, что соединение предъявило действующий сервисный токен

    Args:
        websocket: соединение (источник заголовков)
        token: значение query-параметра ``token`` (или None)

    Raises:
        sqlalchemy.exc.SQLAlchemyError: при ошибке проверки токена в БД
    """
    candidate = await _extract_token(websocket, token)
    if not candidate:
        return False
    async with session_scope() as session:
        return await verify_token(session, candidate) is not None


async def _send_backfill(websocket: WebSocket, chat_id: int, after_id: int) -> None:
    """Дошлёт сообщения, появившиеся после after_id (закрытие дыры за REST)

    Шлёт как ``message.new``; клиент дедуплицирует по ``tg_message_id``. Ограничен
    ``_BACKFILL_LIMIT`` — большую дыру клиент добирает обычным REST по ``after_id``.

    Args:
        websocket: соединение
        chat_id: telegram id чата
        after_id: tg_message_id, после которого слать сообщения (не включая)

    Raises:
        sqlalchemy.exc.SQLAlchemyError: при ошибке чтения из БД
    """
    async with session_scope() as session:
        messages = await ChatHistoryRepository(session).messages_after(chat_id, after_id, _BACKFILL_LIMIT)
    for message in messages:
        payload = message_to_out(message).model_dump(mode='json')
        await websocket.send_json({'type': 'message.new', 'message': payload})


async def _pump(websocket: WebSocket, queue: asyncio.Queue) -> None:
    """Гонит события из очереди подписчика в сокет, heartbeat'ит при простое

    Args:
        websocket: соединение
        queue: очередь подписчика из ChatHub.subscribe

    Raises:
        WebSocketDisconnect: при закрытии соединения клиентом
    """
    while True:
        try:
            event = await asyncio.wait_for(queue.get(), timeout=_PING_INTERVAL_SECONDS)
        except TimeoutError:
            await websocket.send_json({'type': 'ping'})
            continue
        await websocket.send_json(event)


@router.websocket('/{chat_id}/ws')
async def chat_stream(
    websocket: WebSocket,
    chat_id: int,
    token: str | None = None,
    after_id: int | None = None,
) -> None:
    """Живая лента сообщений чата по WebSocket

    Подписка оформляется ДО добора по ``after_id`` — поэтому сообщения, пришедшие
    во время добора, не теряются (попадут в очередь и уйдут следом; возможный
    повтор клиент гасит upsert'ом по ``tg_message_id``).

    Args:
        websocket: соединение
        chat_id: telegram id чата
        token: сервисный токен (если не в заголовке Authorization)
        after_id: наибольший уже отрисованный tg_message_id для добора дыры
    """
    await websocket.accept()
    if not await _is_authorized(websocket, token):
        await websocket.close(code=_CLOSE_UNAUTHORIZED)
        return

    queue = hub.subscribe(chat_id)
    try:
        if after_id is not None:
            await _send_backfill(websocket, chat_id, after_id)
        await _pump(websocket, queue)
    except WebSocketDisconnect:
        pass
    # Любая иная ошибка не должна валить процесс бота — логируем и закрываем
    except Exception:
        logger.exception('Ошибка в живой ленте чата %s', chat_id)
    finally:
        hub.unsubscribe(chat_id, queue)
