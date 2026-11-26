"""Kayi Arena — Module 7: Durable Persistence & Recovery public API."""

from pathlib import Path
from typing import Any

from app.persistence.migrate import MigrationReport, migrate_sqlite_to_mongo
from app.persistence.models import (
    CorruptStateError,
    HistoricalMatchRecord,
    PersistenceError,
    StartupRecoveryReport,
)
from app.persistence.mongo_store import MongoMatchStore, PersistenceConflictError
from app.persistence.store import SCHEMA_VERSION, SqliteMatchStore


def create_match_store(config: Any) -> SqliteMatchStore | MongoMatchStore:
    """Create the configured match store (SQLite default, optional MongoDB Atlas)."""
    backend = str(getattr(config, "db_backend", "sqlite")).lower()
    mongo_uri = str(getattr(config, "mongodb_uri", "")).strip()
    if backend == "mongodb" and mongo_uri:
        return MongoMatchStore(
            mongo_uri,
            database_name=str(getattr(config, "mongodb_database", "kayi_arena") or "kayi_arena"),
        )
    state_db_path = Path(str(getattr(config, "match_db_path", "data/kayi_arena_state.sqlite3")))
    state_db_path.parent.mkdir(parents=True, exist_ok=True)
    return SqliteMatchStore(state_db_path)


__all__ = [
    "CorruptStateError",
    "HistoricalMatchRecord",
    "MigrationReport",
    "MongoMatchStore",
    "PersistenceConflictError",
    "PersistenceError",
    "SCHEMA_VERSION",
    "SqliteMatchStore",
    "StartupRecoveryReport",
    "create_match_store",
    "migrate_sqlite_to_mongo",
]
