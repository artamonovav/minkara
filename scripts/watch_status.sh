#!/usr/bin/env bash
# Пишет краткий статус в work/status.log каждые 10 минут.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
LOG="$ROOT/work/status.log"
LOCK="$ROOT/work/status.lock"

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "watch_status уже запущен"
  exit 1
fi

while true; do
  {
    echo "=== $(date -Is)"
    "$ROOT/.venv/bin/python" "$ROOT/scripts/status.py" | head -12
    echo
  } >>"$LOG"
  sleep 600
done
