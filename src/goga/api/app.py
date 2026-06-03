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
        description='HTTP API Гоги для интеграции со средствами автоматизации и командным сайтом',
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
