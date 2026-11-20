#!/usr/bin/env bash
# Открыть собранный офлайн-архив в браузере (Linux).
# Работает и из репозитория, и из корня смонтированного ISO.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$ROOT/out/site/index.html" ]; then
  INDEX="$ROOT/out/site/index.html"
else
  INDEX="$ROOT/index.html"
fi
if [ ! -f "$INDEX" ]; then
  echo "Сайт не найден. Соберите: python3 scripts/04_build.py"
  exit 1
fi
if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$INDEX"
elif command -v open >/dev/null 2>&1; then
  open "$INDEX"
else
  echo "Откройте вручную: $INDEX"
fi
