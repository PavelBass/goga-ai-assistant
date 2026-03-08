#!/usr/bin/env python
"""Скрипт миграции dailydb.json: добавление Telegram username участникам дейли

Зачем нужен:
    В старом формате dailydb.json участники хранились как список имён:
        "participants": ["Павел", "Кирилл", "Лена"]

    В новом формате ключом стал Telegram username, а значением — имя:
        "participants": {"pbass": "Павел", "Kademn": "Кирилл", "lenok": "Лена"}

    Это позволяет упоминать ведущего дейли через @username в сообщении бота,
    чтобы Telegram отправлял уведомление выбранному участнику.

    Помимо participants скрипт обновляет очередь претендентов (state.pretendents),
    заменяя имена на соответствующие username.

Команды:
    migrate
        Интерактивная миграция. Для каждого участника из текущего dailydb.json
        скрипт запрашивает Telegram username. Перед изменением создаётся резервная
        копия dailydb-old-{ISO 8601 timestamp}.json рядом с оригиналом.
        Если БД уже в новом формате — миграция не выполняется.

        Пример:
            python scripts/migrate_dailydb.py migrate
            python scripts/migrate_dailydb.py --db /path/to/dailydb.json migrate

    restore <backup>
        Восстановление dailydb.json из указанной резервной копии.
        Перед копированием проверяет, что backup-файл содержит валидный JSON.

        Пример:
            python scripts/migrate_dailydb.py restore dailydb-old-2026-03-08T120000.json

Общий аргумент:
    --db    Путь к dailydb.json (по умолчанию: dailydb.json в текущей директории)
"""
import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


def _read_db(path: Path) -> dict:
    """Читает JSON-файл базы данных"""
    text = path.read_text(encoding='utf-8')
    return json.loads(text)


def _write_db(path: Path, data: dict) -> None:
    """Записывает JSON-файл базы данных"""
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def _make_backup_path(original: Path) -> Path:
    """Формирует путь для резервной копии с ISO 8601 меткой времени"""
    timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H%M%S')
    return original.parent / f'dailydb-old-{timestamp}.json'


def migrate(db_path: Path) -> None:
    """Миграция: запрашивает username для каждого участника и обновляет формат БД"""
    if not db_path.is_file():
        print(f'Файл {db_path} не найден')
        sys.exit(1)

    data = _read_db(db_path)
    participants = data.get('participants', [])

    if isinstance(participants, dict):
        print('База данных уже в новом формате (participants — словарь). Миграция не требуется.')
        sys.exit(0)

    if not isinstance(participants, list):
        print(f'Неожиданный формат participants: {type(participants).__name__}')
        sys.exit(1)

    # Резервная копия
    backup_path = _make_backup_path(db_path)
    shutil.copy2(db_path, backup_path)
    print(f'Резервная копия сохранена: {backup_path}')

    # Запрос username для каждого участника
    print()
    print('Введите Telegram username (без @) для каждого участника.')
    print('Этот username будет ключом в базе данных.')
    print()

    new_participants = {}
    name_to_username = {}
    for name in participants:
        while True:
            username = input(f'  {name} → @').strip()
            if not username:
                print('    Username не может быть пустым. Попробуйте ещё раз.')
                continue
            if username.startswith('@'):
                username = username[1:]
            if username in new_participants:
                print(f'    Username @{username} уже используется для "{new_participants[username]}". Попробуйте другой.')
                continue
            break
        new_participants[username] = name
        name_to_username[name] = username

    # Обновляем participants
    data['participants'] = new_participants

    # Обновляем очередь претендентов: имена → username
    state = data.get('state', {})
    old_pretendents = state.get('pretendents', [])
    new_pretendents = []
    for name in old_pretendents:
        username = name_to_username.get(name)
        if username:
            new_pretendents.append(username)
        else:
            print(f'  Предупреждение: участник "{name}" из очереди претендентов не найден среди участников, пропущен.')
    state['pretendents'] = new_pretendents
    data['state'] = state

    _write_db(db_path, data)
    print()
    print(f'Миграция завершена. Обновлённая БД: {db_path}')


def restore(db_path: Path, backup_path: Path) -> None:
    """Восстановление базы данных из резервной копии"""
    if not backup_path.is_file():
        print(f'Файл резервной копии {backup_path} не найден')
        sys.exit(1)

    # Проверяем, что backup — валидный JSON
    try:
        _read_db(backup_path)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f'Файл резервной копии повреждён: {e}')
        sys.exit(1)

    shutil.copy2(backup_path, db_path)
    print(f'База данных восстановлена из {backup_path} → {db_path}')


def main():
    """Точка входа"""
    parser = argparse.ArgumentParser(
        prog='migrate_dailydb',
        description='Миграция dailydb.json: добавление Telegram username участникам дейли',
    )
    parser.add_argument(
        '--db', type=Path, default='dailydb.json',
        help='Путь к dailydb.json (по умолчанию: dailydb.json)',
    )
    subparsers = parser.add_subparsers(dest='command')

    subparsers.add_parser('migrate', help='Мигрировать БД: добавить username участникам')

    restore_parser = subparsers.add_parser('restore', help='Восстановить БД из резервной копии')
    restore_parser.add_argument('backup', type=Path, help='Путь к файлу резервной копии (dailydb-old-*.json)')

    args = parser.parse_args()

    if args.command == 'migrate':
        migrate(args.db)
    elif args.command == 'restore':
        restore(args.db, args.backup)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
