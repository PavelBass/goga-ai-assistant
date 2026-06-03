"""CLI-интерфейсы Гоги: запуск бота (goga) и управление токенами (goga-token)"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from pydantic import BaseModel

from goga import config
from goga.config import initiate_config
from goga.gigachat.tools import get_or_create_repository
from goga.ui.telegram.aiogram.run import run_telegram_bot


class CLIArguments(BaseModel):
    """Аргументы командной строки

    Attributes:
        configuration: Путь к конфигурационному toml-файлу
    """

    configuration: Path


def get_arguments() -> CLIArguments:
    """Получение аргументов командной строки"""
    parser = argparse.ArgumentParser(prog='goga', description='CLI-интерфейс запуска Гоги')
    parser.add_argument('--configuration', type=Path, default='config.toml', help='Путь к конфигурационному toml-файлу')
    arugments = parser.parse_args()
    return CLIArguments(**vars(arugments))


def main():
    """Точка входа в CLI-приложение"""
    arguments = get_arguments()
    initiate_config(arguments.configuration)
    get_or_create_repository(config.CONFIG['db']['daily'])

    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(run_telegram_bot())


async def _create_token(name: str) -> None:
    """Выпускает токен и печатает его один раз

    Raises:
        SystemExit: если сервис с таким именем уже существует
    """
    from sqlalchemy.exc import IntegrityError

    from goga.api.tokens import create_token
    from goga.db.engine import session_scope

    try:
        async with session_scope() as session:
            record, token = await create_token(session, name)
    except IntegrityError:
        print(f'Ошибка: токен для сервиса «{name}» уже существует.', file=sys.stderr)
        raise SystemExit(1) from None
    print(f'Токен для сервиса «{name}» выпущен (id={record.id}).')
    print('Сохраните его — он показывается только один раз:')
    print(token)


async def _list_tokens() -> None:
    """Печатает все выпущенные токены"""
    from goga.api.tokens import list_tokens
    from goga.db.engine import session_scope

    async with session_scope() as session:
        tokens = await list_tokens(session)
    if not tokens:
        print('Токенов нет.')
        return
    for token in tokens:
        state = 'отозван' if token.revoked_at else 'активен'
        last_used = token.last_used_at.isoformat() if token.last_used_at else '—'
        print(f'{token.id}\t{token.name}\t{token.token_prefix}…\t{state}\tпоследнее использование: {last_used}')


async def _revoke_token(name: str) -> None:
    """Отзывает токен сервиса по имени"""
    from goga.api.tokens import revoke_token
    from goga.db.engine import session_scope

    async with session_scope() as session:
        revoked = await revoke_token(session, name)
    if revoked:
        print(f'Токен сервиса «{name}» отозван.')
    else:
        print(f'Активный токен сервиса «{name}» не найден.')


def token_main():
    """Точка входа CLI управления API-токенами (goga-token)

    Подкоманды:
        create <name>  — выпустить токен для сервиса (печатается один раз)
        list           — показать все токены
        revoke <name>  — отозвать токен сервиса
    """
    parser = argparse.ArgumentParser(prog='goga-token', description='Управление сервисными токенами HTTP API Гоги')
    subparsers = parser.add_subparsers(dest='command', required=True)

    create_parser = subparsers.add_parser('create', help='Выпустить токен для сервиса')
    create_parser.add_argument('name', help='Имя сервиса-потребителя')

    subparsers.add_parser('list', help='Показать все токены')

    revoke_parser = subparsers.add_parser('revoke', help='Отозвать токен сервиса')
    revoke_parser.add_argument('name', help='Имя сервиса-потребителя')

    arguments = parser.parse_args()
    if arguments.command == 'create':
        asyncio.run(_create_token(arguments.name))
    elif arguments.command == 'list':
        asyncio.run(_list_tokens())
    elif arguments.command == 'revoke':
        asyncio.run(_revoke_token(arguments.name))


if __name__ == '__main__':
    main()
