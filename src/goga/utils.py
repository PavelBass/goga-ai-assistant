from pathlib import Path


def get_project_root() -> Path:
    """Путь до корневого каталога проекта"""
    return Path(__file__).parent.parent

def get_data_directory() -> Path:
    """Путь до каталога с данными"""
    return get_project_root() / 'data'


def get_images_directory() -> Path:
    """Путь до каталога с изображениями"""
    return get_data_directory() / 'images'

