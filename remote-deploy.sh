#!/usr/bin/bash
#
# Локальный запуск деплоя Гоги на сервер tw_fra одной командой.
#
# Делает:
#   1. коммитит изменения, если они есть, и пушит в origin;
#   2. на сервере подтягивает код и запускает deploy.sh.
#
# Запускаем deploy.sh прямой ssh-командой (не через -o RemoteCommand): при
# RemoteCommand daemon не переживал закрытие сессии и Гога не поднимался.
# git pull делаем ДО запуска, чтобы исполнялась свежая версия самого deploy.sh.
#
# Если предпочитаешь коммитить вручную — закоммить/запушь сам и запусти только:
#   ssh tw_fra 'cd goga-ai-assistant && git pull --ff-only && ./deploy.sh'
set -euo pipefail

cd "$(dirname "$0")"

if [ -n "$(git status --porcelain)" ]; then
  echo "[remote-deploy] commit changes"
  git add -A
  git commit -m "deploy: sync"
fi

echo "[remote-deploy] push"
git push

echo "[remote-deploy] run deploy.sh on tw_fra"
ssh tw_fra 'cd goga-ai-assistant && git pull --ff-only && ./deploy.sh'
