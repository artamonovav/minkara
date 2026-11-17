#!/usr/bin/env bash
# Открыть собранный офлайн-архив в браузере (Linux).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INDEX="$ROOT/out/site/index.html"
if [ ! -f "$INDEX" ]; then
  echo "Сайт ещё не собран. Запустите: python3 scripts/04_build.py"
  exit 1
fi
if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$INDEX"
elif command -v open >/dev/null 2>&1; then
  open "$INDEX"
else
  echo "Откройте вручную: $INDEX"
fi
