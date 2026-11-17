# Minkara Archive — мастер-план

Документ самодостаточен: содержит результаты разведки, архитектуру, задачи и
принятые решения. Его можно передавать в контекст другому исполнителю без
дополнительных пояснений.

Статус: план утверждается. Код-каркас репозитория уже создан.

---

## 1. Цель

Локальный архив сайта `minkara.carview.co.jp` по заданным маркам/моделям
(старт — Honda Freed 2-го и 3-го поколений), с:

* хранением **контента в SQLite**, а **медиа — файлами в папке**;
* переводом текстов на русский (двуязычный просмотр);
* офлайн-просмотром на **Linux, Windows, macOS без установки софта**;
* возможностью позже добавить **любые другие марки** без переписывания кода.

Не цель: публикация архива, обход платных функций, сбор персональных данных
сверх необходимого для атрибуции.

---

## 2. Результаты разведки (проверено на живом сайте)

### 2.1 Доступ

* `minkara.carview.co.jp` → CNAME `e.edge12.g.yimg.jp` (edge-сеть Yahoo! JAPAN).
* Блокировка — **geo-IP denylist** на edge: `403 Request forbidden by
  administrative rules.` (статичный ответ 93 байта).
* Заголовки (`Accept-Language`, UA, `sec-ch-ua`, `sec-fetch-*`) **не влияют**.
  Старый трюк с `Accept-Language: en-US,...` больше не работает.
* С не-РФ IP (проверено: США, в т.ч. датацентр) — `200` и полный контент.
  `www.carview.co.jp` с того же IP открывается → блокируется конкретный хост.
* Вывод: нужен любой выход за пределы РФ; Япония не обязательна.

### 2.2 Структура URL

| Что | Шаблон |
|---|---|
| Каталог моделей марки | `/car/{brand}/` (может отдавать 404; список моделей берём из конфига) |
| Страница модели | `/car/{brand}/{model}/` |
| Листинг заметок | `/car/{brand}/{model}/note/?pn=N` |
| Заметка | `/userid/{uid}/car/{car}/{note}/note.aspx` |
| Отдельное фото заметки | `/userid/{uid}/car/{car}/{note}/{i}/note.aspx` (не нужно) |
| Листинг обзоров запчастей | `/car/{brand}/{model}/partsreview/?pn=N` (каталог товаров) |
| Товар | `/car/{brand}/{model}/partsreview/?mk=…&br=…&id=…` |
| Отзыв о товаре | `/userid/{uid}/car/{car}/{note}/parts.aspx` |
| Листинг отзывов об авто | `/car/{brand}/{model}/review/?pn=N` (каталог отзывов) |
| Отзыв об авто | `/car/{brand}/{model}/review/detail.aspx?cid=…` |
| Фото/альбомы | `/car/{brand}/{model}/photo/`, `/userid/{uid}/album/` |
| Q&A | `/car/{brand}/{model}/qa/`, `/car/{brand}/{model}/qa/unit{id}/` |
| Профиль машины | `/userid/{uid}/car/{car}/profile.aspx` |

### 2.3 Листинг заметок

* 10 записей на страницу, блок `_ctl0_CPH1_UnitList_rList__ctlN`.
* Элемент: `li.item` → `a[id$="_HL_Image"]` (URL), `h2.article-title a`
  (заголовок), `p.lead` (лид), `span.date`, `span.username a`,
  `ul.sharevalue` (лайки/комментарии), `ol.figure4 img` (миниатюры),
  `div.stars span.cmn_icon_difficult` (сложность).
* **Конец списка:** после последней страницы `?pn=` не даёт 404, а показывает
  только блок «注目のコンテンツ» (`li.itemlist`, 3 записи). Признак конца —
  отсутствие `UnitList_rList` в HTML. Нельзя ориентироваться на HTTP-код.
* Рядом с основным списком есть фильтры `?bi=…&sci=…&ci=…` (категории).
  Для полного охвата идём без фильтров, категории берём со страниц заметок.

### 2.4 Страница заметки

* Заголовок: `h1.contentsTitle`.
* Шапка: `p.user-article-header__date` («作業日：…»), категории
  `ul.article-category-contents a`, авто `a[id$="_HL_UserCarTitle"]`,
  лайки `span[id^="txtLikeCount"]`, соседние заметки
  `a[id$="_Pager3_HL_Pre"]` / `_HL_Next`, оглавление `_HL_List`.
* Таблица характеристик: `table tr` с `th` = `難易度`, `作業時間` и т.п.
* Контент — **галерея**: последовательность
  `div.galleryTitle` → `div.galleryPhoto` → `div.galleryMemo` (соседние
  siblings). В `galleryPhoto`: `img[src]` (крупное фото) и `a[href]` на
  просмотр фото; в `galleryMemo`: текст с `<br />`.
* Картинки: `cdn.snsimg.carview.co.jp/minkara/note/…/pN.jpg` (крупные),
  `pNs.jpg` (средние), `pNmm.jpg` (миниатюры). Query `?ct=…` — кэш-ключ,
  для файла не нужен.

### 2.5 Отзывы о запчастях и об авто

* `partsreview` и `review` — это **каталоги**: список товаров/отзывов →
  страница товара/отзыва → пользовательские отзывы (`parts.aspx`,
  `detail.aspx?cid=…`). Плоского списка «все отзывы» нет.
* `parts.aspx`: `h1.contentsTitle`, оценка `em.score`, текст
  `.userCarPhotoMemo`, фото `#UserCarPhoto img`, категории, дата.
* Поэтому это отдельные пайплайны, а не один общий обход.

### 2.6 Поколения Freed (важно)

Поколение **нельзя** определить по листингу: в нём нет кода кузова, а в
заголовках `GB7` встречается лишь как текст. Достоверный источник — профиль
машины: `/userid/{uid}/car/{car}/profile.aspx`, поле **型式**.

Проверено на живых данных: `6AA-GB7` (2-е поколение, гибрид),
`6AA-GT6` (3-е поколение). Отсюда правило:

| Поколение | Коды (型式) | Модели minkara |
|---|---|---|
| 1-е | GB1–GB4 | `freed`, `freed_hybrid`, `freed_spike`, `freed_spike_hybrid` |
| 2-е | GB5–GB8 | `freed`, `freed_hybrid`, `freed_plus`, `freed_plus_hybrid` |
| 3-е | GT1–GT8 | `freed`, `freed_hybrid` (новые кузова) |

Маппинг выносится в `config/generations.yaml` (regex по коду), чтобы
поддержать другие марки. Заметка наследует поколение от своей машины.
Если код не распознан — `generation=unknown` (по умолчанию **включаем**,
помечаем в отчёте; политика настраивается).

### 2.7 Масштаб (оценка)

* Freed, раздел `note`: ~200 страниц листинга × 10 = **~2000 заметок**.
* 6 моделей семейства; после фильтра 2–3 поколений ожидается ~60–80% от
  общего числа (точные числа даст `01_discover`).
* HTML: ~90 КБ/страница → ~180 МБ; медиа ~1–2 ГБ.
* При 1 запросе/сек: ~1 час на 2000 страниц + время на картинки.

### 2.8 Ограничения сайта

* `robots.txt`: `Crawl-delay: 1`; запрещены в основном API-эндпоинты
  (`/include_api/…`), `*edit.aspx`, `/image.aspx`, личные кабинеты.
  Нужные нам разделы разрешены.
* При агрессивном темпе edge начинает отдавать `403` — держим 1 req/s
  (настраивается `MINKARA_DELAY`).
* `?pn=` вне диапазона не сигнализирует ошибку — см. 2.3.

---

## 3. Объём работ

### 3.1 Стартовый охват

* Марка: Honda.
* Модели: **все, содержащие `freed`** — `freed`, `freed_hybrid`, `freed_plus`,
  `freed_plus_hybrid`, `freed_spike`, `freed_spike_hybrid`. Список проверен
  по странице модели и автообнаружением (`00_models.py --match freed`).
* Поколения/годы: **все** (`generations: []`). Поколение определяется по
  коду кузова (型式), при его отсутствии — по названию комплектации
  (`grade_hints`), и остаётся **метаданными** для фильтров и отчётов.
  Заметки с неизвестным поколением всё равно собираются.
* Темы: **все** категории заметок — ремонт, тюнинг/украшения, обзоры,
  расходники и т.д. Фильтра по категориям нет.

### 3.2 Разделы

| Раздел | Приоритет | Комментарий |
|---|---|---|
| `note` (整備手帳) | P0 | ядро: галерея + подписи |
| `partsreview` (パーツレビュー) | P1 | каталог товаров → отзывы |
| `review` (クルマレビュー) | P1 | отзывы владельцев |
| `photo` (フォト) | P2 | альбомы/фото |
| `qa` (Q&A) | P2 | вопросы-ответы |
| профили машин | P0 (служебный) | нужны для поколения и контекста |
| страницы модели/каталог | P2 | связность офлайн-сайта |

### 3.3 Возможность других марок

Конфиг описывает марки и модели; код не знает про Honda/Freed ничего, кроме
шаблонов URL и парсеров разделов. Добавление марки = правка YAML + запуск
`01_discover` с новым `--brand`.

---

## 4. Архитектура

### 4.1 Компоненты

```
config/*.yaml
     │
     ▼
[01 discover] ──► SQLite (pages) ──► [02 fetch] ──► data/raw/*.html
                                          │           data/assets/**
                                          ▼
                                   SQLite (pages.meta_json, cars, assets)
                                          │
                                          ▼
                                  [03 translate] ──► text_units(ru)
                                          │
                                          ▼
                                   [04 build] ──► out/site/** (статика)
                                          │
                                          ▼
                              браузер (file://) или serve.py
```

* **SQLite** — источник истины для контента и состояния пайплайна.
* **Медиа** — обычные файлы в `data/assets/`, путь сохраняет структуру CDN.
* **Просмотр** — сгенерированный **статический сайт**: не требует сервера,
  БД и установки софта. `serve.py` — опционально, для удобства.

### 4.2 Схема БД (`data/archive.sqlite`)

```sql
-- марки/модели/поколения дублируются из конфига для целостности отчётов
CREATE TABLE brands (
  id INTEGER PRIMARY KEY, key TEXT UNIQUE, name TEXT
);
CREATE TABLE models (
  id INTEGER PRIMARY KEY, brand_id INTEGER REFERENCES brands(id),
  key TEXT, name TEXT, UNIQUE(brand_id, key)
);

CREATE TABLE pages (
  id INTEGER PRIMARY KEY,
  url TEXT UNIQUE NOT NULL,
  kind TEXT NOT NULL,           -- listing|note|parts|review|photo|qa|model|car|other
  brand TEXT, model TEXT, section TEXT,
  listing_page INTEGER,         -- для листингов
  uid INTEGER, car INTEGER, note INTEGER,
  state TEXT NOT NULL DEFAULT 'new',  -- new|fetched|parsed|error|skipped
  http_code INTEGER,
  file TEXT,                    -- путь в data/raw
  title TEXT,
  generation INTEGER,           -- 2|3|NULL
  meta_json TEXT,               -- распарсенные данные
  fetched_at TEXT, error TEXT
);

CREATE TABLE cars (             -- профили машин
  id INTEGER PRIMARY KEY,
  car_id INTEGER UNIQUE,        -- /car/<id>/
  url TEXT, uid INTEGER,
  brand TEXT, model TEXT,
  grade TEXT, code TEXT,        -- 型式, напр. 6AA-GB7
  generation INTEGER,
  state TEXT DEFAULT 'new',     -- new|fetched|parsed|error
  meta_json TEXT, fetched_at TEXT, error TEXT
);

CREATE TABLE assets (
  id INTEGER PRIMARY KEY,
  url TEXT UNIQUE NOT NULL,
  page_url TEXT,
  kind TEXT,                    -- image|thumb|other
  file TEXT, bytes INTEGER,
  state TEXT DEFAULT 'new',     -- new|done|error
  http_code INTEGER, error TEXT
);

CREATE TABLE text_units (
  id INTEGER PRIMARY KEY,
  page_id INTEGER REFERENCES pages(id),
  kind TEXT,                    -- title|memo|lead|review|qa
  idx INTEGER,
  ja TEXT NOT NULL,
  hash TEXT NOT NULL,
  ru TEXT, engine TEXT, translated_at TEXT,
  UNIQUE(page_id, kind, idx)
);
CREATE INDEX ix_text_units_hash ON text_units(hash);

CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
```

Инварианты:

* `pages.url` и `assets.url` канонизированы (`urls.canonical`).
* Состояния только вперёд: `new → fetched → parsed`, ошибки — `error` с
  возможностью сброса.
* `text_units.hash` = sha1 исходного `ja`; перевод кэшируется глобально по
  хэшу (одинаковые подписи не переводятся дважды).

### 4.3 Хранение медиа

```
data/assets/
  cdn.snsimg.carview.co.jp/minkara/note/000/006/379/447/6379447/p1.jpg
  cdn.snsimg.carview.co.jp/carlife/images/User/2025950/p1.jpg
  ...
```

* Имя = host + path без query; при коллизии/длинном пути — суффикс-хэш.
* Дубликаты не качаются (UNIQUE по URL).
* Миниатюры `pNmm.jpg` нужны только для листингов; по умолчанию качаем
  крупные `pN.jpg`, миниатюры — опционально (`--with-thumbs`).

### 4.4 Просмотр: кроссплатформенность без установки

**Основной режим — статический сайт.**

* `out/site/index.html` открывается двойным кликом в любом браузере
  (Linux/Windows/macOS), в т.ч. по `file://`, без сервера и Python.
* Поиск работает офлайн: индекс кладётся в `search-index.js`
  (`window.MINKARA_INDEX = [...]`), подключается через `<script>` — это
  обходит CORS-ограничения `file://` (fetch JSON там запрещён).
* Для 2000+ заметок индекс бьётся на шарды по 300–500 записей либо грузится
  лениво по первой букве/модели; стартовый вариант — один файл ~2–5 МБ.

**Запускаторы (в репозитории, без зависимостей):**

| ОС | Файл | Действие |
|---|---|---|
| Linux | `view.sh` | `xdg-open out/site/index.html` |
| macOS | `view.command` | `open out/site/index.html` |
| Windows | `view.bat` | `start "" out\site\index.html` |

**Опционально — локальный сервер** (`scripts/serve.py`, только stdlib):

* красивые URL, ленивая подгрузка, поиск через fetch;
* запуск: `python3 scripts/serve.py` → `http://127.0.0.1:8765`;
* не обязателен; нужен, если хочется «как сайт».

**Почему не отдельное приложение на Electron/Tauri:** требует установки
или сборки под каждую ОС, противоречит требованию «без доп. софта».
Статика решает задачу дешевле и надёжнее. При желании позже можно
упаковать статику в один бинарник (PyInstaller/Tauri), но это не блокер.

### 4.5 Генеричность по маркам

`config/models.yaml`:

```yaml
brands:
  honda:
    name: Honda
    models:
      - key: freed
        name: Honda Freed
        generations: [2, 3]
      - key: freed_hybrid
        name: Honda Freed Hybrid
        generations: [2, 3]
      - key: freed_plus
        name: Honda Freed Plus
        generations: [2, 3]
      - key: freed_plus_hybrid
        name: Honda Freed Plus Hybrid
        generations: [2, 3]
      - key: freed_spike
        name: Honda Freed Spike
        generations: []        # только 1-е, не берём
sections:
  note:        { enabled: true,  title: 整備手帳 }
  partsreview: { enabled: true,  title: パーツレビュー }
  review:      { enabled: true,  title: クルマレビュー }
  photo:       { enabled: false, title: フォト }
  qa:          { enabled: false, title: Q&A }
```

`config/generations.yaml` — правила «код 型式 → поколение» на марку/модель:

```yaml
honda:
  freed:
    - { generation: 1, codes: ["GB1", "GB2", "GB3", "GB4"] }
    - { generation: 2, codes: ["GB5", "GB6", "GB7", "GB8"] }
    - { generation: 3, codes: ["GT1", "GT2", "GT3", "GT4", "GT5", "GT6", "GT7", "GT8"] }
```

Код извлекается из `型式` (`6AA-GB7` → `GB7`), сравнивается по префиксу.
Неизвестный код → `unknown`.

---

## 5. Пайплайн: этапы и CLI

Все этапы идемпотентны, прерываемы, поддерживают `--limit` и `--retry-errors`.

### 5.1 `01_discover.py` — сбор URL

* Вход: конфиг (марки/модели/разделы/поколения).
* Действие:
  1. Для каждой модели/раздела обходит листинги `?pn=1..N` до отсутствия
     `UnitList_rList` (для `note`), либо до конца каталога (для
     `partsreview`/`review`).
  2. Сохраняет HTML листинга в `data/raw` (нужен для отладки и повторного
     парсинга без сети).
  3. Пишет `pages` (kind=`note`/`parts`/`review`/`listing`) и `assets`
     (миниатюры листинга — опционально).
  4. Для `note` дополнительно регистрирует `cars` (профили машин) —
     по одному на `car_id`.
* Выход: заполненные `pages`, `cars`.
* Ключевые флаги: `--brand honda --models freed,freed_hybrid`,
  `--sections note,partsreview`, `--max-pages`, `--delay`.

### 5.2 `02_fetch.py` — скачивание и парсинг

* Берёт `pages.state=new` (и `cars.state=new`).
* Для `note`: качает HTML → `data/raw`, парсит (`parse_note`), пишет
  `meta_json`, регистрирует картинки в `assets`, ставит `state=parsed`.
* Для `cars`: качает профиль, извлекает `型式`/`グレード`, вычисляет
  `generation`, обновляет связанные заметки.
* Для `parts`/`review`: аналогично своими парсерами.
* Затем качает `assets.state=new` в `data/assets`.
* Ошибки: `403` → остановка с подсказкой про VPN; `404` → `state=skipped`;
  прочее → `error` + повтор при следующем запуске.
* Флаги: `--limit`, `--kind`, `--with-thumbs`, `--no-assets`, `--retry-errors`.

### 5.3 `03_translate.py` — перевод

* Собирает `text_units` из `meta_json` (заголовок, подписи к фото, лид,
  текст отзывов).
* Провайдеры (адаптер):
  * `echo` — заглушка (для тестов пайплайна);
  * `openai` — любой OpenAI-совместимый API;
  * `ollama` — локальная модель (офлайн, без оплаты).
* Батчинг по N единиц, ретраи, кэш по `hash`, глоссарий
  `config/glossary.yaml`.
* Флаги: `--provider`, `--limit`, `--only-missing`, `--dry-run`.

### 5.4 `04_build.py` — сборка статики

* Страницы: заметка, отзыв о запчасти, отзыв об авто, Q&A (по мере фаз).
* Индекс: список заметок с фильтрами (модель, поколение, категория, год).
* Поиск: `search-index.js` + клиентский фильтр (ja + ru).
* Ссылки: внутренние → локальные, если страница в архиве; иначе — на
  оригинал (помечено). Prev/next сохраняются.
* Медиа: относительные пути, `loading="lazy"`.
* Атрибуция: автор, дата, ссылка на оригинал на каждой странице.
* Флаги: `--only-missing`, `--lang both|ru|ja`.

### 5.5 `serve.py` — опциональный просмотр

* `python3 scripts/serve.py [--port 8765]` — stdlib `http.server`,
  отдаёт `out/site`.

---

## 6. Задачи (чек-лист)

### M0. Каркас (сделано)

- [x] Структура репозитория, `.gitignore`, README, requirements.
- [x] Конфиги: модели (все Freed), поколения, глоссарий, шаблон env.
- [x] Документация: план, архитектура, инструменты.
- [x] `scripts/setup.sh` + `setup_mcp.py` (uv, venv, ruff/pytest/sqlite-utils, MCP).

### M1. Ядро: все заметки всех моделей Freed (сделано)

- [x] `src/minkara/config.py` — generic-загрузка марок/моделей/поколений,
      fallback по комплектации.
- [x] `src/minkara/urls.py` — канонизация, классификация, раскладка файлов.
- [x] `src/minkara/http.py` — rate limit, retries, `403`-детект.
- [x] `src/minkara/parse.py` — `parse_listing`, `parse_note`, `parse_profile`,
      `parse_parts`, `parse_review`, `extract_text_units`.
- [x] `src/minkara/db.py` — схема, `Store`.
- [x] `scripts/00_models.py` — автообнаружение моделей по подстроке.
- [x] `scripts/01_discover.py` — обход листингов + регистрация машин.
- [x] `scripts/02_fetch.py` — страницы + профили + картинки.
- [x] Тесты (11) на фикстурах, ruff чистый.
- [x] Сквозной прогон: discover → fetch → translate → build.

### M2. Перевод и просмотр (сделано)

- [x] `scripts/03_translate.py` (echo/google/google_cloud/openai/ollama).
- [x] `scripts/04_build.py` — страницы + индекс + поиск.
- [x] `view.sh` / `view.command` / `view.bat`, `serve.py`.
- [ ] Проверка на Windows/macOS (на Linux проверено).

### M3. Обзоры запчастей (сделано)

- [x] Обход каталога товаров (`li.item-common`, 20 на страницу).
- [x] Страница товара (`/partsreview/parts.aspx?pt=…`) → отзывы.
- [x] Парсер `parts.aspx`, регистрация отзывов.
- [x] Включение в перевод, каталог и поиск.

### M4. Отзывы об авто (сделано)

- [x] Обход каталога `review/` (`ul.review-carpage-list`, 5 на страницу).
- [x] Парсер `detail.aspx?cid=…`: оценки по аспектам, секции, фото.
- [x] Поколение по названию комплектации (grade_hints), если 型式 нет.

### M5. Дополнительно

- [ ] Фото/альбомы, Q&A, страницы моделей.
- [ ] Инкрементальное обновление (`--since`/повторный discover).
- [ ] Отчёт о покрытии: сколько заметок по моделям/поколениям/категориям.

---

## 7. Решения и обоснования

| Решение | Почему |
|---|---|
| SQLite, а не файлы JSON | транзакции, уникальность URL, инкрементальность, SQL-отчёты |
| Медиа файлами, а не BLOB | размер, кэширование браузером, простота бэкапа |
| Статический сайт для просмотра | работает на 3 ОС без установки софта и сервера |
| Поиск через `search-index.js` | `fetch` JSON не работает на `file://` |
| Поколение через профиль машины | в листингах и заметках нет кода кузова |
| Поколения в YAML | другие марки добавляются без правки кода |
| 1 req/s по умолчанию | robots `Crawl-delay`, защита от 403 |
| Кэш перевода по хэшу | не платить дважды, безопасные повторные запуски |

---

## 8. Риски и меры

| Риск | Мера |
|---|---|
| Смена вёрстки сайта | парсеры на устойчивых id/классах, тесты на фикстурах, `--reparse` из `data/raw` без сети |
| Блокировка по IP/лимитам | 1 req/s, пауза при 403, возобновление |
| Огромный объём медиа | качать только крупные фото, `--no-assets`, дедупликация по URL |
| Неизвестные коды кузовов | `generation=unknown`, отчёт, ручное дополнение YAML |
| Потеря контекста при передаче | этот документ + `docs/architecture.md` самодостаточны |
| Авторские права | личное использование, атрибуция, без публикации |

---

## 9. Открытые вопросы (с дефолтами)

1. **Провайдер перевода.** Дефолт: `echo` для обкатки, затем решить —
   локальная модель (Ollama) или API. Вопрос бюджета/качества.
2. **Комментарии к заметкам.** Не входят в P0; ценны, но это отдельные
   страницы/эндпоинты. Дефолт: фаза M5.
3. **Полноразмерные фото.** `pN.jpg` — это уже крупный размер; оригинала
   больше нет. Дефолт: `pN.jpg`, миниатюры опционально.
4. **Язык интерфейса архива.** Дефолт: русский UI, контент ja+ru.
5. **Инкрементальность.** Дефолт: разовый полный обход + повторный discover
   для новых заметок.
6. **Поколения и годы.** Берём все; поколение — только метаданные. Если
   появятся отдельные модели minkara для новых кузовов, их добавит
   `00_models.py --match freed --write`.

---

## 10. Инструменты и MCP

См. `docs/tools.md`. Кратко: `uv` (окружение), `ruff` + `pytest`
(качество), `sqlite-utils`/`sqlite3` (инспекция БД), MCP: `filesystem`,
`sqlite`, `fetch`, `git`. Опционально: `playwright` MCP (если появится
JS-рендеринг), `ollama` (локальный перевод).

---

## Приложение A. Проверенные селекторы

```text
Листинг заметок:
  li.item
  a[id$="_HL_Image"]            -> URL заметки
  h2.article-title a            -> заголовок
  p.lead                        -> лид
  span.date                     -> дата
  span.username a               -> автор
  ol.figure4 img                -> миниатюры
  div.stars span.cmn_icon_difficult -> сложность (кол-во)
  признак конца: нет "UnitList_rList" в HTML

Заметка:
  h1.contentsTitle
  p.user-article-header__date
  ul.article-category-contents a
  a[id$="_HL_UserCarTitle"]     -> модель
  a[id$="_HL_UserCar"]          -> профиль машины
  table tr (th/td)              -> 難易度, 作業時間, ...
  div.galleryTitle / div.galleryPhoto / div.galleryMemo
  span[id^="txtLikeCount"]
  a[id$="_Pager3_HL_Pre"] / _HL_Next / _HL_List

Профиль машины:
  table tr: グレード, 型式, ボディーカラー, 所有形態, 車歴, 所有期間
  поле 型式 -> код (6AA-GB7) -> поколение

Отзыв о запчасти (parts.aspx):
  h1.contentsTitle
  em.score
  .userCarPhotoMemo
  #UserCarPhoto img
  ul.article-category-contents a
```

## Приложение B. Канонизация URL

* Приводить к `https://`, нижний регистр хоста, без фрагмента.
* Сохранять только значимые query: `pn`, `bi`, `sci`, `ci`, `mk`, `br`, `id`,
  `cid`.
* Отбрасывать `ct`, `utm_*`, `_x_tr_*` (артефакты Google Translate).
* `?pn=1` и без `pn` — один и тот же URL.
