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

    _FILE_PATTERN = re.compile(r'^(\d{8})\s')

    def __init__(self, news_dir: str | Path) -> None:
        self._dir = Path(news_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._seen_dir = self._dir / 'seen'

    def _list_news_files(self) -> list[Path]:
        """Возвращает md-файлы новостей, отсортированные по дате (старые первыми)"""
        files = [f for f in self._dir.glob('*.md') if self._FILE_PATTERN.match(f.name)]
        files.sort(key=lambda f: f.name)
        return files

    def get_news(self, limit: int = 7) -> list[str]:
        """Возвращает содержимое до limit новостей (старые первыми)"""
        files = self._list_news_files()[:limit]
        news = []
        for file in files:
            news.append(file.read_text(encoding='utf-8').strip())
        return news

    def get_news_list(self) -> list[tuple[int, str, str]]:
        """Возвращает пронумерованный список всех новостей: (номер, имя файла, содержимое)

        Новости группируются по датам показа (по 7 штук). Нумерация сквозная.
        """
        files = self._list_news_files()
        result = []
        for i, file in enumerate(files, 1):
            content = file.read_text(encoding='utf-8').strip()
            result.append((i, file.name, content))
        return result

    def add_news(self, filename: str, content: str) -> Path:
        """Добавляет новость в директорию

        Args:
            filename: имя файла (например "20260305 OpenAI выпустили GPT-5.4.md")
            content: содержимое файла новости

        Returns:
            путь к созданному файлу
        """
        file_path = self._dir / filename
        file_path.write_text(content, encoding='utf-8')
        return file_path

    def delete_news(self, index: int) -> str | None:
        """Удаляет новость по номеру в списке (нумерация с 1)

        Returns:
            имя удалённого файла или None, если номер невалидный
        """
        files = self._list_news_files()
        if index < 1 or index > len(files):
            return None
        file = files[index - 1]
        name = file.name
        file.unlink()
        return name

    def mark_as_seen(self, limit: int = 7) -> None:
        """Перемещает показанные новости в поддиректорию seen"""
        files = self._list_news_files()[:limit]
        if not files:
            return
        self._seen_dir.mkdir(parents=True, exist_ok=True)
        for file in files:
            shutil.move(str(file), str(self._seen_dir / file.name))
