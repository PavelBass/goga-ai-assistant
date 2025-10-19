import argparse
import asyncio
import logging
import sys
from pathlib import Path

from pydantic import BaseModel

from goga import config
from goga.config import initiate_config
from goga.gigachat.tools import get_or_create_repository
from goga.ui.telegram.aiogram import run


class CLIArguments(BaseModel):
    """Аргументы командной строки
    
    Attributes:
        configuration: Путь к конфигурационному toml-файлу
    """
    configuration: Path

def get_arguments() -> CLIArguments:
    """Получение аргументов командной строки"""
    parser = argparse.ArgumentParser(prog='goga', description='CLI-интерфейс запуска Гоги')
    parser.add_argument(
        '--configuration', type=Path, default='config.toml', help='Путь к конфигурационному toml-файлу'
    )
    arugments = parser.parse_args()
    return CLIArguments(**vars(arugments))

def main():
    """Точка входа в CLI-приложение"""
    arguments = get_arguments()
    initiate_config(arguments.configuration)
    get_or_create_repository(config.CONFIG['db']['daily'])

    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(run())

if __name__ == '__main__':
    main()

