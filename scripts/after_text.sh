#!/usr/bin/env bash
# Ждёт завершения текстовых стадий выкачки (3/7 и 4/7) и запускает перевод,
# не дожидаясь скачивания медиа (5/7). Медиа и перевод работают параллельно.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
LOG="$ROOT/work/crawl.log"
LOCK="$ROOT/work/after_text.lock"

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "after_text уже запущен"
  exit 1
fi

echo "[$(date -Is)] ждём текстовые стадии (5/7 медиа или DONE)"
deadline=$((SECONDS + 24 * 3600))
while (( SECONDS < deadline )); do
  last="$(grep -E '^=== ' "$LOG" | tail -1 || true)"
  case "$last" in
    *"5/7 медиа"*|*"DONE crawl_all"*) break ;;
  esac
  sleep 60
done

if ! grep -qE '5/7 медиа|DONE crawl_all' <<< "${last:-}"; then
  echo "[$(date -Is)] таймаут ожидания текстовых стадий"
  exit 1
fi

echo "[$(date -Is)] текстовые стадии завершены, запускаю перевод"
MINKARA_DEEPL_MIN_CHARS="${MINKARA_DEEPL_MIN_CHARS:-500}" \
  bash scripts/translate_all.sh
echo "[$(date -Is)] перевод завершён"
