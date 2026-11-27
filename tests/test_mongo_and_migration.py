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
from app.scoring import DatasetKind, SCORING_ROLES
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
                if "$ne" in v and val == v["$ne"]:
                    return False
            elif val != v:
                return False
        return True

    def find_one(self, query: dict[str, Any]) -> dict[str, Any] | None:
        for doc in self.docs.values():
            if self._matches(doc, query):
                return dict(doc)
        return None

    def find(self, query: dict[str, Any], projection: dict[str, Any] | None = None) -> list[dict[str, Any]]:
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

    # Verify export_draft_catalog produces valid CatalogEntry(rarity_id=...)
    from app.scoring import DatasetKind

    eligible_ids = [
        c.character_id
        for c in mdb.list_characters("naruto")
        if c.power is not None and c.fit is not None
    ][:20]
    manifest, _ = mdb.publish_dataset(
        "naruto", "naruto-test-export", kind=DatasetKind.TEST, character_ids=eligible_ids
    )
    catalog, weights, dver = mdb.export_draft_catalog(manifest.dataset_version)
    assert dver == "naruto-test-export"
    assert len(catalog) == 20
    assert catalog[0].rarity_id in weights


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


@pytest.mark.asyncio
async def test_mongo_shared_client_without_uri_and_orphan_lock_recovery(tmp_path: Path) -> None:
    fake_db = _FakeMongoDatabase()

    class _FakeClient:
        def __getitem__(self, name: str) -> _FakeMongoDatabase:
            return fake_db

    # Constructing with client= and no uri= must succeed
    mdb = MongoCharacterDatabase(database_name="kayi_arena", client=_FakeClient())
    mstore = MongoMatchStore(database_name="kayi_arena", client=_FakeClient())

    # Simulate an orphan lock left behind by a crash before match creation
    fake_db["active_player_locks"].insert_one(
        {"_id": "555", "player_id": "555", "match_id": "match-crashed-ghost"}
    )
    assert "555" in mstore.load_active_player_locks()

    mgr = MatchManager(mdb, store=mstore)
    report, *_ = await mgr.recover_from_store()
    assert report.restored_matches == 0
    assert mstore.load_active_player_locks() == {}

    # Terminal match statuses must not be treated as active or have locks recreated
    for term_status in ("forfeited", "inactivity_win", "terminated_admin", "terminated_technical"):
        fake_db["matches"].insert_one(
            {
                "_id": f"match-{term_status}",
                "match_id": f"match-{term_status}",
                "status": term_status,
                "player_1_id": "701",
                "player_2_id": "702",
            }
        )
    assert mstore.load_active_matches() == []
    assert mstore.reconcile_orphan_locks() == 0
    assert mstore.load_active_player_locks() == {}

    # Crash-consistency: pending_commit=True match with partial/full locks & valid lock on another match
    mdb.create_universe("naruto", "Naruto", active=True)
    for idx in range(1, 15):
        c = mdb.add_character(
            character_id=f"c_{idx}",
            universe_id="naruto",
            name=f"Ninja {idx}",
            canonical_version="Base",
            rarity="Common",
            power=3,
            fit={r: 3 for r in SCORING_ROLES},
            image=ImageMetadata(url_or_ref=f"https://cdn.example.org/{idx}.png", status=ImageValidationStatus.VERIFIED),
        )
        mdb.submit_for_review(c.character_id)
        mdb.approve_character(c.character_id)
    mdb.publish_dataset("naruto", "1.0.0")
    _, res_valid = await mgr.handle_draft_command(
        player_id="900", chat_id="-100", universe_arg="naruto", reply_to_user_id="901"
    )
    acc_valid = await mgr.accept_challenge(challenge_id=res_valid.challenge.challenge_id, player_id="901")
    valid_mid = acc_valid.match.match_id

    fake_db["matches"].insert_one(
        {
            "_id": "match-crashed-pending",
            "match_id": "match-crashed-pending",
            "challenge_id": "chl-crashed",
            "status": "drafting",
            "pending_commit": True,
            "player_1_id": "801",
            "player_2_id": "802",
        }
    )
    fake_db["active_player_locks"].insert_one(
        {"_id": "801", "player_id": "801", "match_id": "match-crashed-pending"}
    )
    fake_db["challenges"].insert_one(
        {
            "_id": "chl-crashed",
            "challenge_id": "chl-crashed",
            "challenge_type": "open",
            "challenger_id": "801",
            "target_player_id": None,
            "universe_id": "naruto",
            "game_mode": "ranked",
            "chat_id": "-100",
            "status": "accepted",
            "created_at": 1.0,
            "expires_at": 301.0,
            "generation": 1,
            "accepted_by": "802",
            "match_id": "match-crashed-pending",
        }
    )
    # Incomplete match must never be loaded as active
    assert [m.match_id for m in mstore.load_active_matches()] == [valid_mid]
    # Reconciliation removes pending_commit match + its partial lock, restores challenge to open, preserves valid lock 900
    assert mstore.reconcile_orphan_locks() >= 1
    assert "801" not in mstore.load_active_player_locks()
    assert mstore.load_active_player_locks().get("900") == valid_mid
    assert mstore.load_active_player_locks().get("901") == valid_mid
    restored_chl, _ = mstore.load_challenge("chl-crashed")
    assert restored_chl.status.value == "open"
    assert restored_chl.match_id is None


@pytest.mark.asyncio
async def test_pending_commit_live_conflict_uncertain_writes_and_same_second_publish() -> None:
    from app.database import generate_dataset_version

    fake_db = _FakeMongoDatabase()

    class _FakeClient:
        def __getitem__(self, name: str) -> _FakeMongoDatabase:
            return fake_db

    mdb = MongoCharacterDatabase(database_name="kayi_arena", client=_FakeClient())
    mstore = MongoMatchStore(database_name="kayi_arena", client=_FakeClient())
    mdb.create_universe("naruto", "Naruto", active=True)
    for idx in range(1, 15):
        c = mdb.add_character(
            character_id=f"c_{idx}",
            universe_id="naruto",
            name=f"Ninja {idx}",
            canonical_version="Base",
            rarity="Common",
            power=3,
            fit={r: 3 for r in SCORING_ROLES},
            image=ImageMetadata(url_or_ref=f"https://cdn.example.org/{idx}.png", status=ImageValidationStatus.VERIFIED),
        )
        mdb.submit_for_review(c.character_id)
        mdb.approve_character(c.character_id)

    # 1. Multiple publications within the same second on MongoDB get distinct versions & strict ordering
    v1 = generate_dataset_version("naruto", DatasetKind.PRODUCTION)
    v2 = generate_dataset_version("naruto", DatasetKind.PRODUCTION)
    assert v1 != v2
    m1, _ = mdb.publish_dataset("naruto", v1, kind=DatasetKind.PRODUCTION)
    m2, _ = mdb.publish_dataset("naruto", v2, kind=DatasetKind.PRODUCTION)
    assert mdb.get_latest_published_version("naruto", kind=DatasetKind.PRODUCTION) == v2
    assert mdb.load_manifest(v1).content_hash == m1.content_hash
    assert mdb.load_manifest(v2).content_hash == m2.content_hash

    # 2. Live lock-conflict reconciliation MUST NOT disrupt a fresh in-progress pending_commit in another process
    mgr = MatchManager(mdb, store=mstore)
    _, chl_inprog = await mgr.handle_draft_command(
        player_id="1001", chat_id="-200", universe_arg="naruto", reply_to_user_id="1002"
    )
    import time as _time
    fake_db["matches"].insert_one(
        {
            "_id": "match-other-proc-live",
            "match_id": "match-other-proc-live",
            "challenge_id": "chl-other-proc",
            "status": "drafting",
            "pending_commit": True,
            "pending_since": _time.time(),
            "player_1_id": "1001",
            "player_2_id": "1003",
        }
    )
    fake_db["active_player_locks"].insert_one(
        {"_id": "1001", "player_id": "1001", "match_id": "match-other-proc-live"}
    )
    # Attempting to accept a challenge for player 1001 must fail with PersistenceConflictError, NOT delete the in-progress match/lock
    with pytest.raises(PersistenceConflictError):
        mstore.accept_challenge_and_create_match(
            chl_inprog.challenge,
            (await mgr.accept_challenge(challenge_id=chl_inprog.challenge.challenge_id, player_id="1002")).match
            if False
            else _make_dummy_match("match-competing", chl_inprog.challenge.challenge_id, ("1001", "1002"), v2, mdb),
        )
    assert fake_db["matches"].find_one({"_id": "match-other-proc-live"}) is not None
    assert "1001" in mstore.load_active_player_locks()

    # 3. Uncertain final update (pending_commit=False persisted before exception): match, locks, and challenge stay intact
    fake_db["active_player_locks"].delete_many({})
    fake_db["matches"].delete_many({})
    _, chl_unc = await mgr.handle_draft_command(
        player_id="2001", chat_id="-200", universe_arg="naruto", reply_to_user_id="2002"
    )
    dummy_match = _make_dummy_match("match-uncertain", chl_unc.challenge.challenge_id, ("2001", "2002"), v2, mdb)
    orig_update = fake_db["matches"].update_one

    def _timeout_after_commit(flt, upd, *args, **kwargs):
        orig_update(flt, upd, *args, **kwargs)
        raise TimeoutError("Simulated PyMongo ack timeout after pending_commit=False")

    fake_db["matches"].update_one = _timeout_after_commit  # type: ignore[method-assign]
    mstore.accept_challenge_and_create_match(chl_unc.challenge, dummy_match)
    fake_db["matches"].update_one = orig_update  # type: ignore[method-assign]
    assert [m.match_id for m in mstore.load_active_matches()] == ["match-uncertain"]
    assert mstore.load_active_player_locks().get("2001") == "match-uncertain"
    assert mstore.load_active_player_locks().get("2002") == "match-uncertain"


def _make_dummy_match(match_id: str, challenge_id: str, players: tuple[str, str], dver: str, db: MongoCharacterDatabase):
    from app.engine import start_draft
    from app.matches import ManagedMatch, MatchLifecycleStatus, TimeoutPolicy

    catalog, _, _ = db.export_draft_catalog(dver)
    res = start_draft(
        match_id=match_id,
        players=players,
        universe_id="naruto",
        mode="ranked",
        catalog=catalog,
        rarity_weights=db.get_universe("naruto").rarity_weights,
        dataset_version=dver,
        forced_starter=players[0],
    )
    return ManagedMatch(
        match_id=match_id,
        challenge_id=challenge_id,
        players=players,
        universe_id="naruto",
        game_mode="ranked",
        dataset_version=dver,
        status=MatchLifecycleStatus.DRAFTING,
        draft_snapshot=res.snapshot,
        public_view=res.public_view,
        generation=1,
        turn_started_at=1.0,
        turn_deadline_at=121.0,
        turn_number_at_start=0,
        extensions_remaining={players[0]: 1, players[1]: 1},
        timeout_policy=TimeoutPolicy(),
        created_at=1.0,
        updated_at=1.0,
    )
