PY ?= .venv/bin/python

.PHONY: help setup status report crawl translate build iso serve test lint optimize clean

help:
	@echo "make setup      — окружение, зависимости, MCP"
	@echo "make status     — состояние архива"
	@echo "make report     — отчёт о покрытии"
	@echo "make crawl      — полная выкачка"
	@echo "make translate  — перевод (DeepL + Google + fix-bad)"
	@echo "make build      — сборка офлайн-сайта"
	@echo "make iso        — ISO-образ для просмотра"
	@echo "make optimize   — сжатие HTML, дедуп медиа, VACUUM"
	@echo "make serve      — локальный сервер"
	@echo "make test       — тесты"
	@echo "make lint       — ruff"

setup:
	bash scripts/setup.sh

status:
	$(PY) scripts/status.py

report:
	$(PY) scripts/report.py

crawl:
	bash scripts/crawl_all.sh

translate:
	bash scripts/translate_all.sh

build:
	$(PY) scripts/04_build.py

iso:
	bash scripts/build_iso.sh

optimize:
	$(PY) scripts/optimize.py --compress-raw --dedupe-assets --hardlink-out --vacuum

serve:
	$(PY) scripts/serve.py

test:
	$(PY) -m pytest -q

lint:
	$(PY) -m ruff check src scripts tests

clean:
	rm -rf out/site work/*.log work/*.run.sh
