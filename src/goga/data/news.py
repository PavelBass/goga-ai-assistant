"""Управление новостями для ежедневных сообщений"""
import re
import shutil
from pathlib import Path


class NewsRepository:
    """Репозиторий новостей из md-файлов

    Новости хранятся в директории в виде md-файлов. Имя файла начинается
    с даты в формате ГГГГММДД, например: "20260305 OpenAI выпустили GPT-5.4.md".
    После показа новости перемещаются в поддиректорию "seen".
    """

    def __init__(self, news_dir: str | Path) -> None:
        self._dir = Path(news_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._seen_dir = self._dir / 'seen'

    def _list_news_files(self) -> list[Path]:
        """Возвращает md-файлы новостей, отсортированные по дате (старые первыми)"""
        files = [f for f in self._dir.glob('*.md') if re.match(r'^\d{8}\s', f.name)]
        files.sort(key=lambda f: f.name)
        return files

    def get_news(self, limit: int = 7) -> list[str]:
        """Возвращает содержимое до limit новостей (старые первыми)"""
        files = self._list_news_files()[:limit]
        news = []
        for file in files:
            news.append(file.read_text(encoding='utf-8').strip())
        return news

    def mark_as_seen(self, limit: int = 7) -> None:
        """Перемещает показанные новости в поддиректорию seen"""
        files = self._list_news_files()[:limit]
        if not files:
            return
        self._seen_dir.mkdir(parents=True, exist_ok=True)
        for file in files:
            shutil.move(str(file), str(self._seen_dir / file.name))
