#!/usr/bin/env bash
# Установка окружения и настройка MCP для OpenCode.
# Запуск: bash scripts/setup.sh
# Рут не нужен; если чего-то не хватает (например, jq) — скрипт подскажет команду.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

say()  { printf '\n\033[1m%s\033[0m\n' "$*"; }
warn() { printf '\033[33m! %s\033[0m\n' "$*"; }

# ---------------------------------------------------------------- uv
if ! command -v uv >/dev/null 2>&1; then
  say "Ставлю uv (в ~/.local/bin, без root)"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
else
  say "uv уже установлен: $(uv --version)"
fi

# ---------------------------------------------------------------- venv + deps
say "Создаю .venv и ставлю зависимости"
uv venv .venv
uv pip install --python .venv/bin/python -r requirements.txt -r requirements-dev.txt

# ---------------------------------------------------------------- tools
say "Ставлю инструменты (ruff, pytest, sqlite-utils) в .venv"
uv pip install --python .venv/bin/python ruff pytest sqlite-utils

# ---------------------------------------------------------------- jq
if ! command -v jq >/dev/null 2>&1; then
  warn "jq не найден (нужен только для ручной отладки JSON)."
  case "$(uname -s)" in
    Darwin) echo "    Установка: brew install jq" ;;
    Linux)  echo "    Установка: sudo apt install jq   (нужен root)" ;;
    *)      echo "    Установите jq вручную: https://jqlang.github.io/jq/" ;;
  esac
fi

# ---------------------------------------------------------------- env
if [ ! -f config/settings.local.env ]; then
  cp config/settings.example.env config/settings.local.env
  say "Создан config/settings.local.env (можно поправить)"
fi

# ---------------------------------------------------------------- mcp
say "Настраиваю MCP-серверы в opencode.json"
python3 scripts/setup_mcp.py

# ---------------------------------------------------------------- network
say "Проверяю доступ к minkara"
code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 https://minkara.carview.co.jp/ || true)"
if [ "$code" = "200" ]; then
  echo "  доступ есть (200)"
elif [ "$code" = "403" ]; then
  warn "403: включите VPN/прокси с выходом за пределы РФ"
else
  warn "неожиданный код: ${code:-нет ответа}"
fi

say "Готово. Дальше:"
cat <<'EOF'
  . .venv/bin/activate
  python scripts/01_discover.py --brand honda --models freed,freed_hybrid
  python scripts/02_fetch.py --limit 20
  python scripts/04_build.py
  ./view.sh
EOF
