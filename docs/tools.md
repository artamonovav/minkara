# Инструменты и MCP

Список того, что предлагается поставить для работы над архивом. Разделён на
«нужно сейчас», «понадобится позже» и «не нужно / отклонено».

---

## 1. Нужно сейчас (минимальный набор)

### uv — окружение и зависимости

Быстрый менеджер Python-проектов: сам создаёт venv, ставит зависимости,
фиксирует версии, умеет запускать скрипты и инструменты (`uv run`, `uvx`).
Кроссплатформенный.

```bash
# Linux / macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Зачем: воспроизводимое окружение, `uv run scripts/01_discover.py`,
`uvx` для MCP-серверов без глобальной установки.

### ruff — линтер и форматтер

```bash
uv tool install ruff
# или как dev-зависимость проекта:
uv add --dev ruff
```

Зачем: единый стиль, раннее ловит ошибки (неиспользуемые импорты, баги в
f-строках), быстрый.

### pytest — тесты парсеров

```bash
uv add --dev pytest
```

Зачем: вёрстка minkara меняется; тесты на сохранённых фикстурах позволяют
править парсеры без походов в сеть.

### sqlite-utils (или sqlite3 CLI)

```bash
uv tool install sqlite-utils
# либо системный пакет: apt install sqlite3
```

Зачем: смотреть состояние БД, строить быстрые отчёты
(`sqlite-utils rows data/archive.sqlite pages --csv`), не писать скрипты
ради каждого запроса.

### jq

```bash
apt install jq        # Debian/Ubuntu
brew install jq       # macOS
```

Зачем: разбор JSON-ответов API перевода и отладочных выгрузок.

---

## 2. MCP-серверы

MCP подключается в конфиг OpenCode (`opencode.json` в корне проекта или
глобальный). Ниже — рекомендуемый минимум.

### sqlite — главный

Даёт агенту прямой доступ к `data/archive.sqlite`: схема, выборки, отчёты.

```json
{
  "mcp": {
    "sqlite": {
      "type": "local",
      "command": ["uvx", "mcp-server-sqlite", "--db-path", "data/archive.sqlite"],
      "enabled": true
    }
  }
}
```

Зачем: на этапе разработки быстро отвечать на вопросы «сколько заметок
скачано», «какие поколения не определились», «сколько текстов без перевода».

### fetch — проверка страниц

```json
{
  "mcp": {
    "fetch": {
      "type": "local",
      "command": ["uvx", "mcp-server-fetch"],
      "enabled": true
    }
  }
}
```

Зачем: точечно смотреть страницы/редиректы, не добавляя одноразовые curl.

### filesystem — доступ к данным и результату

```json
{
  "mcp": {
    "filesystem": {
      "type": "local",
      "command": ["npx", "-y", "@modelcontextprotocol/server-filesystem",
                  "/home/anatoly/prj/minkara"],
      "enabled": true
    }
  }
}
```

Зачем: агенту нужен доступ к `data/` и `out/` (вне git, но в проекте).

### git — история и коммиты

```json
{
  "mcp": {
    "git": {
      "type": "local",
      "command": ["uvx", "mcp-server-git", "--repository",
                  "/home/anatoly/prj/minkara"],
      "enabled": true
    }
  }
}
```

Зачем: осмысленные коммиты по этапам, просмотр диффов.

---

## 3. Понадобится позже

### Ollama — локальный перевод (опционально)

Если решим переводить локально, без API и оплаты.

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:14b-instruct   # или gemma3:12b, mistral-nemo
```

Требования: 16+ ГБ RAM (14B в Q4), лучше GPU. Плюсы: офлайн, бесплатно,
данные не уходят. Минусы: качество и скорость ниже топовых API; японский
технический текст требует аккуратного промпта и глоссария.

Альтернатива — любой OpenAI-совместимый API (см. `MINKARA_TRANSLATE_*`).

### ImageMagick — миниатюры и нормализация фото

```bash
apt install imagemagick
```

Зачем: если понадобятся превью для каталога или пережатие больших фото.

### Playwright MCP — только если появится JS-рендеринг

```json
{
  "mcp": {
    "playwright": {
      "type": "local",
      "command": ["npx", "@playwright/mcp@latest"],
      "enabled": false
    }
  }
}
```

Сейчас **не нужен**: страницы minkara отдаются серверным HTML, контент
доступен без исполнения JS. Держим как резерв, если сайт переедет на
клиентский рендеринг.

---

## 4. Что отклонено и почему

| Инструмент | Почему нет |
|---|---|
| `wget --mirror` / `httrack` | тянут весь сайт, ломают структуру, не умеют ждать `?pn=` и фильтровать по поколению; нет БД и инкрементальности |
| `monolith` / SingleFile | годятся для разовой страницы, но не для 2000+ с переводами и поиском |
| Electron/Tauri-приложение | требует сборки/установки под каждую ОС; статический сайт решает задачу без софта |
| Отдельный сервер (Flask/FastAPI) как обязательный | лишняя зависимость; оставляем опциональный `serve.py` на stdlib |

---

## 5. Проверка окружения

```bash
uv --version
ruff --version
pytest --version
sqlite-utils --version
jq --version
```

Если чего-то нет — команды установки выше. Проект должен запускаться и без
`uv` (системный Python 3.12 + `pip install -r requirements.txt`), но с `uv`
воспроизводимее.
