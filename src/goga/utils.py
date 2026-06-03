from pathlib import Path


def get_project_root() -> Path:
    """Путь до корневого каталога проекта"""
    return Path(__file__).parent.parent.parent.absolute()


def get_data_directory() -> Path:
    """Путь до каталога с данными"""
    return get_project_root() / 'data/'


def get_images_directory() -> Path:
    """Путь до каталога с изображениями"""
    return get_data_directory() / 'images/'


def get_media_directory() -> Path:
    """Путь до каталога со скачанными медиа из истории чата

    Создаёт каталог, если он ещё не существует.

    Raises:
        OSError: если каталог не удаётся создать
    """
    directory = get_data_directory() / 'media/'
    directory.mkdir(parents=True, exist_ok=True)
    return directory
