"""SQLite-хранилище состояния пайплайна и распарсенного контента."""
from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS pages (
    id INTEGER PRIMARY KEY,
    url TEXT UNIQUE NOT NULL,
    kind TEXT NOT NULL,
    brand TEXT,
    model TEXT,
    section TEXT,
    listing_page INTEGER,
    uid INTEGER,
    car INTEGER,
    note INTEGER,
    state TEXT NOT NULL DEFAULT 'new',
    http_code INTEGER,
    file TEXT,
    title TEXT,
    generation INTEGER,
    meta_json TEXT,
    fetched_at TEXT,
    error TEXT
);
CREATE INDEX IF NOT EXISTS ix_pages_state ON pages(state);
CREATE INDEX IF NOT EXISTS ix_pages_kind ON pages(kind);
CREATE INDEX IF NOT EXISTS ix_pages_car ON pages(car);

CREATE TABLE IF NOT EXISTS cars (
    id INTEGER PRIMARY KEY,
    car_id INTEGER UNIQUE NOT NULL,
    url TEXT,
    uid INTEGER,
    brand TEXT,
    model TEXT,
    grade TEXT,
    code TEXT,
    generation INTEGER,
    state TEXT NOT NULL DEFAULT 'new',
    meta_json TEXT,
    fetched_at TEXT,
    error TEXT
);
CREATE INDEX IF NOT EXISTS ix_cars_state ON cars(state);

CREATE TABLE IF NOT EXISTS assets (
    id INTEGER PRIMARY KEY,
    url TEXT UNIQUE NOT NULL,
    page_url TEXT,
    kind TEXT,
    file TEXT,
    bytes INTEGER,
    state TEXT NOT NULL DEFAULT 'new',
    http_code INTEGER,
    error TEXT
);
CREATE INDEX IF NOT EXISTS ix_assets_state ON assets(state);

CREATE TABLE IF NOT EXISTS text_units (
    id INTEGER PRIMARY KEY,
    page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    idx INTEGER NOT NULL,
    ja TEXT NOT NULL,
    hash TEXT NOT NULL,
    ru TEXT,
    engine TEXT,
    translated_at TEXT,
    UNIQUE(page_id, kind, idx)
);
CREATE INDEX IF NOT EXISTS ix_text_units_hash ON text_units(hash);
CREATE INDEX IF NOT EXISTS ix_text_units_ru ON text_units(ru);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def text_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


class Store:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        # timeout нужен, чтобы не падать при параллельной записи (crawl + перевод)
        self.conn = sqlite3.connect(self.path, timeout=30)
        self.conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self.conn.close()

    def init(self) -> None:
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ------------------------------------------------------------------ pages
    def upsert_page(self, url: str, **fields: Any) -> int:
        known = {
            "kind",
            "brand",
            "model",
            "section",
            "listing_page",
            "uid",
            "car",
            "note",
            "state",
            "http_code",
            "file",
            "title",
            "generation",
            "meta_json",
            "fetched_at",
            "error",
        }
        data = {k: v for k, v in fields.items() if k in known and v is not None}
        cur = self.conn.execute("SELECT id FROM pages WHERE url = ?", (url,))
        row = cur.fetchone()
        if row:
            if data:
                assignments = ", ".join(f"{key} = ?" for key in data)
                self.conn.execute(
                    f"UPDATE pages SET {assignments} WHERE id = ?",
                    (*data.values(), row["id"]),
                )
            return int(row["id"])
        data["url"] = url
        columns = ", ".join(data)
        placeholders = ", ".join("?" for _ in data)
        cur = self.conn.execute(
            f"INSERT INTO pages ({columns}) VALUES ({placeholders})",
            tuple(data.values()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def set_page(self, page_id: int, **fields: Any) -> None:
        if not fields:
            return
        assignments = ", ".join(f"{key} = ?" for key in fields)
        self.conn.execute(
            f"UPDATE pages SET {assignments} WHERE id = ?",
            (*fields.values(), page_id),
        )
        self.conn.commit()

    def pending_pages(
        self, kinds: Iterable[str] | None = None, limit: int | None = None
    ) -> list[sqlite3.Row]:
        sql = "SELECT * FROM pages WHERE state = 'new'"
        params: list[Any] = []
        if kinds:
            placeholders = ", ".join("?" for _ in kinds)
            sql += f" AND kind IN ({placeholders})"
            params.extend(kinds)
        sql += " ORDER BY id"
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        return list(self.conn.execute(sql, params))

    def retry_errors(self, kind: str | None = None) -> int:
        if kind:
            cur = self.conn.execute(
                "UPDATE pages SET state = 'new', error = NULL WHERE state = 'error' AND kind = ?",
                (kind,),
            )
        else:
            cur = self.conn.execute(
                "UPDATE pages SET state = 'new', error = NULL WHERE state = 'error'"
            )
        self.conn.commit()
        return cur.rowcount

    # ------------------------------------------------------------------- cars
    def upsert_car(self, car_id: int, **fields: Any) -> int:
        known = {
            "url",
            "uid",
            "brand",
            "model",
            "grade",
            "code",
            "generation",
            "state",
            "meta_json",
            "fetched_at",
            "error",
        }
        data = {k: v for k, v in fields.items() if k in known and v is not None}
        row = self.conn.execute(
            "SELECT id FROM cars WHERE car_id = ?", (car_id,)
        ).fetchone()
        if row:
            if data:
                assignments = ", ".join(f"{key} = ?" for key in data)
                self.conn.execute(
                    f"UPDATE cars SET {assignments} WHERE id = ?",
                    (*data.values(), row["id"]),
                )
                self.conn.commit()
            return int(row["id"])
        data["car_id"] = car_id
        columns = ", ".join(data)
        placeholders = ", ".join("?" for _ in data)
        cur = self.conn.execute(
            f"INSERT INTO cars ({columns}) VALUES ({placeholders})",
            tuple(data.values()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def pending_cars(self, limit: int | None = None) -> list[sqlite3.Row]:
        sql = "SELECT * FROM cars WHERE state = 'new' ORDER BY id"
        params: list[Any] = []
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        return list(self.conn.execute(sql, params))

    def apply_generation(self, car_id: int, generation: int | None) -> None:
        self.conn.execute(
            "UPDATE cars SET generation = ? WHERE car_id = ?", (generation, car_id)
        )
        self.conn.execute(
            "UPDATE pages SET generation = ? WHERE car = ?", (generation, car_id)
        )
        self.conn.commit()

    # ----------------------------------------------------------------- assets
    def add_asset(self, url: str, page_url: str | None = None, kind: str = "image") -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO assets (url, page_url, kind) VALUES (?, ?, ?)",
            (url, page_url, kind),
        )
        self.conn.commit()

    def pending_assets(self, limit: int | None = None) -> list[sqlite3.Row]:
        sql = "SELECT * FROM assets WHERE state = 'new' ORDER BY id"
        params: list[Any] = []
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        return list(self.conn.execute(sql, params))

    def set_asset(self, asset_id: int, **fields: Any) -> None:
        if not fields:
            return
        assignments = ", ".join(f"{key} = ?" for key in fields)
        self.conn.execute(
            f"UPDATE assets SET {assignments} WHERE id = ?",
            (*fields.values(), asset_id),
        )
        self.conn.commit()

    # ------------------------------------------------------------ text units
    def upsert_text_unit(
        self, page_id: int, kind: str, idx: int, ja: str, commit: bool = True
    ) -> None:
        self.conn.execute(
            """INSERT INTO text_units (page_id, kind, idx, ja, hash)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(page_id, kind, idx)
               DO UPDATE SET ja = excluded.ja, hash = excluded.hash""",
            (page_id, kind, idx, ja, text_hash(ja)),
        )
        if commit:
            self.conn.commit()

    def purge_non_japanese(self) -> int:
        """Удаляет единицы без японского текста (числа, латиница)."""
        rows = self.conn.execute("SELECT id, ja FROM text_units").fetchall()
        ids = []
        for row in rows:
            text = row["ja"] or ""
            has_cjk = any(
                "\u3040" <= ch <= "\u30ff" or "\u3400" <= ch <= "\u9fff" for ch in text
            )
            if not has_cjk:
                ids.append((row["id"],))
        if ids:
            self.conn.executemany("DELETE FROM text_units WHERE id = ?", ids)
            self.conn.commit()
        return len(ids)

    def pending_units(
        self, limit: int | None = None, kinds: list[str] | None = None
    ) -> list[sqlite3.Row]:
        sql = """SELECT t.* FROM text_units t
                 JOIN pages p ON p.id = t.page_id
                 WHERE t.ru IS NULL AND length(trim(t.ja)) > 0"""
        params: list[Any] = []
        if kinds:
            placeholders = ", ".join("?" for _ in kinds)
            sql += f" AND p.kind IN ({placeholders})"
            params.extend(kinds)
        # Сначала самое ценное: заметки, отзывы об авто, Q&A, модели,
        # затем товары и отзывы о запчастях.
        sql += """ ORDER BY CASE p.kind
                     WHEN 'note' THEN 1
                     WHEN 'review' THEN 2
                     WHEN 'qa' THEN 3
                     WHEN 'model' THEN 4
                     WHEN 'product' THEN 5
                     WHEN 'parts' THEN 6
                     ELSE 7 END, t.id"""
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        return list(self.conn.execute(sql, params))

    def cached_translation(self, hash_value: str, engine: str | None = None) -> str | None:
        sql = "SELECT ru FROM text_units WHERE hash = ? AND ru IS NOT NULL"
        params: list[Any] = [hash_value]
        if engine:
            # Кэш привязан к движку: echo-заглушки не должны попадать
            # в результат google/deepl/openai.
            sql += " AND engine = ?"
            params.append(engine)
        row = self.conn.execute(sql + " LIMIT 1", params).fetchone()
        return row["ru"] if row else None

    def units_for_page(self, page_id: int) -> dict[tuple[str, int], str]:
        rows = self.conn.execute(
            "SELECT kind, idx, ru FROM text_units WHERE page_id = ? AND ru IS NOT NULL",
            (page_id,),
        ).fetchall()
        return {(row["kind"], row["idx"]): row["ru"] for row in rows}

    def parsed_pages(self, kind: str) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                """SELECT * FROM pages
                   WHERE kind = ? AND state = 'parsed' AND meta_json IS NOT NULL
                   ORDER BY id""",
                (kind,),
            )
        )

    def set_translation(
        self, unit_id: int, ru: str, engine: str, commit: bool = True
    ) -> None:
        self.conn.execute(
            "UPDATE text_units SET ru = ?, engine = ?, translated_at = datetime('now') WHERE id = ?",
            (ru, engine, unit_id),
        )
        if commit:
            self.conn.commit()

    # ------------------------------------------------------------------ stats
    def stats(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for table in ("pages", "cars", "assets", "text_units"):
            result[table] = self.conn.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]
        result["pages_by_state"] = {
            row["state"]: row["n"]
            for row in self.conn.execute(
                "SELECT state, COUNT(*) AS n FROM pages GROUP BY state"
            )
        }
        result["pages_by_kind"] = {
            row["kind"]: row["n"]
            for row in self.conn.execute(
                "SELECT kind, COUNT(*) AS n FROM pages GROUP BY kind"
            )
        }
        result["assets_by_state"] = {
            row["state"]: row["n"]
            for row in self.conn.execute(
                "SELECT state, COUNT(*) AS n FROM assets GROUP BY state"
            )
        }
        result["translated"] = self.conn.execute(
            "SELECT COUNT(*) FROM text_units WHERE ru IS NOT NULL"
        ).fetchone()[0]
        return result
