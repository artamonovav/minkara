#!/usr/bin/env bash
# Перевод архива: DeepL для объёмных текстов, Google для остального,
# затем DeepL исправляет неудачные сегменты Google.
#
# Запуск: bash scripts/translate_all.sh
# Лог:    work/translate.log
#
# Переменные:
#   MINKARA_DEEPL_MIN_CHARS=300   — с какой длины текст отдавать DeepL
#   MINKARA_TRANSLATE_API_KEY     — ключ DeepL (или в config/settings.local.env)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="$ROOT/.venv/bin/python"
LOG="$ROOT/work/translate.log"
MIN="${MINKARA_DEEPL_MIN_CHARS:-300}"
mkdir -p "$ROOT/work"

exec 9>"$ROOT/work/translate.lock"
if ! flock -n 9; then
  echo "Перевод уже запущен (work/translate.lock)."
  exit 1
fi

exec >>"$LOG" 2>&1
export PYTHONUNBUFFERED=1
say() { printf '\n=== %s | %s ===\n' "$(date -Is)" "$*"; }

say "START translate_all (DeepL >= ${MIN} символов, остальное Google)"
"$PY" scripts/03_translate.py --check-usage

say "1/4 синхронизация единиц из БД"
"$PY" scripts/03_translate.py --sync-only

say "2/4 DeepL: объёмные тексты"
"$PY" scripts/03_translate.py --provider deepl --min-chars "$MIN" \
  --report work/translation-deepl-long.md

say "3/4 Google: остальное"
"$PY" scripts/03_translate.py --provider google \
  --report work/translation-google.md

say "4/4 DeepL: исправление плохих сегментов Google"
"$PY" scripts/03_translate.py --fix-bad --fix-engine google \
  --report work/translation-fix-deepl.md

say "сборка сайта"
"$PY" scripts/04_build.py

say "DONE translate_all"
