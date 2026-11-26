"""SQLite-to-MongoDB migration utility with dry-run support and BSON size estimation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from app.database import CharacterDatabase
from app.persistence.mongo_store import MongoMatchStore, _serialize_history
from app.persistence.store import SqliteMatchStore


@dataclass(slots=True)
class MigrationReport:
    dry_run: bool = True
    counts_by_collection: dict[str, int] = field(default_factory=dict)
    estimated_bytes: int = 0
    warnings: list[str] = field(default_factory=list)


def _estimate_json_bytes(obj: Any) -> int:
    return len(json.dumps(obj, default=str).encode("utf-8"))


def migrate_sqlite_to_mongo(
    sqlite_store: SqliteMatchStore,
    mongo_store: MongoMatchStore | None = None,
    *,
    char_db: CharacterDatabase | None = None,
    dry_run: bool = True,
) -> MigrationReport:
    """Inspect or migrate SQLite state (and optional character DB) into MongoDB Atlas.

    When dry_run=True, zero writes are executed against MongoDB and an exact
    count + estimated BSON payload size report is returned.
    """
    report = MigrationReport(dry_run=dry_run)
    if not dry_run and mongo_store is None:
        raise ValueError("mongo_store is required when dry_run=False.")

    open_challenges = sqlite_store.load_open_challenges()
    active_matches = sqlite_store.load_active_matches()
    history = sqlite_store.list_match_history(limit=100000, offset=0)
    player_names = sqlite_store.load_player_names()
    known_private = sqlite_store.list_known_chats(chat_type="private")
    known_all = sqlite_store.list_known_chats()
    media_rows = sqlite_store._conn.execute("SELECT * FROM media_assets").fetchall()
    settings_rows = sqlite_store._conn.execute("SELECT key, value FROM bot_settings").fetchall()
    audit_rows = sqlite_store.list_admin_audit_log(limit=10000)

    report.counts_by_collection = {
        "challenges": len(open_challenges),
        "matches": len(active_matches),
        "match_history": len(history),
        "player_profiles": len(player_names),
        "known_chats": len(known_all),
        "media_assets": len(media_rows),
        "bot_settings": len(settings_rows),
        "admin_audit_log": len(audit_rows),
    }

    est_bytes = (
        _estimate_json_bytes([c.challenge_id for c, _ in open_challenges])
        + len(open_challenges) * 450
        + len(active_matches) * 2400
        + len(history) * 1400
        + len(player_names) * 180
        + len(known_all) * 160
        + sum(_estimate_json_bytes(dict(r)) for r in media_rows)
        + sum(_estimate_json_bytes(dict(r)) for r in settings_rows)
        + sum(_estimate_json_bytes(r) for r in audit_rows)
    )

    chars = []
    universes = []
    if char_db is not None:
        universes = char_db.list_universes(active_only=False)
        for u in universes:
            chars.extend(char_db.list_characters(u.universe_id))
        report.counts_by_collection["universes"] = len(universes)
        report.counts_by_collection["characters"] = len(chars)
        est_bytes += len(universes) * 280
        est_bytes += sum(_estimate_json_bytes(c.to_dict()) for c in chars)

    report.estimated_bytes = est_bytes
    if est_bytes > 400 * 1024 * 1024:
        report.warnings.append("Estimated payload exceeds 400 MB; review Atlas M0 512 MB limit.")

    if dry_run or mongo_store is None:
        return report

    for chl, msg_id in open_challenges:
        mongo_store.save_challenge(chl, message_id=msg_id)
    for match in active_matches:
        mongo_store.save_match_transition(match)
    for hrec in history:
        mongo_store._db["match_history"].replace_one(
            {"_id": hrec.match_id},
            _serialize_history(hrec),
            upsert=True,
        )
    for pid, name in player_names.items():
        mongo_store.upsert_player_profile(pid, name)
    private_set = set(known_private)
    for cid in known_all:
        mongo_store.upsert_known_chat(cid, "private" if cid in private_set else "supergroup")
    for row in media_rows:
        r = dict(row)
        mongo_store.upsert_media_asset(
            media_key=str(r["media_key"]),
            character_id=str(r["character_id"]),
            universe_id=str(r["universe_id"]),
            source_url=str(r["source_url"]),
            telegram_file_id=str(r["telegram_file_id"]),
            telegram_file_unique_id=str(r.get("telegram_file_unique_id", "")),
            channel_id=str(r.get("channel_id", "")),
            channel_message_id=r.get("channel_message_id"),
            bot_username=str(r.get("bot_username", "")),
            image_hash=str(r.get("image_hash", "")),
            verification_status=str(r.get("verification_status", "pending")),
            upload_status=str(r.get("upload_status", "uploaded")),
            attribution=str(r.get("attribution", "")),
        )
    for row in settings_rows:
        mongo_store.set_setting(str(row["key"]), str(row["value"]))
    for c in chars:
        mongo_store._db["characters"].replace_one(
            {"_id": c.character_id},
            {"_id": c.character_id, **c.to_dict()},
            upsert=True,
        )

    return report
