"""Сборка приложения FastAPI

Приложение поднимается в одном event loop с поллингом aiogram (см.
goga.ui.telegram.aiogram.run). Авторизация — сервисным Bearer-токеном,
кроме эндпоинта проверки здоровья /health.
"""

from importlib.metadata import version

from fastapi import FastAPI

from goga.api.routers import (
    daily,
    news,
)


def create_app() -> FastAPI:
    """Создаёт и настраивает экземпляр FastAPI"""
    try:
        app_version = version('goga')
    except Exception:
        app_version = '0'
    app = FastAPI(
        title='Goga API',
        version=app_version,
        description='HTTP API Гоги для интеграции со средствами автоматизации и командным сайтом',
    )

    @app.get('/health', tags=['service'])
    async def health() -> dict[str, str]:
        """Проверка доступности сервиса (без авторизации)"""
        return {'status': 'ok'}

    app.include_router(news.router)
    app.include_router(daily.router)
    return app


app = create_app()
