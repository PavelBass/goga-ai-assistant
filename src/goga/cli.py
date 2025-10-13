import argparse
import asyncio
import logging
import sys
from pathlib import Path

from pydantic import BaseModel

from goga.config import initiate_config
from goga.gigachat.tools import get_or_create_repository
from goga.ui.telegram.aiogram import run


class CLIArguments(BaseModel):
    """Аргументы командной строки
    
    Attributes:
        daily_db_json: Путь к JSON-файлу данных Daily Standup
        configuration: Путь к конфигурационному toml-файлу
    """
    daily_db_json: Path
    configuration: Path

def get_arguments() -> CLIArguments:
    """Получение аргументов командной строки"""
    parser = argparse.ArgumentParser(prog='goga', description='CLI-интерфейс запуска Гоги')
    parser.add_argument(
        '--daily-db-json', type=Path, default='dailydb.json', help='Путь к JSON-файлу данных Daily Standup'
    )
    parser.add_argument(
        '--configuration', type=Path, default='config.toml', help='Путь к конфигурационному toml-файлу'
    )
    arugments = parser.parse_args()
    return CLIArguments(**vars(arugments))

def main():
    """Точка входа в CLI-приложение"""
    arguments = get_arguments()
    get_or_create_repository(arguments.daily_db_json)
    initiate_config(arguments.configuration)

    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(run())

if __name__ == '__main__':
    main()

