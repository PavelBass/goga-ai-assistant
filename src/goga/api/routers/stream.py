"""WebSocket-эндпоинт живой ленты чата

Отдаёт командному сайту новые сообщения чата в реальном времени. Формат
сообщения в кадре совпадает с REST (``MessageOut``) — см. ``docs/chat-stream-ws.md``.

Авторизация — тем же сервисным Bearer-токеном, что и REST, но токен НЕ кладётся в
URL: query-строка попадает в access-логи nginx/uvicorn и прочую телеметрию, то
есть секрет утёк бы в открытом виде даже под wss. Поэтому клиент первым кадром
шлёт ``{"type":"auth","token":...,"after_id":...}``; серверный прокси может вместо
``token`` в кадре передать заголовок ``Authorization: Bearer`` (но кадр шлёт всё
равно — в нём едет ``after_id``). Кадр ждём не дольше ``_AUTH_TIMEOUT_SECONDS``:
таймаут/обрыв/мусор/неверный токен → закрытие ``4401``. Маршрут вынесен в отдельный
роутер без роутерной Bearer-зависимости REST — у WebSocket своя проверка.
"""

import asyncio
import json
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
# Сколько ждём первый (auth) кадр клиента, прежде чем закрыть как неавторизованного.
# Коротко: неавторизованный сокет уже принят и держит ресурсы (slowloris-поверхность).
_AUTH_TIMEOUT_SECONDS = 5.0


def _header_token(websocket: WebSocket) -> str | None:
    """Достаёт сервисный токен из заголовка ``Authorization: Bearer`` (серверный прокси)

    Args:
        websocket: соединение (источник заголовков)
    """
    header = websocket.headers.get('authorization')
    if header and header.lower().startswith('bearer '):
        return header[len('bearer ') :].strip() or None
    return None


async def _read_auth_frame(websocket: WebSocket) -> dict | None:
    """Читает первый (auth) кадр клиента с таймаутом ``_AUTH_TIMEOUT_SECONDS``

    Любой не-успех (кадр не пришёл вовремя, соединение оборвалось, текст — не
    JSON-объект, прислан бинарный кадр) преобразуется в None: вызывающий трактует
    это как «не авторизован» (fail-closed), отдельные коды наружу не утекают.

    Args:
        websocket: соединение
    """
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=_AUTH_TIMEOUT_SECONDS)
    except (TimeoutError, WebSocketDisconnect, KeyError, RuntimeError):
        return None
    try:
        frame = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None
    return frame if isinstance(frame, dict) else None


async def _authenticate(websocket: WebSocket) -> tuple[bool, int | None]:
    """Авторизует соединение по первому кадру и/или заголовку, возвращает (ok, after_id)

    Протокол: первым кадром клиент шлёт ``{"type":"auth","token":...,"after_id":...}``.
    ``token`` обязателен, если не передан заголовок ``Authorization: Bearer`` (токен в
    кадре имеет приоритет). ``after_id`` — необязательный int для добора дыры за REST;
    нечисловое значение игнорируется. Любой не-успех → ``(False, None)``.

    Args:
        websocket: соединение (источник кадра и заголовков)

    Raises:
        sqlalchemy.exc.SQLAlchemyError: при ошибке проверки токена в БД
    """
    frame = await _read_auth_frame(websocket)
    if frame is None or frame.get('type') != 'auth':
        return False, None
    token = frame.get('token') or _header_token(websocket)
    if not token:
        return False, None
    async with session_scope() as session:
        if await verify_token(session, token) is None:
            return False, None
    after_id = frame.get('after_id')
    return True, after_id if isinstance(after_id, int) and not isinstance(after_id, bool) else None


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
async def chat_stream(websocket: WebSocket, chat_id: int) -> None:
    """Живая лента сообщений чата по WebSocket

    Авторизация и ``after_id`` приезжают первым клиентским кадром (см.
    ``_authenticate``), а не из URL — секрет не должен попадать в query-строку. До
    успешной проверки сервер не шлёт и не читает ничего, кроме auth-кадра.

    Подписка оформляется ДО добора по ``after_id`` — поэтому сообщения, пришедшие
    во время добора, не теряются (попадут в очередь и уйдут следом; возможный
    повтор клиент гасит upsert'ом по ``tg_message_id``).

    Args:
        websocket: соединение
        chat_id: telegram id чата
    """
    await websocket.accept()
    authorized, after_id = await _authenticate(websocket)
    if not authorized:
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
