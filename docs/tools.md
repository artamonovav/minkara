# Инструменты и MCP

Что установлено/предлагается для работы над архивом. Установка
автоматизирована: `bash scripts/setup.sh` (рут не нужен; если чего-то не
хватает — скрипт подскажет команду).

---

## 1. Уже ставится скриптом setup.sh

| Инструмент | Зачем |
|---|---|
| `uv` | окружение, `uv run`, `uvx` для MCP |
| `ruff` | линт и формат |
| `pytest` | тесты парсеров на фикстурах |
| `sqlite-utils` | быстрая инспекция БД из консоли |
| `jq` | разбор JSON (если нет — скрипт подскажет `apt install jq`) |

```bash
bash scripts/setup.sh
```

Скрипт создаёт `.venv`, ставит зависимости, копирует
`config/settings.example.env` в `settings.local.env`, настраивает MCP и
проверяет доступ к minkara (200/403).

---

## 2. MCP-серверы (OpenCode V2)

Конфигурация — `opencode.json`, ключ `mcp.servers`. Настраивается скриптом:

```bash
python3 scripts/setup_mcp.py
opencode mcp list
```

Скрипт идемпотентен: добавляет недостающие серверы, обновляет изменившиеся,
не трогает остальные ключи конфига.

### sqlite — DBHub

Даёт агенту SQL-доступ к `data/archive.sqlite` (инструменты `execute_sql`,
`search_objects`).

```jsonc
{
  "mcp": {
    "servers": {
      "sqlite": {
        "type": "local",
        "command": ["npx", "-y", "@bytebase/dbhub@1.7.1",
                    "--transport", "stdio",
                    "--dsn", "sqlite:////home/anatoly/prj/minkara/data/archive.sqlite"],
        "cwd": "/home/anatoly/prj/minkara"
      }
    }
  }
}
```

> Почему не `mcp-server-sqlite`: пакет устарел и падает с
> `AttributeError: 'Server' object has no attribute 'list_resources'` на
> актуальном Python-SDK MCP. Пиннинг старых версий SDK упирается в
> несовместимость с pydantic. DBHub — поддерживаемый сервер, проверен
> handshake'ом и реальным запросом к архиву.

### fetch — точечные запросы

```jsonc
{
  "mcp": {
    "servers": {
      "fetch": {
        "type": "local",
        "command": ["uvx", "mcp-server-fetch"],
        "cwd": "/home/anatoly/prj/minkara"
      }
    }
  }
}
```

### filesystem — доступ к проекту

```jsonc
{
  "mcp": {
    "servers": {
      "filesystem": {
        "type": "local",
        "command": ["npx", "-y", "@modelcontextprotocol/server-filesystem",
                    "/home/anatoly/prj/minkara"],
        "cwd": "/home/anatoly/prj/minkara"
      }
    }
  }
}
```

### git — история и коммиты

```jsonc
{
  "mcp": {
    "servers": {
      "git": {
        "type": "local",
        "command": ["uvx", "mcp-server-git", "--repository",
                    "/home/anatoly/prj/minkara"],
        "cwd": "/home/anatoly/prj/minkara"
      }
    }
  }
}
```

### Отключение сервера

В V2 нет поля `enabled`; чтобы оставить сервер в конфиге, но не подключать —
`"disabled": true`.

---

## 3. Понадобится позже

### Ollama — локальный перевод

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:14b-instruct   # или gemma3:12b, mistral-nemo
```

16+ ГБ RAM (14B в Q4), лучше GPU. Плюсы: офлайн, бесплатно. Минусы: качество
и скорость ниже топовых API; японский технический текст требует глоссария.

Провайдер уже поддержан: `MINKARA_TRANSLATE_PROVIDER=ollama`.

### Google Translate

* `--provider google` — бесплатный веб-эндпоинт (без ключа, без SLA);
* `--provider google_cloud` — официальный API, нужен ключ
  (`MINKARA_TRANSLATE_API_KEY`).

### OpenAI-совместимый API

`--provider openai` + `MINKARA_TRANSLATE_BASE_URL`, `MINKARA_TRANSLATE_API_KEY`,
`MINKARA_TRANSLATE_MODEL`.

### ImageMagick — превью и пережатие

```bash
sudo apt install imagemagick
```

### Playwright MCP — только если появится JS-рендеринг

Сейчас не нужен: страницы отдаются серверным HTML. Держим как резерв:

```jsonc
{
  "mcp": {
    "servers": {
      "playwright": {
        "type": "local",
        "command": ["npx", "@playwright/mcp@latest"],
        "disabled": true
      }
    }
  }
}
```

---

## 4. Что отклонено и почему

| Инструмент | Почему нет |
|---|---|
| `wget --mirror` / `httrack` | тянут весь сайт, ломают структуру, не умеют ждать `?pn=` и фильтровать по поколению; нет БД и инкрементальности |
| `monolith` / SingleFile | годятся для разовой страницы, но не для тысяч страниц с переводами и поиском |
| Electron/Tauri | требует сборки/установки под каждую ОС; статический сайт решает задачу без софта |
| Обязательный сервер (Flask/FastAPI) | лишняя зависимость; есть опциональный `serve.py` на stdlib |

---

## 5. Проверка

```bash
uv --version
.venv/bin/ruff --version
.venv/bin/pytest --version
.venv/bin/sqlite-utils --version
opencode mcp list
```

Ожидаемо: `fetch`, `filesystem`, `git`, `sqlite` — `connected`.
