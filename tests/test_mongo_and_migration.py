"""Tests for Phase 6: Optional MongoDB Atlas backend & SQLite->MongoDB dry-run migration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.database import (
    CharacterDatabase,
    ImageMetadata,
    ImageValidationStatus,
    MongoCharacterDatabase,
    bootstrap_naruto_database,
    create_character_database,
)
from app.matches import MatchManager
from app.persistence import (
    MongoMatchStore,
    PersistenceConflictError,
    SqliteMatchStore,
    create_match_store,
    migrate_sqlite_to_mongo,
)
from app.scoring import SCORING_ROLES
from app.telegram.config import BotConfig


class _FakeCollection:
    def __init__(self) -> None:
        self.docs: dict[Any, dict[str, Any]] = {}
        self.auto_seq = 0

    def create_index(self, *args: Any, **kwargs: Any) -> None:
        return None

    def _matches(self, doc: dict[str, Any], query: dict[str, Any]) -> bool:
        if not query:
            return True
        if "$or" in query:
            return any(self._matches(doc, sub) for sub in query["$or"])
        for k, v in query.items():
            val = doc.get(k)
            if isinstance(v, dict):
                if "$in" in v and val not in v["$in"]:
                    return False
                if "$nin" in v and val in v["$nin"]:
                    return False
            elif val != v:
                return False
        return True

    def find_one(self, query: dict[str, Any]) -> dict[str, Any] | None:
        for doc in self.docs.values():
            if self._matches(doc, query):
                return dict(doc)
        return None

    def find(self, query: dict[str, Any]) -> list[dict[str, Any]]:
        return [dict(doc) for doc in self.docs.values() if self._matches(doc, query)]

    def replace_one(self, query: dict[str, Any], doc: dict[str, Any], upsert: bool = False) -> None:
        key = query.get("_id")
        if key in self.docs or upsert:
            self.docs[key] = dict(doc)

    def update_one(self, query: dict[str, Any], update: dict[str, Any]) -> None:
        doc = self.find_one(query)
        if doc is not None and "$set" in update:
            doc.update(update["$set"])
            self.docs[doc["_id"]] = doc

    def insert_one(self, doc: dict[str, Any]) -> None:
        self.auto_seq += 1
        key = doc.get("_id", f"auto_{self.auto_seq}")
        stored = dict(doc)
        stored["_id"] = key
        self.docs[key] = stored

    def delete_many(self, query: dict[str, Any]) -> None:
        to_del = [k for k, d in self.docs.items() if self._matches(d, query)]
        for k in to_del:
            del self.docs[k]

    def count_documents(self, query: dict[str, Any]) -> int:
        return len(self.find(query))


class _FakeMongoDatabase:
    def __init__(self) -> None:
        self._cols: dict[str, _FakeCollection] = {}

    def __getitem__(self, name: str) -> _FakeCollection:
        if name not in self._cols:
            self._cols[name] = _FakeCollection()
        return self._cols[name]

    def command(self, cmd: str) -> dict[str, Any]:
        if cmd == "ping":
            return {"ok": 1}
        return {}


def test_create_match_store_defaults_to_sqlite(tmp_path: Path) -> None:
    cfg = BotConfig(
        db_path=str(tmp_path / "chars.sqlite3"),
        match_db_path=str(tmp_path / "state.sqlite3"),
    )
    store = create_match_store(cfg)
    char_db = create_character_database(cfg)
    assert isinstance(store, SqliteMatchStore)
    assert isinstance(char_db, CharacterDatabase)
    store.close()
    char_db.close()


def test_mongo_character_database_naruto_bootstrap_and_dataset_pinning() -> None:
    fake_db = _FakeMongoDatabase()
    mdb = MongoCharacterDatabase(database=fake_db)
    summary1 = bootstrap_naruto_database(mdb)
    assert summary1.total_loaded == 60
    assert summary1.draft_count == 53
    assert summary1.held_count == 7
    assert len(mdb.list_characters("naruto")) == 60

    # Idempotent second bootstrap
    summary2 = bootstrap_naruto_database(mdb)
    assert summary2.total_loaded == 60
    assert len(mdb.list_characters("naruto")) == 60


@pytest.mark.asyncio
async def test_mongo_store_match_lifecycle_cas_and_media_metadata(tmp_path: Path) -> None:
    db = CharacterDatabase(tmp_path / "chars.sqlite3")
    db.create_universe("naruto", "Naruto", active=True)
    for idx in range(1, 15):
        c = db.add_character(
            character_id=f"char_{idx}",
            universe_id="naruto",
            name=f"Ninja {idx}",
            canonical_version="Shippuden",
            rarity="Common",
            power=3,
            fit={r: 3 for r in SCORING_ROLES},
            image=ImageMetadata(
                url_or_ref=f"https://cdn.example.org/{idx}.png",
                status=ImageValidationStatus.VERIFIED,
            ),
        )
        db.submit_for_review(c.character_id)
        db.approve_character(c.character_id)
    db.publish_dataset("naruto", "1.0.0")

    fake_db = _FakeMongoDatabase()
    mstore = MongoMatchStore(database=fake_db)
    assert mstore.integrity_check() == (True, "mongodb ok")

    mgr = MatchManager(db, store=mstore)
    _, res = await mgr.handle_draft_command(
        player_id="100", chat_id="-1001", universe_arg="naruto", reply_to_user_id="200"
    )
    assert res and res.accepted and res.challenge is not None
    acc = await mgr.accept_challenge(challenge_id=res.challenge.challenge_id, player_id="200")
    assert acc.accepted and acc.match is not None

    # Active locks persisted in MongoDB
    locks = mstore.load_active_player_locks()
    assert locks == {"100": acc.match.match_id, "200": acc.match.match_id}

    # CAS generation mismatch raises PersistenceConflictError
    with pytest.raises(PersistenceConflictError):
        mstore.save_match_transition(acc.match, expected_generation=999)

    # Media metadata stored without binaries
    mstore.upsert_media_asset(
        media_key="char_1:url",
        character_id="char_1",
        universe_id="naruto",
        source_url="https://cdn.example.org/1.png",
        telegram_file_id="tg_file_1",
        upload_status="uploaded",
    )
    assert mstore.get_media_cache("char_1:url") == "tg_file_1"
    assert mstore.get_media_stats("naruto")["uploaded"] == 1


@pytest.mark.asyncio
async def test_sqlite_to_mongo_dry_run_and_execute_migration(tmp_path: Path) -> None:
    db = CharacterDatabase(tmp_path / "chars.sqlite3")
    db.create_universe("naruto", "Naruto", active=True)
    c = db.add_character(
        character_id="naruto_1",
        universe_id="naruto",
        name="Naruto",
        canonical_version="Base",
        rarity="Rare",
        power=4,
        fit={r: 4 for r in SCORING_ROLES},
        image=ImageMetadata(
            url_or_ref="https://cdn.example.org/n1.png",
            status=ImageValidationStatus.VERIFIED,
        ),
    )
    db.submit_for_review(c.character_id)
    db.approve_character(c.character_id)

    sstore = SqliteMatchStore(tmp_path / "state.sqlite3")
    sstore.upsert_player_profile("10", "Alice")
    sstore.set_setting("welcome_video_file_id", "VID_123")
    sstore.upsert_media_asset(
        media_key="naruto_1:k",
        character_id="naruto_1",
        universe_id="naruto",
        source_url="https://cdn.example.org/n1.png",
        telegram_file_id="FILE_123",
    )

    fake_db = _FakeMongoDatabase()
    mstore = MongoMatchStore(database=fake_db)

    dry = migrate_sqlite_to_mongo(sstore, mstore, char_db=db, dry_run=True)
    assert dry.dry_run is True
    assert dry.counts_by_collection["player_profiles"] == 1
    assert dry.counts_by_collection["media_assets"] == 1
    assert dry.counts_by_collection["characters"] == 1
    assert dry.estimated_bytes > 0
    assert fake_db["player_profiles"].count_documents({}) == 0

    real = migrate_sqlite_to_mongo(sstore, mstore, char_db=db, dry_run=False)
    assert real.dry_run is False
    assert mstore.load_player_names() == {"10": "Alice"}
    assert mstore.get_setting("welcome_video_file_id") == "VID_123"
    assert mstore.get_media_cache("naruto_1:k") == "FILE_123"
    assert fake_db["characters"].count_documents({}) == 1
