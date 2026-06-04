"""Тесты авторизации WebSocket-ленты чата первым (auth) кадром

Проверяют контракт ``stream.chat_stream``: токен приходит не в URL, а первым
кадром (или заголовком ``Authorization`` для прокси); неуспех закрывается кодом
4401. БД и поток событий замоканы — тесту не нужна PostgreSQL.

Тесты синхронные: ``starlette.testclient.TestClient`` гоняет ASGI-приложение в
фоновом потоке и поддерживает ``websocket_connect``.
"""

import contextlib

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from goga.api.app import create_app
from goga.api.routers import stream

_VALID_TOKEN = 'goga_valid'
_CHAT_ID = -100


@contextlib.asynccontextmanager
async def _fake_session_scope():
    """Подменяет сессию БД пустышкой — verify_token всё равно замокан"""
    yield None


async def _fake_verify_token(session, token):
    """Возвращает «запись» только для валидного токена, иначе None"""
    return object() if token == _VALID_TOKEN else None


async def _fake_pump(websocket, queue):
    """Вместо живого потока шлёт один маркерный кадр — признак успешной авторизации"""
    await websocket.send_json({'type': 'ping'})


async def _fake_backfill(websocket, chat_id, after_id):
    """Вместо чтения БД эхает полученный after_id — проверяем, что он распознан"""
    await websocket.send_json({'type': 'backfill', 'after_id': after_id})


@pytest.fixture
def client(monkeypatch):
    """TestClient с замоканными БД, проверкой токена и потоком событий"""
    monkeypatch.setattr(stream, 'session_scope', _fake_session_scope)
    monkeypatch.setattr(stream, 'verify_token', _fake_verify_token)
    monkeypatch.setattr(stream, '_pump', _fake_pump)
    monkeypatch.setattr(stream, '_send_backfill', _fake_backfill)
    return TestClient(create_app())


def _url(chat_id: int = _CHAT_ID) -> str:
    return f'/api/v1/chats/{chat_id}/ws'


def _assert_closed_unauthorized(websocket) -> None:
    """Утверждает, что сервер закрыл соединение кодом 4401"""
    with pytest.raises(WebSocketDisconnect) as exc:
        websocket.receive_text()
    assert exc.value.code == 4401


def test_token_must_not_be_in_url(client, monkeypatch):
    """Query-параметр token больше не авторизует: без auth-кадра — таймаут и 4401"""
    monkeypatch.setattr(stream, '_AUTH_TIMEOUT_SECONDS', 0.2)
    # клиент по ошибке надеется на токен в URL и не шлёт auth-кадр
    with client.websocket_connect(f'{_url()}?token={_VALID_TOKEN}') as websocket:
        _assert_closed_unauthorized(websocket)


def test_no_auth_frame_times_out(client, monkeypatch):
    """Без auth-кадра сервер закрывает соединение по таймауту с кодом 4401"""
    monkeypatch.setattr(stream, '_AUTH_TIMEOUT_SECONDS', 0.2)
    with client.websocket_connect(_url()) as websocket:
        _assert_closed_unauthorized(websocket)


def test_first_frame_not_json(client):
    """Первый кадр — не JSON → 4401"""
    with client.websocket_connect(_url()) as websocket:
        websocket.send_text('not json at all')
        _assert_closed_unauthorized(websocket)


def test_first_frame_wrong_type(client):
    """Первый кадр с type != 'auth' → 4401"""
    with client.websocket_connect(_url()) as websocket:
        websocket.send_json({'type': 'hello', 'token': _VALID_TOKEN})
        _assert_closed_unauthorized(websocket)


def test_auth_frame_without_token(client):
    """auth-кадр без токена и без заголовка → 4401"""
    with client.websocket_connect(_url()) as websocket:
        websocket.send_json({'type': 'auth'})
        _assert_closed_unauthorized(websocket)


def test_invalid_token(client):
    """auth-кадр с неверным токеном → 4401"""
    with client.websocket_connect(_url()) as websocket:
        websocket.send_json({'type': 'auth', 'token': 'goga_wrong'})
        _assert_closed_unauthorized(websocket)


def test_valid_token_in_frame(client):
    """Валидный токен в кадре авторизует — приходит живой поток (маркерный кадр)"""
    with client.websocket_connect(_url()) as websocket:
        websocket.send_json({'type': 'auth', 'token': _VALID_TOKEN})
        assert websocket.receive_json() == {'type': 'ping'}


def test_valid_token_in_authorization_header(client):
    """Токен можно отдать заголовком Authorization (серверный прокси), кадр — без token"""
    headers = {'Authorization': f'Bearer {_VALID_TOKEN}'}
    with client.websocket_connect(_url(), headers=headers) as websocket:
        websocket.send_json({'type': 'auth'})
        assert websocket.receive_json() == {'type': 'ping'}


def test_after_id_taken_from_auth_frame(client):
    """after_id едет в auth-кадре и доходит до добора (а не из query)"""
    with client.websocket_connect(_url()) as websocket:
        websocket.send_json({'type': 'auth', 'token': _VALID_TOKEN, 'after_id': 77})
        assert websocket.receive_json() == {'type': 'backfill', 'after_id': 77}
        assert websocket.receive_json() == {'type': 'ping'}
