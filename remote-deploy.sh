#!/usr/bin/bash
#
# Локальный запуск деплоя Гоги на сервер tw_fra одной командой.
#
# Делает:
#   1. коммитит изменения, если они есть, и пушит в origin;
#   2. дёргает серверный deploy.sh через ssh RemoteCommand.
#
# Если предпочитаешь коммитить вручную — закоммить/запушь сам и запусти только
# последний шаг: ssh tw_fra -o RemoteCommand='goga-ai-assistant/deploy.sh'
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
ssh tw_fra -o RemoteCommand='goga-ai-assistant/deploy.sh'
