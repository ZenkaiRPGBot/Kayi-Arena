"""Optional MongoDB Atlas persistence backend for Kayi Arena.

Implements the same store interface as SqliteMatchStore so callers, MatchManager,
and ArenaTelegramCoordinator work identically with either SQLite (default) or MongoDB.
Never stores image binaries in MongoDB; only lightweight Telegram file_id metadata.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.engine import DraftSnapshot, project_public_view
from app.matches.models import (
    ChallengeRecord,
    ChallengeStatus,
    ChallengeType,
    ManagedMatch,
    MatchLifecycleStatus,
    MessageReference,
)
from app.persistence.models import (
    HistoricalMatchRecord,
    PersistenceError,
    outcome_from_dict,
    outcome_to_dict,
    timeout_policy_from_dict,
    timeout_policy_to_dict,
)

logger = logging.getLogger(__name__)


class PersistenceConflictError(PersistenceError):
    """Raised on active-player lock conflicts or optimistic concurrency mismatches."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _serialize_challenge(c: ChallengeRecord, *, message_id: str | None = None) -> dict[str, Any]:
    return {
        "_id": c.challenge_id,
        "challenge_id": c.challenge_id,
        "challenge_type": c.challenge_type.value,
        "challenger_id": c.challenger_id,
        "target_player_id": c.target_player_id,
        "universe_id": c.universe_id,
        "game_mode": c.game_mode,
        "chat_id": c.chat_id,
        "status": c.status.value,
        "created_at": float(c.created_at),
        "expires_at": float(c.expires_at),
        "generation": int(c.generation),
        "accepted_by": c.accepted_by,
        "match_id": c.match_id,
        "message_id": message_id,
        "updated_at": _utc_now(),
    }


def _doc_to_challenge(doc: dict[str, Any]) -> tuple[ChallengeRecord, str | None]:
    chl = ChallengeRecord(
        challenge_id=str(doc["challenge_id"]),
        challenge_type=ChallengeType(str(doc["challenge_type"])),
        challenger_id=str(doc["challenger_id"]),
        target_player_id=doc.get("target_player_id"),
        universe_id=str(doc["universe_id"]),
        game_mode=str(doc["game_mode"]),
        chat_id=str(doc["chat_id"]),
        status=ChallengeStatus(str(doc["status"])),
        created_at=float(doc["created_at"]),
        expires_at=float(doc["expires_at"]),
        generation=int(doc.get("generation", 1)),
        accepted_by=doc.get("accepted_by"),
        match_id=doc.get("match_id"),
    )
    msg_id = doc.get("message_id")
    return chl, str(msg_id) if msg_id is not None else None


def _serialize_match(m: ManagedMatch) -> dict[str, Any]:
    return {
        "_id": m.match_id,
        "match_id": m.match_id,
        "challenge_id": m.challenge_id,
        "player_1_id": m.players[0],
        "player_2_id": m.players[1],
        "universe_id": m.universe_id,
        "game_mode": m.game_mode,
        "dataset_version": m.dataset_version,
        "status": m.status.value,
        "generation": int(m.generation),
        "draft_revision": int(m.draft_snapshot.revision),
        "turn_started_at": float(m.turn_started_at),
        "turn_deadline_at": float(m.turn_deadline_at),
        "turn_number_at_start": int(m.turn_number_at_start),
        "inactivity_claim_offered_to": m.inactivity_claim_offered_to,
        "inactivity_claim_expires_at": (
            float(m.inactivity_claim_expires_at)
            if m.inactivity_claim_expires_at is not None
            else None
        ),
        "created_at": float(m.created_at),
        "updated_at": float(m.updated_at),
        "draft_snapshot": json.loads(m.draft_snapshot.to_json()),
        "timeout_policy": timeout_policy_to_dict(m.timeout_policy),
        "extensions_remaining": {str(k): int(v) for k, v in m.extensions_remaining.items()},
        "message_refs": [
            {"chat_id": r.chat_id, "message_id": r.message_id, "kind": r.kind}
            for r in m.message_refs
        ],
        "outcome": outcome_to_dict(m.outcome) if m.outcome is not None else None,
    }


def _doc_to_match(doc: dict[str, Any]) -> ManagedMatch:
    snap = DraftSnapshot.from_dict(doc["draft_snapshot"])
    policy = timeout_policy_from_dict(doc["timeout_policy"])
    ext = {str(k): int(v) for k, v in doc.get("extensions_remaining", {}).items()}
    refs = tuple(
        MessageReference(
            chat_id=str(item["chat_id"]),
            message_id=str(item["message_id"]),
            kind=str(item.get("kind", "game")),
        )
        for item in doc.get("message_refs", [])
    )
    outcome_raw = doc.get("outcome")
    outcome = outcome_from_dict(outcome_raw) if outcome_raw else None
    return ManagedMatch(
        match_id=str(doc["match_id"]),
        challenge_id=str(doc["challenge_id"]),
        players=(str(doc["player_1_id"]), str(doc["player_2_id"])),
        universe_id=str(doc["universe_id"]),
        game_mode=str(doc["game_mode"]),
        dataset_version=str(doc["dataset_version"]),
        status=MatchLifecycleStatus(str(doc["status"])),
        draft_snapshot=snap,
        public_view=project_public_view(snap),
        generation=int(doc["generation"]),
        turn_started_at=float(doc["turn_started_at"]),
        turn_deadline_at=float(doc["turn_deadline_at"]),
        turn_number_at_start=int(doc["turn_number_at_start"]),
        extensions_remaining=ext,
        timeout_policy=policy,
        created_at=float(doc["created_at"]),
        updated_at=float(doc["updated_at"]),
        inactivity_claim_offered_to=doc.get("inactivity_claim_offered_to"),
        inactivity_claim_expires_at=doc.get("inactivity_claim_expires_at"),
        message_refs=refs,
        outcome=outcome,
    )


def _serialize_history(rec: HistoricalMatchRecord) -> dict[str, Any]:
    return {
        "_id": rec.match_id,
        "match_id": rec.match_id,
        "universe_id": rec.universe_id,
        "game_mode": rec.game_mode,
        "dataset_version": rec.dataset_version,
        "resolution_version": rec.resolution_version,
        "scoring_version": rec.scoring_version,
        "player_1_id": rec.player_1_id,
        "player_2_id": rec.player_2_id,
        "status": rec.status.value,
        "outcome_reason": rec.outcome_reason.value,
        "winner_id": rec.winner_id,
        "loser_id": rec.loser_id,
        "affects_rating": bool(rec.affects_rating),
        "wins_player_1": rec.wins_player_1,
        "wins_player_2": rec.wins_player_2,
        "draws": rec.draws,
        "total_player_1": rec.total_player_1,
        "total_player_2": rec.total_player_2,
        "decided_by": rec.decided_by,
        "completed_at": float(rec.completed_at),
        "outcome": outcome_to_dict(rec.outcome),
    }


def _doc_to_history(doc: dict[str, Any]) -> HistoricalMatchRecord:
    outcome = outcome_from_dict(doc["outcome"])
    return HistoricalMatchRecord(
        match_id=str(doc["match_id"]),
        universe_id=str(doc["universe_id"]),
        game_mode=str(doc["game_mode"]),
        dataset_version=str(doc["dataset_version"]),
        resolution_version=doc.get("resolution_version"),
        scoring_version=doc.get("scoring_version"),
        player_1_id=str(doc["player_1_id"]),
        player_2_id=str(doc["player_2_id"]),
        status=MatchLifecycleStatus(str(doc["status"])),
        outcome_reason=outcome.reason,
        winner_id=doc.get("winner_id"),
        loser_id=doc.get("loser_id"),
        affects_rating=bool(doc["affects_rating"]),
        wins_player_1=doc.get("wins_player_1"),
        wins_player_2=doc.get("wins_player_2"),
        draws=doc.get("draws"),
        total_player_1=doc.get("total_player_1"),
        total_player_2=doc.get("total_player_2"),
        decided_by=doc.get("decided_by"),
        completed_at=float(doc["completed_at"]),
        outcome=outcome,
    )


class MongoMatchStore:
    """MongoDB Atlas-backed persistence store matching SqliteMatchStore's interface."""

    def __init__(
        self,
        uri: str = "",
        *,
        database_name: str = "kayi_arena",
        client: Any = None,
        database: Any = None,
    ) -> None:
        self._owns_client = False
        if database is not None:
            self._client = client
            self._db = database
        else:
            try:
                from pymongo import MongoClient
            except ImportError as exc:
                raise RuntimeError(
                    "pymongo is required when DB_BACKEND=mongodb. Install pymongo>=4.6."
                ) from exc
            if client is None and not uri:
                raise ValueError("MONGODB_URI is required when DB_BACKEND=mongodb.")
            self._client = client or MongoClient(
                uri,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000,
                socketTimeoutMS=10000,
            )
            self._owns_client = client is None
            self._db = self._client[database_name]
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        try:
            self._db.command("ping")
            self._db["challenges"].create_index([("status", 1), ("created_at", 1)])
            self._db["matches"].create_index([("status", 1), ("updated_at", 1)])
            self._db["match_history"].create_index([("player_1_id", 1), ("completed_at", -1)])
            self._db["match_history"].create_index([("player_2_id", 1), ("completed_at", -1)])
            self._db["media_assets"].create_index([("character_id", 1)])
            self._db["media_assets"].create_index([("universe_id", 1), ("upload_status", 1)])
            self._db["admin_audit_log"].create_index([("created_at", -1)])
        except Exception as exc:
            logger.debug("Index creation skipped or deferred: %s", exc)

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()

    def backup_to(self, dest_path: str | Path) -> None:
        """Export a JSON snapshot of MongoDB collections for local disaster recovery."""
        dest = Path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "exported_at": _utc_now(),
            "challenges": list(self._db["challenges"].find({})),
            "matches": list(self._db["matches"].find({})),
            "active_player_locks": list(self._db["active_player_locks"].find({})),
            "match_history": list(self._db["match_history"].find({})),
            "player_profiles": list(self._db["player_profiles"].find({})),
            "media_assets": list(self._db["media_assets"].find({})),
            "bot_settings": list(self._db["bot_settings"].find({})),
            "known_chats": list(self._db["known_chats"].find({})),
        }
        dest.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    # ------------------------------------------------------------------
    # Challenges
    # ------------------------------------------------------------------

    def save_challenge(self, challenge: ChallengeRecord, *, message_id: str | None = None) -> None:
        if message_id is None:
            existing = self._db["challenges"].find_one({"_id": challenge.challenge_id})
            if existing is not None:
                message_id = existing.get("message_id")
        doc = _serialize_challenge(challenge, message_id=message_id)
        self._db["challenges"].replace_one({"_id": challenge.challenge_id}, doc, upsert=True)

    def set_challenge_message(self, challenge_id: str, chat_id: str, message_id: str) -> None:
        self._db["challenges"].update_one(
            {"_id": challenge_id},
            {"$set": {"chat_id": chat_id, "message_id": str(message_id), "updated_at": _utc_now()}},
        )

    def load_challenge(self, challenge_id: str) -> tuple[ChallengeRecord, str | None] | None:
        doc = self._db["challenges"].find_one({"_id": challenge_id})
        return _doc_to_challenge(doc) if doc is not None else None

    def load_open_challenges(self) -> list[tuple[ChallengeRecord, str | None]]:
        docs = self._db["challenges"].find({"status": ChallengeStatus.OPEN.value})
        items = [_doc_to_challenge(d) for d in docs]
        items.sort(key=lambda pair: pair[0].created_at)
        return items

    # ------------------------------------------------------------------
    # Matches & Active Player Locks
    # ------------------------------------------------------------------

    def accept_challenge_and_create_match(
        self, challenge: ChallengeRecord, match: ManagedMatch
    ) -> None:
        existing_locks = list(
            self._db["active_player_locks"].find({"_id": {"$in": list(match.players)}})
        )
        if existing_locks:
            lock_mids = list({str(l.get("match_id", "")) for l in existing_locks if l.get("match_id")})
            if lock_mids and self._db["matches"].find_one({"_id": {"$in": lock_mids}, "pending_commit": True}) is not None:
                self.reconcile_orphan_locks()
                existing_locks = list(
                    self._db["active_player_locks"].find({"_id": {"$in": list(match.players)}})
                )
        if existing_locks:
            raise PersistenceConflictError(
                f"Active match lock conflict: player {existing_locks[0]['_id']} already locked."
            )
        now = _utc_now()
        acquired: list[str] = []
        match_written = False
        challenge_attempted = False
        try:
            doc = _serialize_match(match)
            doc["pending_commit"] = True
            self._db["matches"].replace_one({"_id": match.match_id}, doc, upsert=True)
            match_written = True
            for pid in match.players:
                self._db["active_player_locks"].insert_one(
                    {"_id": pid, "player_id": pid, "match_id": match.match_id, "updated_at": now}
                )
                acquired.append(pid)
            challenge_attempted = True
            self.save_challenge(challenge)
            self._db["matches"].update_one(
                {"_id": match.match_id}, {"$set": {"pending_commit": False}}
            )
        except Exception as exc:
            if match_written:
                try:
                    current_match = self._db["matches"].find_one({"_id": match.match_id})
                    if current_match is not None and current_match.get("pending_commit") is False:
                        return
                except Exception:
                    pass

            challenge_rolled_back = not challenge_attempted
            if challenge_attempted:
                try:
                    self._db["challenges"].update_one(
                        {
                            "_id": challenge.challenge_id,
                            "status": ChallengeStatus.ACCEPTED.value,
                            "match_id": match.match_id,
                        },
                        {
                            "$set": {
                                "status": ChallengeStatus.OPEN.value,
                                "accepted_by": None,
                                "match_id": None,
                                "updated_at": _utc_now(),
                            }
                        },
                    )
                    challenge_rolled_back = True
                except Exception:
                    challenge_rolled_back = False

            if challenge_rolled_back:
                if acquired:
                    self._db["active_player_locks"].delete_many(
                        {"_id": {"$in": acquired}, "match_id": match.match_id}
                    )
                if match_written:
                    self._db["matches"].delete_many(
                        {"_id": match.match_id, "pending_commit": True}
                    )
            raise PersistenceConflictError(
                f"Active match lock conflict for match {match.match_id}: {exc}"
            ) from exc

    def save_match_transition(
        self,
        match: ManagedMatch,
        *,
        release_players: bool = False,
        history_record: HistoricalMatchRecord | None = None,
        expected_generation: int | None = None,
    ) -> None:
        doc = _serialize_match(match)
        if expected_generation is not None:
            existing = self._db["matches"].find_one({"_id": match.match_id})
            if existing is not None and int(existing.get("generation", 1)) != expected_generation:
                raise PersistenceConflictError(
                    f"Concurrent modification on match {match.match_id}: expected gen {expected_generation}"
                )
        self._db["matches"].replace_one({"_id": match.match_id}, doc, upsert=True)
        if release_players:
            self._db["active_player_locks"].delete_many({"match_id": match.match_id})
        if history_record is not None:
            self._db["match_history"].replace_one(
                {"_id": history_record.match_id},
                _serialize_history(history_record),
                upsert=True,
            )

    def load_match(self, match_id: str) -> ManagedMatch | None:
        doc = self._db["matches"].find_one({"_id": match_id})
        return _doc_to_match(doc) if doc is not None else None

    def load_active_matches(self) -> list[ManagedMatch]:
        docs = self._db["matches"].find(
            {"status": MatchLifecycleStatus.DRAFTING.value, "pending_commit": {"$ne": True}}
        )
        items = [_doc_to_match(d) for d in docs]
        items.sort(key=lambda m: m.created_at)
        return items

    def load_active_player_locks(self) -> dict[str, str]:
        return {
            str(d["player_id"]): str(d["match_id"])
            for d in self._db["active_player_locks"].find({})
        }

    def reconcile_orphan_locks(self) -> int:
        """Clean up incomplete (pending_commit) matches and orphan active_player_locks."""
        removed = 0
        for inc_doc in list(self._db["matches"].find({"pending_commit": True})):
            inc_mid = str(inc_doc.get("match_id", inc_doc.get("_id", "")))
            inc_cid = inc_doc.get("challenge_id")
            if inc_cid and self._db["matches"].find_one({"_id": inc_mid, "pending_commit": True}) is not None:
                self._db["challenges"].update_one(
                    {
                        "_id": inc_cid,
                        "status": ChallengeStatus.ACCEPTED.value,
                        "match_id": inc_mid,
                    },
                    {
                        "$set": {
                            "status": ChallengeStatus.OPEN.value,
                            "accepted_by": None,
                            "match_id": None,
                            "updated_at": _utc_now(),
                        }
                    },
                )
            if self._db["matches"].find_one({"_id": inc_mid, "pending_commit": True}) is not None:
                self._db["active_player_locks"].delete_many({"match_id": inc_mid})
            res = self._db["matches"].delete_many({"_id": inc_mid, "pending_commit": True})
            if res is None or getattr(res, "deleted_count", 0):
                removed += 1

        active_matches = self.load_active_matches()
        active_by_id = {m.match_id: m for m in active_matches}
        for lock_doc in list(self._db["active_player_locks"].find({})):
            mid = str(lock_doc.get("match_id", ""))
            if mid not in active_by_id:
                live_doc = self._db["matches"].find_one(
                    {
                        "_id": mid,
                        "status": MatchLifecycleStatus.DRAFTING.value,
                        "pending_commit": {"$ne": True},
                    }
                )
                if live_doc is None:
                    self._db["active_player_locks"].delete_many(
                        {"_id": lock_doc["_id"], "match_id": mid}
                    )
                    removed += 1
        now = _utc_now()
        for match in active_matches:
            for pid in match.players:
                if self._db["active_player_locks"].find_one({"_id": pid}) is None:
                    self._db["active_player_locks"].replace_one(
                        {"_id": pid},
                        {"_id": pid, "player_id": pid, "match_id": match.match_id, "updated_at": now},
                        upsert=True,
                    )
        return removed

    # ------------------------------------------------------------------
    # History & Profiles
    # ------------------------------------------------------------------

    def get_historical_match(self, match_id: str) -> HistoricalMatchRecord | None:
        doc = self._db["match_history"].find_one({"_id": match_id})
        return _doc_to_history(doc) if doc is not None else None

    def list_match_history(
        self, *, player_id: str | None = None, limit: int = 20, offset: int = 0
    ) -> list[HistoricalMatchRecord]:
        query: dict[str, Any] = {}
        if player_id is not None:
            query = {"$or": [{"player_1_id": player_id}, {"player_2_id": player_id}]}
        docs = list(self._db["match_history"].find(query))
        docs.sort(key=lambda d: float(d.get("completed_at", 0.0)), reverse=True)
        return [_doc_to_history(d) for d in docs[offset : offset + limit]]

    def upsert_player_profile(
        self, player_id: str, display_name: str, username: str | None = None
    ) -> None:
        self._db["player_profiles"].replace_one(
            {"_id": player_id},
            {
                "_id": player_id,
                "player_id": player_id,
                "display_name": display_name,
                "username": username,
                "updated_at": _utc_now(),
            },
            upsert=True,
        )

    def load_player_names(self) -> dict[str, str]:
        return {
            str(d["player_id"]): str(d["display_name"])
            for d in self._db["player_profiles"].find({})
            if d.get("display_name")
        }

    # ------------------------------------------------------------------
    # Media Assets & Cache (metadata only, NO binaries)
    # ------------------------------------------------------------------

    def save_media_cache(
        self,
        media_key: str,
        telegram_file_id: str,
        *,
        character_id: str = "",
        source_ref: str = "",
    ) -> None:
        self.upsert_media_asset(
            media_key=media_key,
            character_id=character_id,
            universe_id="",
            source_url=source_ref,
            telegram_file_id=telegram_file_id,
            upload_status="uploaded",
        )

    def get_media_cache(self, media_key: str) -> str | None:
        doc = self._db["media_assets"].find_one({"_id": media_key})
        if doc and doc.get("upload_status") == "uploaded" and doc.get("telegram_file_id"):
            return str(doc["telegram_file_id"])
        return None

    def upsert_media_asset(
        self,
        *,
        media_key: str,
        character_id: str,
        universe_id: str,
        source_url: str,
        telegram_file_id: str,
        telegram_file_unique_id: str = "",
        channel_id: str = "",
        channel_message_id: int | None = None,
        bot_username: str = "",
        image_hash: str = "",
        verification_status: str = "pending",
        upload_status: str = "uploaded",
        attribution: str = "",
        last_error: str = "",
    ) -> None:
        now = _utc_now()
        self._db["media_assets"].replace_one(
            {"_id": media_key},
            {
                "_id": media_key,
                "media_key": media_key,
                "character_id": character_id,
                "universe_id": universe_id,
                "source_url": source_url,
                "telegram_file_id": telegram_file_id,
                "telegram_file_unique_id": telegram_file_unique_id,
                "channel_id": channel_id,
                "channel_message_id": channel_message_id,
                "bot_username": bot_username,
                "image_hash": image_hash,
                "verification_status": verification_status,
                "upload_status": upload_status,
                "attribution": attribution,
                "last_error": last_error,
                "last_validated_at": now,
                "updated_at": now,
            },
            upsert=True,
        )

    def get_media_asset_by_character(self, character_id: str) -> dict[str, Any] | None:
        docs = list(self._db["media_assets"].find({"character_id": character_id}))
        if not docs:
            return None
        docs.sort(key=lambda d: str(d.get("updated_at", "")), reverse=True)
        return dict(docs[0])

    def get_media_stats(self, universe_id: str | None = None) -> dict[str, int]:
        query = {"universe_id": universe_id} if universe_id else {}
        docs = list(self._db["media_assets"].find(query))
        counts: dict[str, int] = {}
        for d in docs:
            st = str(d.get("upload_status", "pending"))
            counts[st] = counts.get(st, 0) + 1
        return {
            "total": len(docs),
            "uploaded": counts.get("uploaded", 0),
            "pending": counts.get("pending", 0),
            "failed": counts.get("failed", 0),
        }

    # ------------------------------------------------------------------
    # Admin Audit, Settings & Known Chats
    # ------------------------------------------------------------------

    def record_admin_action(
        self,
        *,
        actor_id: str,
        action: str,
        target_type: str = "",
        target_id: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        self._db["admin_audit_log"].insert_one(
            {
                "actor_id": actor_id,
                "action": action,
                "target_type": target_type,
                "target_id": target_id,
                "details": details or {},
                "created_at": _utc_now(),
            }
        )

    def list_admin_audit_log(self, *, limit: int = 20) -> list[dict[str, Any]]:
        docs = list(self._db["admin_audit_log"].find({}))
        docs.sort(key=lambda d: str(d.get("created_at", "")), reverse=True)
        return [dict(d) for d in docs[:limit]]

    def get_setting(self, key: str, default: str = "") -> str:
        doc = self._db["bot_settings"].find_one({"_id": key})
        return str(doc["value"]) if doc is not None and "value" in doc else default

    def set_setting(self, key: str, value: str) -> None:
        self._db["bot_settings"].replace_one(
            {"_id": key},
            {"_id": key, "key": key, "value": str(value), "updated_at": _utc_now()},
            upsert=True,
        )

    def upsert_known_chat(self, chat_id: str, chat_type: str, title: str | None = None) -> None:
        self._db["known_chats"].replace_one(
            {"_id": str(chat_id)},
            {
                "_id": str(chat_id),
                "chat_id": str(chat_id),
                "chat_type": chat_type,
                "title": title,
                "updated_at": _utc_now(),
            },
            upsert=True,
        )

    def list_known_chats(self, *, chat_type: str | None = None) -> list[str]:
        query = {"chat_type": chat_type} if chat_type else {}
        return [str(d["chat_id"]) for d in self._db["known_chats"].find(query)]

    def integrity_check(self) -> tuple[bool, str]:
        try:
            self._db.command("ping")
            return True, "mongodb ok"
        except Exception as exc:
            return False, f"mongodb error: {type(exc).__name__}"

    def get_stats_snapshot(self) -> dict[str, int]:
        return {
            "total_users": self._db["player_profiles"].count_documents({}),
            "private_chats": self._db["known_chats"].count_documents({"chat_type": "private"}),
            "group_chats": self._db["known_chats"].count_documents(
                {"chat_type": {"$in": ["group", "supergroup"]}}
            ),
            "active_matches": self._db["matches"].count_documents(
                {"status": MatchLifecycleStatus.DRAFTING.value}
            ),
            "completed_matches": self._db["matches"].count_documents(
                {"status": {"$ne": MatchLifecycleStatus.DRAFTING.value}}
            ),
            "total_history": self._db["match_history"].count_documents({}),
            "open_challenges": self._db["challenges"].count_documents(
                {"status": ChallengeStatus.OPEN.value}
            ),
        }
