"""Конфигурация приложения Goga"""
import tomllib
from pathlib import Path

# TODO: Переписать на pydantic. Статический контекст?
CONFIG = None

def initiate_config(config_path: Path | str):
    """Инициализация конфигурации приложения"""
    global CONFIG
    with open(config_path, 'rb') as f:
        CONFIG = tomllib.load(f)

__all__ = ['CONFIG']
