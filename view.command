#!/usr/bin/env bash
# Открыть собранный офлайн-архив в браузере (macOS).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INDEX="$ROOT/out/site/index.html"
if [ ! -f "$INDEX" ]; then
  echo "Сайт ещё не собран. Запустите: python3 scripts/04_build.py"
  exit 1
fi
open "$INDEX"
