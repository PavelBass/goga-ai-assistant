#!/usr/bin/bash
#
# Серверный деплой Гоги. Запускается НА сервере tw_fra — локально дёргается
# через remote-deploy.sh (ssh tw_fra '… && ./deploy.sh').
#
# Делает:
#   1. git pull свежего кода;
#   2. pip install -e . — зависимости в pyenv-окружение goga;
#   3. alembic upgrade head — миграции БД (Postgres локален на сервере, строка
#      DATABASE_URL берётся из .env по расположению пакета через find_dotenv);
#   4. перезапуск Гоги (бот + HTTP API в одном процессе) под daemon с --respawn
#      (поднимает Гогу обратно при падении/внешнем SIGTERM) — метод запуска
#      совпадает с проверенным ~/run_goga.sh (лог в $LOG, конфиг $CONFIG).
#
# Предполагает выполненный одноразовый bootstrap:
#   - создано pyenv-окружение goga (pyenv virtualenv <py> goga);
#   - в каталоге проекта присутствует прод-файл .env (TELEGRAM_BOT_TOKEN,
#     GIGACHAT_CREDENTIALS, DATABASE_URL на локальный Postgres сервера);
#     goga находит его через find_dotenv (по расположению пакета, не по cwd);
#   - прод-config.toml лежит по пути $CONFIG (вне git, mode='production');
#   - поднят Postgres, БД из DATABASE_URL создана;
#   - у бота отключён Privacy Mode в BotFather (нужно для полной истории чата).
set -euo pipefail

PROJECT_DIR=/home/pbass/goga-ai-assistant
ENV_BIN=/home/pbass/.pyenv/versions/goga/bin
# Прод-конфиг лежит вне репозитория (config.toml в .gitignore) — абсолютный путь.
CONFIG=/home/pbass/config.toml
# Лог Гоги — как в ~/run_goga.sh (вывод бота/uvicorn пишется сюда через daemon -o).
LOG=/home/pbass/goga.log
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

echo "[deploy] stop goga"
daemon --name=goga --stop 2>/dev/null || true
# Ждём, пока супервизор daemon полностью остановится и освободит имя goga.
# Критично для --respawn-рестарта: daemon гарантирует единственный именованный
# инстанс, поэтому новый старт молча не поднимется, пока имя занято ещё не до
# конца остановленным супервизором (его клиент гасится gracefully несколько
# секунд). Прежний sleep 1 этот гон не закрывал — ждём по факту состояния.
for _ in $(seq 1 40); do
  daemon --name=goga --running 2>/dev/null || break
  sleep 0.5
done
# Подстраховка: если --stop не сработал (потерянный pidfile), добиваем сам Гогу
# по шаблону. Строго ПОСЛЕ остановки супервизора — иначе --respawn тут же поднял
# бы клиента обратно. Важно ещё и потому, что Telegram допускает лишь один поллинг
# getUpdates — два процесса Гоги конфликтуют. Шаблон не совпадает с deploy.sh.
pkill -f "bin/goga --configuration" 2>/dev/null || true
# Ждём освобождения порта API, чтобы uvicorn не упал на занятом порту.
for _ in $(seq 1 20); do
  ss -ltn 2>/dev/null | grep -q "127.0.0.1:$PORT\b" || break
  sleep 0.5
done
echo "[deploy] start goga (метод как в ~/run_goga.sh, с --respawn)"
# Метод запуска взят из проверенного ~/run_goga.sh: daemon с логом в $LOG и
# абсолютным путём к конфигу. .env goga находит через find_dotenv (по
# расположению пакета), config.toml вне репозитория — отсюда абсолютный $CONFIG.
# --respawn: daemon перезапускает Гогу, если процесс упал или получил внешний
# SIGTERM (без него любой выход оставлял бота лежать). Корректный стоп при
# деплое обеспечивает `daemon --stop` выше — он гасит и супервизор, и клиента,
# поэтому respawn при перезапуске не срабатывает.
/usr/bin/daemon --name=goga --respawn -o "$LOG" -- "$ENV_BIN/goga" --configuration "$CONFIG"

echo "[deploy] done — Гога перезапущен (бот + HTTP API на 127.0.0.1:$PORT), лог: $LOG"
