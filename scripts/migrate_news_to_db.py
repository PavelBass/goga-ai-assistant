#!/usr/bin/env python
"""Импорт файловых новостей (md) в PostgreSQL

Зачем нужен:
    Ранее новости хранились md-файлами в каталоге, а показанные перемещались в
    подкаталог ``seen/``. Этот скрипт переносит их в таблицу ``news``:
        - файлы из корня каталога  → статус Pending;
        - файлы из ``seen/``        → статус Shown (с заполнением shown_at).

    Имя файла вида ``ГГГГММДД Краткое название.md`` используется для определения
    даты публикации (source_date). Первая строка содержимого — заголовок
    (``# Заголовок``), остальное — анонс; ссылка извлекается из markdown-ссылки,
    если она присутствует в тексте.

Использование:
    DATABASE_URL=postgresql+asyncpg://... python scripts/migrate_news_to_db.py --news-dir ~/goga-news

Идемпотентность:
    Скрипт не отслеживает уже импортированные файлы. Запускать один раз на
    непустом каталоге; повторный запуск создаст дубли.
"""

import argparse
import asyncio
import datetime as dt
import re
from pathlib import Path

from goga.data.news import NewsRepository
from goga.db.engine import session_scope
from goga.db.models import NewsStatus

_DATE_PREFIX = re.compile(r'^(\d{8})\s')
_MARKDOWN_LINK = re.compile(r'\[[^\]]*\]\((https?://[^)]+)\)')


def _parse_filename_date(name: str) -> dt.date | None:
    """Извлекает дату ГГГГММДД из начала имени файла"""
    match = _DATE_PREFIX.match(name)
    if not match:
        return None
    try:
        return dt.datetime.strptime(match.group(1), '%Y%m%d').date()
    except ValueError:
        return None


def _parse_content(text: str) -> tuple[str, str, str | None]:
    """Разбирает md-новость на (заголовок, описание, ссылку)"""
    text = text.strip()
    first_line, _, rest = text.partition('\n')
    title = first_line.lstrip('# ').strip()
    description = rest.strip()
    url_match = _MARKDOWN_LINK.search(text)
    url = url_match.group(1) if url_match else None
    return title, description, url


async def _import_file(repository: NewsRepository, file: Path, status: NewsStatus) -> None:
    """Импортирует один md-файл в БД с заданным статусом"""
    title, description, url = _parse_content(file.read_text(encoding='utf-8'))
    shown_at = dt.datetime.now(dt.UTC) if status is NewsStatus.Shown else None
    news = await repository.add(
        title=title,
        description=description,
        url=url,
        source_date=_parse_filename_date(file.name),
        status=status,
        created_by='migrate_news_to_db',
    )
    if shown_at is not None:
        news.shown_at = shown_at


async def _migrate(news_dir: Path) -> None:
    """Переносит все md-файлы каталога (и seen/) в БД"""
    pending = sorted(f for f in news_dir.glob('*.md') if f.is_file())
    seen_dir = news_dir / 'seen'
    shown = sorted(f for f in seen_dir.glob('*.md') if f.is_file()) if seen_dir.is_dir() else []

    if not pending and not shown:
        print(f'В каталоге {news_dir} нет md-файлов новостей — импортировать нечего.')
        return

    async with session_scope() as session:
        repository = NewsRepository(session)
        for file in pending:
            await _import_file(repository, file, NewsStatus.Pending)
        for file in shown:
            await _import_file(repository, file, NewsStatus.Shown)

    print(f'Импортировано: {len(pending)} непоказанных, {len(shown)} показанных.')


def main() -> None:
    """Точка входа"""
    parser = argparse.ArgumentParser(
        prog='migrate_news_to_db',
        description='Импорт файловых новостей (md) в PostgreSQL',
    )
    parser.add_argument(
        '--news-dir', type=Path, required=True, help='Каталог с md-файлами новостей (с подкаталогом seen/)'
    )
    args = parser.parse_args()
    if not args.news_dir.is_dir():
        parser.error(f'Каталог не найден: {args.news_dir}')
    asyncio.run(_migrate(args.news_dir))


if __name__ == '__main__':
    main()
