from __future__ import annotations

import sqlite3
from pathlib import Path

from jobpipe.storage.migrations import apply_migrations, get_schema_version


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def initialize_database(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with connect(db_path) as conn:
        apply_migrations(conn)
        conn.commit()


def schema_version(db_path: Path) -> int:
    with connect(db_path) as conn:
        return get_schema_version(conn)
