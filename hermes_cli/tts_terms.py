"""Persistent TTS reading-term store.

The store is intentionally small and provider-agnostic: it maps a surface term
to the reading that should be fed into a TTS-specific normalizer. AquesTalk uses
it first, but Fish/other Japanese providers can reuse it later.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

from hermes_constants import get_hermes_home

logger = logging.getLogger(__name__)

DEFAULT_TTS_TERMS_DB = get_hermes_home() / "tts_terms.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tts_terms (
    term TEXT PRIMARY KEY COLLATE NOCASE,
    reading TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual',
    confidence REAL NOT NULL DEFAULT 1.0,
    metadata_json TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    last_used_at REAL,
    usage_count INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_tts_terms_updated_at ON tts_terms(updated_at);
CREATE INDEX IF NOT EXISTS idx_tts_terms_usage_count ON tts_terms(usage_count);
"""


def _db_path(path: str | Path | None = None) -> Path:
    return Path(path).expanduser() if path else DEFAULT_TTS_TERMS_DB


def _connect(path: str | Path | None = None) -> sqlite3.Connection:
    db_path = _db_path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    return conn


def add_tts_term(
    term: str,
    reading: str,
    *,
    source: str = "manual",
    confidence: float = 1.0,
    metadata: dict[str, Any] | None = None,
    db_path: str | Path | None = None,
) -> None:
    cleaned_term = str(term or "").strip()
    cleaned_reading = str(reading or "").strip()
    if not cleaned_term or not cleaned_reading:
        raise ValueError("term and reading are required")
    now = time.time()
    try:
        conf = float(confidence)
    except (TypeError, ValueError):
        conf = 1.0
    metadata_json = json.dumps(metadata, ensure_ascii=False) if metadata else None
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO tts_terms (
                term, reading, source, confidence, metadata_json,
                created_at, updated_at, last_used_at, usage_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 0)
            ON CONFLICT(term) DO UPDATE SET
                reading=excluded.reading,
                source=excluded.source,
                confidence=excluded.confidence,
                metadata_json=excluded.metadata_json,
                updated_at=excluded.updated_at
            """,
            (
                cleaned_term,
                cleaned_reading,
                str(source or "manual").strip() or "manual",
                conf,
                metadata_json,
                now,
                now,
            ),
        )


def delete_tts_term(term: str, *, db_path: str | Path | None = None) -> bool:
    cleaned = str(term or "").strip()
    if not cleaned:
        return False
    with _connect(db_path) as conn:
        cur = conn.execute("DELETE FROM tts_terms WHERE term = ?", (cleaned,))
        return cur.rowcount > 0


def list_tts_terms(
    *,
    limit: int = 100,
    offset: int = 0,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit or 100), 1000))
    safe_offset = max(0, int(offset or 0))
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT term, reading, source, confidence, metadata_json,
                   created_at, updated_at, last_used_at, usage_count
            FROM tts_terms
            ORDER BY usage_count DESC, updated_at DESC, term ASC
            LIMIT ? OFFSET ?
            """,
            (safe_limit, safe_offset),
        ).fetchall()
    return [dict(row) for row in rows]


def find_relevant_tts_terms(
    text: str,
    *,
    limit: int = 64,
    min_confidence: float = 0.0,
    db_path: str | Path | None = None,
) -> dict[str, str]:
    """Return terms whose surface form appears in *text*.

    This is the first retrieval layer. It deliberately returns only relevant
    terms, not the whole dictionary, so a large DB can grow without bloating the
    TTS prompt/normalizer. A later RAG implementation can replace this function
    behind the same return shape.
    """
    haystack = str(text or "")
    if not haystack:
        return {}
    safe_limit = max(1, min(int(limit or 64), 500))
    try:
        conf = float(min_confidence)
    except (TypeError, ValueError):
        conf = 0.0

    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT term, reading
            FROM tts_terms
            WHERE confidence >= ?
              AND instr(lower(?), lower(term)) > 0
            ORDER BY length(term) DESC, confidence DESC, usage_count DESC, updated_at DESC
            LIMIT ?
            """,
            (conf, haystack, safe_limit),
        ).fetchall()
        terms = {str(row["term"]): str(row["reading"]) for row in rows}
        if terms:
            now = time.time()
            conn.executemany(
                """
                UPDATE tts_terms
                SET usage_count = usage_count + 1,
                    last_used_at = ?
                WHERE term = ?
                """,
                [(now, term) for term in terms],
            )
    return terms


def import_tts_terms_json(
    path: str | Path,
    *,
    source: str = "json",
    db_path: str | Path | None = None,
) -> int:
    data = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("TTS terms JSON must be an object mapping term to reading")
    count = 0
    for term, reading in data.items():
        if isinstance(term, str) and isinstance(reading, str) and term.strip() and reading.strip():
            add_tts_term(term, reading, source=source, db_path=db_path)
            count += 1
    return count
