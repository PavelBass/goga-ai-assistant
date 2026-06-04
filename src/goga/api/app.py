"""Сборка приложения FastAPI

Приложение поднимается в одном event loop с поллингом aiogram (см.
goga.ui.telegram.aiogram.run). Авторизация — сервисным Bearer-токеном,
кроме эндпоинта проверки здоровья /api/v1/health.
"""

from importlib.metadata import version

from fastapi import FastAPI

from goga.api.routers import (
    daily,
    history,
    news,
    stream,
)

# Описание для OpenAPI (info.description) — Swagger рендерит его как Markdown и
# отдаёт в /api/v1/openapi.json. WebSocket-маршруты FastAPI в OpenAPI не включает,
# поэтому про ws-ленту и её авторизацию иначе из спеки не узнать — описываем здесь
# главное и ссылаемся на полный контракт.
_API_DESCRIPTION = """\
HTTP API Гоги для интеграции со средствами автоматизации и командным сайтом.

## Авторизация

Все эндпоинты, кроме `GET /api/v1/health`, требуют сервисный Bearer-токен
(`Authorization: Bearer goga_…`), выпущенный Гогой.

## Живая лента чата (WebSocket)

Кроме REST есть WebSocket-лента новых сообщений чата:
`WSS /api/v1/chats/{chat_id}/ws`.

WebSocket-маршруты не попадают в OpenAPI (в списке путей ниже его нет), поэтому
про авторизацию ленты — здесь. Токен **не** передаётся в URL: сразу после
открытия сокета клиент первым кадром шлёт
`{"type": "auth", "token": "goga_…", "after_id": <int?>}`. Серверный прокси может
вместо `token` в кадре передать заголовок `Authorization: Bearer`. Auth-кадр
ожидается не дольше 5 секунд; при его отсутствии, таймауте или неверном токене
соединение закрывается кодом **4401**. Полный контракт — в файле
`docs/chat-stream-ws.md` репозитория.
"""


def create_app() -> FastAPI:
    """Создаёт и настраивает экземпляр FastAPI"""
    try:
        app_version = version('goga')
    except Exception:
        app_version = '0'
    # Спека и доки лежат под /api/v1/, т.к. наружу через nginx проксируется
    # только этот префикс (корневые /openapi.json, /docs, /redoc недоступны).
    app = FastAPI(
        title='Goga API',
        version=app_version,
        description=_API_DESCRIPTION,
        openapi_url='/api/v1/openapi.json',
        docs_url='/api/v1/docs',
        redoc_url='/api/v1/redoc',
    )

    @app.get('/api/v1/health', tags=['service'])
    async def health() -> dict[str, str]:
        """Проверка доступности сервиса (без авторизации)"""
        return {'status': 'ok'}

    app.include_router(news.router)
    app.include_router(daily.router)
    app.include_router(history.router)
    app.include_router(stream.router)
    return app


app = create_app()
