#!/usr/bin/bash
#
# Серверный деплой Гоги. Запускается НА сервере tw_fra — локально дёргается
# через remote-deploy.sh (ssh tw_fra -o RemoteCommand=...).
#
# Делает:
#   1. git pull свежего кода;
#   2. pip install -e . — зависимости в pyenv-окружение goga;
#   3. alembic upgrade head — миграции БД (Postgres локален на сервере, строка
#      DATABASE_URL берётся из .env относительно каталога проекта);
#   4. перезапуск Гоги (бот + HTTP API в одном процессе) под daemon --respawn.
#
# Предполагает выполненный одноразовый bootstrap:
#   - создано pyenv-окружение goga (pyenv virtualenv <py> goga);
#   - присутствует прод-файл .env (TELEGRAM_BOT_TOKEN, GIGACHAT_CREDENTIALS,
#     DATABASE_URL на локальный Postgres сервера);
#   - config.toml с mode='production' (он в git);
#   - поднят Postgres, БД из DATABASE_URL создана;
#   - у бота отключён Privacy Mode в BotFather (нужно для полной истории чата).
set -euo pipefail

PROJECT_DIR=/home/pbass/goga-ai-assistant
ENV_BIN=/home/pbass/.pyenv/versions/goga/bin
# HTTP API биндится на этот порт (см. [api].port в config.toml) — ждём его
# освобождения перед перезапуском, чтобы uvicorn не упал на занятом порту.
PORT=8080

cd "$PROJECT_DIR"

echo "[deploy] git pull"
git pull --ff-only

echo "[deploy] pip install -e ."
"$ENV_BIN/pip" install -e .

echo "[deploy] alembic upgrade head"
"$ENV_BIN/alembic" upgrade head

echo "[deploy] restart goga (daemon)"
daemon --name=goga --stop 2>/dev/null || true
sleep 1
# Подстраховка от бага daemon на этом VDS (см. harmonia/deploy.sh): иногда
# `daemon --list` теряет процесс, а супервизор daemon и/или сам Гога остаются в
# `ps` и держат порт API — тогда `--stop` ничего не делает. Добиваем по шаблону.
# Важно ещё и потому, что Telegram допускает лишь один поллинг getUpdates: два
# процесса Гоги конфликтуют. pkill-шаблоны не совпадают с самим deploy.sh.
pkill -f "daemon --name=goga" 2>/dev/null || true
pkill -f "\.pyenv/versions/goga/bin/goga --configuration" 2>/dev/null || true
for _ in $(seq 1 20); do
  ss -ltn 2>/dev/null | grep -q "127.0.0.1:$PORT\b" || break
  sleep 0.5
done
# --chdir обязателен: и config.toml, и .env читаются относительно cwd (goga ищет
# .env через find_dotenv от текущего каталога; иначе daemon уходит в cwd=/ и
# прод-настройки не подхватятся). --respawn перезапускает Гогу при падении.
# Пакет goga ставится editable (pip install -e .), поэтому запускаем по entrypoint.
daemon --name=goga --respawn --chdir="$PROJECT_DIR" \
  -o "$PROJECT_DIR/goga.log" -- \
  "$ENV_BIN/goga" --configuration config.toml

echo "[deploy] done — Гога перезапущен (бот + HTTP API на 127.0.0.1:$PORT)"
