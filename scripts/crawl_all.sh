#!/usr/bin/env bash
# Полная выкачка архива Honda Freed (все модели со словом freed).
#
# Запуск:   bash scripts/crawl_all.sh
# Фоном:    setsid nohup bash scripts/crawl_all.sh >/dev/null 2>&1 &
# Лог:      work/crawl.log
# Повторный запуск продолжает с места остановки (все этапы идемпотентны).
#
# Переменные:
#   MINKARA_MODELS="freed,freed_hybrid"   — ограничить модели
#   MINKARA_CRAWL_TRANSLATE=1             — перевести после выкачки (провайдер из env)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY="$ROOT/.venv/bin/python"
LOG="$ROOT/work/crawl.log"
mkdir -p "$ROOT/work"

# один экземпляр
exec 9>"$ROOT/work/crawl.lock"
if ! flock -n 9; then
  echo "Выкачка уже запущена (work/crawl.lock)."
  exit 1
fi

exec >>"$LOG" 2>&1
export PYTHONUNBUFFERED=1
say() { printf '\n=== %s | %s ===\n' "$(date -Is)" "$*"; }

say "START crawl_all"
"$PY" -V

MODELS_ARG=()
if [ -n "${MINKARA_MODELS:-}" ]; then
  MODELS_ARG=(--models "$MINKARA_MODELS")
else
  MODELS_ARG=(--match freed)
fi

# Параллельность: страницы — 4 потока при общем лимите ~3.3 запроса/с,
# медиа — 6 потоков при ~6.7 запроса/с (CDN терпит).
WORKERS="${MINKARA_WORKERS:-4}"
PAGE_DELAY="${MINKARA_DELAY:-0.3}"
ASSET_WORKERS="${MINKARA_ASSET_WORKERS:-6}"
ASSET_DELAY="${MINKARA_ASSET_DELAY:-0.15}"

DISCOVER_MARKER="$ROOT/work/discover.done"
if [ -f "$DISCOVER_MARKER" ] && [ "${MINKARA_REFRESH:-0}" != "1" ]; then
  say "1/7 discover пропущен: есть маркер $DISCOVER_MARKER"
  say "    (MINKARA_REFRESH=1 или удалить маркер — чтобы обойти листинги заново)"
else
  say "1/7 discover (note, partsreview, review)"
  "$PY" scripts/01_discover.py --brand honda "${MODELS_ARG[@]}" \
    --sections note,partsreview,review
  touch "$DISCOVER_MARKER"
  say "discover завершён, маркер создан"
fi

say "2/7 fetch: машины + заметки (workers=${WORKERS}, delay=${PAGE_DELAY})"
"$PY" scripts/02_fetch.py --kind note --no-assets \
  --workers "$WORKERS" --delay "$PAGE_DELAY"

say "3/7 fetch: товары (регистрируют отзывы)"
"$PY" scripts/02_fetch.py --kind product --no-assets \
  --workers "$WORKERS" --delay "$PAGE_DELAY"

say "4/7 fetch: отзывы о запчастях и об авто"
"$PY" scripts/02_fetch.py --kind parts,review --no-assets \
  --workers "$WORKERS" --delay "$PAGE_DELAY"

say "5/7 медиа (workers=${ASSET_WORKERS}, delay=${ASSET_DELAY})"
"$PY" scripts/02_fetch.py --only-assets \
  --asset-workers "$ASSET_WORKERS" --asset-delay "$ASSET_DELAY"

if [ "${MINKARA_CRAWL_TRANSLATE:-0}" = "1" ]; then
  say "6/7 перевод"
  "$PY" scripts/03_translate.py
else
  say "6/7 перевод пропущен (MINKARA_CRAWL_TRANSLATE=1 чтобы включить)"
fi

say "7/7 сборка сайта"
"$PY" scripts/04_build.py

say "DONE crawl_all"
