"""Настройки проекта и загрузка декларативных конфигов.

Все пути выводятся из корня репозитория. Runtime-каталоги (data/out/work)
создаются при загрузке настроек и в git не попадают.
"""
from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

DEFAULT_BASE_URL = "https://minkara.carview.co.jp"


@dataclass(frozen=True)
class Settings:
    root: Path
    base_url: str
    user_agent: str
    delay: float
    timeout: float
    retries: int
    data_dir: Path
    out_dir: Path
    work_dir: Path
    models_file: Path
    generations_file: Path
    glossary_file: Path

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def assets_dir(self) -> Path:
        return self.data_dir / "assets"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "archive.sqlite"

    @property
    def site_dir(self) -> Path:
        return self.out_dir / "site"


@dataclass(frozen=True)
class ModelSpec:
    brand: str
    key: str
    name: str
    generations: tuple[int, ...]

    @property
    def slug(self) -> str:
        return f"{self.brand}/{self.key}"


def _load_env_file() -> None:
    """Подхватывает config/settings.local.env, не перетирая окружение."""
    path = ROOT / "config" / "settings.local.env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    return float(value) if value else default


def _env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value).expanduser() if value else default


def load_settings(**overrides: Any) -> Settings:
    """Собирает настройки из окружения и создаёт runtime-каталоги."""
    _load_env_file()
    settings = Settings(
        root=ROOT,
        base_url=os.environ.get("MINKARA_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
        user_agent=os.environ.get("MINKARA_USER_AGENT", DEFAULT_USER_AGENT),
        delay=_env_float("MINKARA_DELAY", 1.0),
        timeout=_env_float("MINKARA_TIMEOUT", 30.0),
        retries=int(os.environ.get("MINKARA_RETRIES", "4")),
        data_dir=_env_path("MINKARA_DATA_DIR", ROOT / "data"),
        out_dir=_env_path("MINKARA_OUT_DIR", ROOT / "out"),
        work_dir=_env_path("MINKARA_WORK_DIR", ROOT / "work"),
        models_file=_env_path("MINKARA_MODELS_FILE", ROOT / "config" / "models.yaml"),
        generations_file=_env_path(
            "MINKARA_GENERATIONS_FILE", ROOT / "config" / "generations.yaml"
        ),
        glossary_file=_env_path("MINKARA_GLOSSARY_FILE", ROOT / "config" / "glossary.yaml"),
    )
    if overrides:
        settings = replace(settings, **overrides)
    for path in (
        settings.data_dir,
        settings.raw_dir,
        settings.assets_dir,
        settings.out_dir,
        settings.work_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)
    return settings


def _read_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_models(settings: Settings) -> list[ModelSpec]:
    """Модели из config/models.yaml + models.discovered.yaml (ручные в приоритете)."""
    sources = []
    discovered = settings.models_file.with_name("models.discovered.yaml")
    if discovered.exists():
        sources.append(discovered)  # сначала авто, затем ручные — ручные перекрывают
    sources.append(settings.models_file)

    models: dict[tuple[str, str], ModelSpec] = {}
    for path in sources:
        data = _read_yaml(path)
        for brand_key, brand in (data.get("brands") or {}).items():
            for item in brand.get("models") or []:
                key = item["key"]
                models[(brand_key, key)] = ModelSpec(
                    brand=brand_key,
                    key=key,
                    name=item.get("name", key),
                    generations=tuple(item.get("generations") or ()),
                )
    return list(models.values())


def load_sections(settings: Settings) -> dict[str, dict]:
    """Разделы сайта: note, partsreview, review, photo, qa."""
    data = _read_yaml(settings.models_file)
    return data.get("sections") or {}


def load_generation_rules(settings: Settings) -> dict:
    return _read_yaml(settings.generations_file)


def extract_code(grade_code: str) -> str | None:
    """'6AA-GB7' -> 'GB7'; 'DBA-GB4' -> 'GB4'; 'GB7' -> 'GB7'."""
    if not grade_code:
        return None
    cleaned = grade_code.strip().upper().replace(" ", "")
    tail = cleaned.split("-")[-1]
    return tail or None


def generation_for(
    rules: dict,
    brand: str,
    model: str,
    grade_code: str | None,
    grade: str | None = None,
) -> int | None:
    """Определяет поколение по коду кузова (型式), иначе — по комплектации.

    Правила ищутся сначала для модели, затем для марки (brand_default).
    Совпадение по коду — префиксное, побеждает самый длинный код.
    Если код не заполнен, используются grade_hints (подстроки в названии
    комплектации). Поколение — только метаданные, сбор идёт по всем годам.
    """
    brand_rules = rules.get(brand) or {}
    model_rules = brand_rules.get(model) or brand_rules.get("brand_default") or []
    code = extract_code(grade_code or "")
    if code:
        best: tuple[int, int] | None = None  # (длина кода, поколение)
        for rule in model_rules:
            generation = int(rule["generation"])
            for candidate in rule.get("codes") or []:
                candidate = str(candidate).upper()
                if code.startswith(candidate) and (best is None or len(candidate) > best[0]):
                    best = (len(candidate), generation)
        if best:
            return best[1]

    if grade:
        for hint in brand_rules.get("grade_hints") or []:
            for pattern in hint.get("patterns") or []:
                if pattern and pattern in grade:
                    return int(hint["generation"])
    return None


def selected_models(
    models: Iterable[ModelSpec], brand: str | None, keys: Iterable[str] | None
) -> list[ModelSpec]:
    keys_set = {k.strip() for k in (keys or []) if k and k.strip()}
    result = []
    for model in models:
        if brand and model.brand != brand:
            continue
        if keys_set and model.key not in keys_set:
            continue
        result.append(model)
    return result
