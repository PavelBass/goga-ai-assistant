"""Управление новостями для ежедневных сообщений (хранилище — PostgreSQL)

Новости больше не удаляются при показе, а помечаются статусом
``NewsStatus.Shown`` с заполнением ``shown_at``. Поля ``scheduled_for`` и
``position`` позволяют формировать план показа на ближайшие дни и порядок
новостей в пределах одного дня.

Репозиторий работает поверх переданной асинхронной сессии и НЕ выполняет
commit самостоятельно — управление транзакцией остаётся за вызывающей стороной
(``session_scope`` или FastAPI-зависимостью ``get_session``).
"""

import datetime as dt
from collections.abc import Sequence

from sqlalchemy import (
    select,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession

from goga.db.models import (
    News,
    NewsStatus,
)

# Поля News, которые разрешено менять через update()
_UPDATABLE_FIELDS = frozenset({'title', 'description', 'url', 'source_date', 'status', 'scheduled_for', 'position'})


class NewsRepository:
    """Репозиторий новостей поверх асинхронной сессии SQLAlchemy

    Attributes:
        session: асинхронная сессия, в рамках которой выполняются операции
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        title: str,
        description: str = '',
        url: str | None = None,
        source_date: dt.date | None = None,
        scheduled_for: dt.date | None = None,
        position: int | None = None,
        status: NewsStatus | None = None,
        created_by: str | None = None,
    ) -> News:
        """Добавляет новость

        Если статус не задан явно, он выбирается по наличию даты показа:
        ``Scheduled`` при заданном ``scheduled_for``, иначе ``Pending``.

        Args:
            title: заголовок новости
            description: краткий анонс (тело новости)
            url: ссылка на оригинальную статью
            source_date: дата публикации оригинала
            scheduled_for: день, на который запланирован показ
            position: порядок показа в пределах дня
            status: явный статус показа (переопределяет автоматический выбор)
            created_by: источник добавления (telegram username или имя сервиса)

        Returns:
            созданная новость с заполненным id

        Raises:
            sqlalchemy.exc.SQLAlchemyError: при ошибке записи в БД
        """
        if status is None:
            status = NewsStatus.Scheduled if scheduled_for else NewsStatus.Pending
        news = News(
            title=title,
            description=description,
            url=url,
            source_date=source_date,
            scheduled_for=scheduled_for,
            position=position,
            status=status,
            created_by=created_by,
        )
        self._session.add(news)
        await self._session.flush()
        return news

    async def get(self, news_id: int) -> News | None:
        """Возвращает новость по id или None, если не найдена

        Args:
            news_id: идентификатор новости

        Raises:
            sqlalchemy.exc.SQLAlchemyError: при ошибке чтения из БД
        """
        return await self._session.get(News, news_id)

    async def list(
        self,
        *,
        status: NewsStatus | None = None,
        scheduled_for: dt.date | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[News]:
        """Возвращает список новостей с фильтрами и пагинацией

        Сортировка: по дате показа, затем по позиции, затем по дате источника
        и id (новости без даты/позиции — в конце).

        Args:
            status: фильтр по статусу показа
            scheduled_for: фильтр по дню запланированного показа
            limit: максимум записей в выдаче
            offset: смещение для пагинации

        Raises:
            sqlalchemy.exc.SQLAlchemyError: при ошибке чтения из БД
        """
        query = select(News)
        if status is not None:
            query = query.where(News.status == status)
        if scheduled_for is not None:
            query = query.where(News.scheduled_for == scheduled_for)
        query = (
            query.order_by(
                News.scheduled_for.asc().nullslast(),
                News.position.asc().nullslast(),
                News.source_date.asc().nullslast(),
                News.id.asc(),
            )
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(query)
        return result.scalars().all()

    async def update(self, news_id: int, **fields) -> News | None:
        """Обновляет разрешённые поля новости

        Args:
            news_id: идентификатор новости
            **fields: пары поле=значение; допустимы только поля из
                _UPDATABLE_FIELDS (title, description, url, source_date,
                status, scheduled_for, position)

        Returns:
            обновлённая новость или None, если новость не найдена

        Raises:
            ValueError: если передано недопустимое для обновления поле
            sqlalchemy.exc.SQLAlchemyError: при ошибке записи в БД
        """
        unknown = set(fields) - _UPDATABLE_FIELDS
        if unknown:
            raise ValueError(f'Недопустимые поля для обновления: {sorted(unknown)}')
        news = await self._session.get(News, news_id)
        if news is None:
            return None
        for field, value in fields.items():
            setattr(news, field, value)
        await self._session.flush()
        return news

    async def delete(self, news_id: int) -> bool:
        """Физически удаляет новость (админская очистка)

        Обычный сценарий «скрыть новость» — пометка показанной (mark_shown),
        запись при этом сохраняется.

        Args:
            news_id: идентификатор новости

        Returns:
            True, если новость была найдена и удалена, иначе False

        Raises:
            sqlalchemy.exc.SQLAlchemyError: при ошибке записи в БД
        """
        news = await self._session.get(News, news_id)
        if news is None:
            return False
        await self._session.delete(news)
        await self._session.flush()
        return True

    async def due_for_today(self, limit: int, today: dt.date | None = None) -> Sequence[News]:
        """Возвращает новости, готовые к показу сегодня

        Берутся непоказанные новости (Pending/Scheduled) без даты показа или с
        датой не позже сегодняшней, в порядке плана показа.

        Args:
            limit: максимум новостей к показу
            today: день, относительно которого считается «сегодня»
                (по умолчанию — текущая дата)

        Raises:
            sqlalchemy.exc.SQLAlchemyError: при ошибке чтения из БД
        """
        if today is None:
            today = dt.date.today()
        query = (
            select(News)
            .where(
                News.status.in_((NewsStatus.Pending, NewsStatus.Scheduled)),
                (News.scheduled_for.is_(None)) | (News.scheduled_for <= today),
            )
            .order_by(
                News.scheduled_for.asc().nullslast(),
                News.position.asc().nullslast(),
                News.source_date.asc().nullslast(),
                News.id.asc(),
            )
            .limit(limit)
        )
        result = await self._session.execute(query)
        return result.scalars().all()

    async def mark_shown(self, ids: Sequence[int]) -> int:
        """Помечает новости показанными (status=Shown, shown_at=now)

        Идемпотентно: уже показанные новости повторно не трогаются.

        Args:
            ids: идентификаторы новостей

        Returns:
            количество новостей, фактически помеченных показанными

        Raises:
            sqlalchemy.exc.SQLAlchemyError: при ошибке записи в БД
        """
        if not ids:
            return 0
        result = await self._session.execute(
            update(News)
            .where(News.id.in_(ids), News.shown_at.is_(None))
            .values(status=NewsStatus.Shown, shown_at=dt.datetime.now(dt.UTC))
        )
        await self._session.flush()
        return result.rowcount or 0
