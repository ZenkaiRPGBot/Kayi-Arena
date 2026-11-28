"""SQLite durable persistence store for Kayi Arena (Module 7).

Provides versioned schema migrations, atomic transactions (`BEGIN IMMEDIATE`),
active-player global lock enforcement at the database level, and historical
match storage for Module 8.
"""

from __future__ import annotations

import json
import sqlite3
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
    COUNTED_HISTORY_STATUSES,
    CorruptStateError,
    HistoricalMatchRecord,
    PersistenceError,
    PlayerStatsSummary,
    display_state_from_dict,
    display_state_to_dict,
    outcome_from_dict,
    outcome_to_dict,
    summarize_player_records,
    timeout_policy_from_dict,
    timeout_policy_to_dict,
)

SCHEMA_VERSION = 4

_MIGRATIONS: dict[int, tuple[str, ...]] = {
    1: (
        """
        CREATE TABLE IF NOT EXISTS challenges (
            challenge_id TEXT PRIMARY KEY,
            challenge_type TEXT NOT NULL,
            challenger_id TEXT NOT NULL,
            target_player_id TEXT,
            universe_id TEXT NOT NULL,
            game_mode TEXT NOT NULL,
            chat_id TEXT NOT NULL,
            message_id TEXT,
            status TEXT NOT NULL,
            created_at REAL NOT NULL,
            expires_at REAL NOT NULL,
            generation INTEGER NOT NULL,
            accepted_by TEXT,
            match_id TEXT
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_challenges_status ON challenges(status)",
        """
        CREATE TABLE IF NOT EXISTS matches (
            match_id TEXT PRIMARY KEY,
            challenge_id TEXT NOT NULL,
            player_1_id TEXT NOT NULL,
            player_2_id TEXT NOT NULL,
            universe_id TEXT NOT NULL,
            game_mode TEXT NOT NULL,
            dataset_version TEXT NOT NULL,
            status TEXT NOT NULL,
            generation INTEGER NOT NULL,
            draft_revision INTEGER NOT NULL,
            turn_started_at REAL NOT NULL,
            turn_deadline_at REAL NOT NULL,
            turn_number_at_start INTEGER NOT NULL,
            inactivity_claim_offered_to TEXT,
            inactivity_claim_expires_at REAL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            draft_snapshot_json TEXT NOT NULL,
            timeout_policy_json TEXT NOT NULL,
            extensions_remaining_json TEXT NOT NULL,
            message_refs_json TEXT NOT NULL,
            outcome_json TEXT
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_matches_status ON matches(status)",
        """
        CREATE TABLE IF NOT EXISTS active_player_locks (
            player_id TEXT PRIMARY KEY,
            match_id TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS player_profiles (
            player_id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            username TEXT,
            updated_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS match_history (
            match_id TEXT PRIMARY KEY,
            universe_id TEXT NOT NULL,
            game_mode TEXT NOT NULL,
            dataset_version TEXT NOT NULL,
            resolution_version TEXT,
            scoring_version TEXT,
            player_1_id TEXT NOT NULL,
            player_2_id TEXT NOT NULL,
            status TEXT NOT NULL,
            outcome_reason TEXT NOT NULL,
            winner_id TEXT,
            loser_id TEXT,
            affects_rating INTEGER NOT NULL,
            wins_player_1 INTEGER,
            wins_player_2 INTEGER,
            draws INTEGER,
            total_player_1 INTEGER,
            total_player_2 INTEGER,
            decided_by TEXT,
            completed_at REAL NOT NULL,
            outcome_json TEXT NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_history_p1 ON match_history(player_1_id, completed_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_history_p2 ON match_history(player_2_id, completed_at DESC)",
        """
        CREATE TABLE IF NOT EXISTS media_cache (
            media_key TEXT PRIMARY KEY,
            character_id TEXT,
            telegram_file_id TEXT NOT NULL,
            source_ref TEXT,
            updated_at TEXT NOT NULL
        )
        """,
    ),
    2: (
        """
        CREATE TABLE IF NOT EXISTS admin_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_id TEXT NOT NULL,
            action TEXT NOT NULL,
            target_type TEXT NOT NULL,
            target_id TEXT NOT NULL,
            details_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_audit_created ON admin_audit_log(id DESC)",
        """
        CREATE TABLE IF NOT EXISTS bot_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS known_chats (
            chat_id TEXT PRIMARY KEY,
            chat_type TEXT NOT NULL,
            title TEXT,
            updated_at TEXT NOT NULL
        )
        """,
    ),
    3: (
        """
        CREATE TABLE IF NOT EXISTS media_assets (
            media_key TEXT PRIMARY KEY,
            character_id TEXT NOT NULL,
            universe_id TEXT NOT NULL,
            source_url TEXT NOT NULL,
            telegram_file_id TEXT NOT NULL,
            telegram_file_unique_id TEXT NOT NULL,
            channel_id TEXT NOT NULL,
            channel_message_id INTEGER,
            bot_username TEXT NOT NULL,
            image_hash TEXT NOT NULL,
            verification_status TEXT NOT NULL,
            upload_status TEXT NOT NULL,
            attribution TEXT NOT NULL,
            last_validated_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_media_assets_char ON media_assets(character_id)",
        "CREATE INDEX IF NOT EXISTS idx_media_assets_univ ON media_assets(universe_id, upload_status)",
    ),
    4: (
        "ALTER TABLE matches ADD COLUMN display_state_json TEXT NOT NULL DEFAULT '{}'",
    ),
}


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SqliteMatchStore:
    """Durable SQLite persistence store for challenges, active matches, and history."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._db_path = str(db_path)
        if self._db_path != ":memory:":
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, isolation_level=None, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._configure_pragmas()
        self._run_migrations()

    def _configure_pragmas(self) -> None:
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA busy_timeout = 5000")
        if self._db_path != ":memory:":
            self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.execute("PRAGMA synchronous = NORMAL")

    def _run_migrations(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )
        applied = {
            int(row["version"])
            for row in self._conn.execute("SELECT version FROM schema_migrations").fetchall()
        }
        for version in sorted(_MIGRATIONS):
            if version in applied:
                continue
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                for stmt in _MIGRATIONS[version]:
                    self._conn.execute(stmt)
                self._conn.execute(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                    (version, _utc_iso()),
                )
                self._conn.execute("COMMIT")
            except Exception as exc:
                self._conn.execute("ROLLBACK")
                raise PersistenceError(f"Migration v{version} failed: {exc}") from exc

    def current_schema_version(self) -> int:
        row = self._conn.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()
        return int(row["v"]) if row and row["v"] is not None else 0

    def close(self) -> None:
        self._conn.close()

    def backup_to(self, dest_path: str | Path) -> None:
        dest = Path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        target = sqlite3.connect(str(dest))
        try:
            self._conn.backup(target)
        finally:
            target.close()

    # ------------------------------------------------------------------
    # Challenges
    # ------------------------------------------------------------------

    def save_challenge(self, challenge: ChallengeRecord, *, message_id: str | None = None) -> None:
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            self._upsert_challenge_in_tx(challenge, message_id=message_id)
            self._conn.execute("COMMIT")
        except Exception as exc:
            self._conn.execute("ROLLBACK")
            raise PersistenceError(f"Failed saving challenge {challenge.challenge_id}: {exc}") from exc

    def _upsert_challenge_in_tx(
        self, challenge: ChallengeRecord, *, message_id: str | None = None
    ) -> None:
        if message_id is None:
            existing = self._conn.execute(
                "SELECT message_id FROM challenges WHERE challenge_id = ?",
                (challenge.challenge_id,),
            ).fetchone()
            if existing is not None:
                message_id = existing["message_id"]

        self._conn.execute(
            """
            INSERT INTO challenges (
                challenge_id, challenge_type, challenger_id, target_player_id,
                universe_id, game_mode, chat_id, message_id, status,
                created_at, expires_at, generation, accepted_by, match_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(challenge_id) DO UPDATE SET
                challenge_type = excluded.challenge_type,
                challenger_id = excluded.challenger_id,
                target_player_id = excluded.target_player_id,
                universe_id = excluded.universe_id,
                game_mode = excluded.game_mode,
                chat_id = excluded.chat_id,
                message_id = COALESCE(excluded.message_id, challenges.message_id),
                status = excluded.status,
                created_at = excluded.created_at,
                expires_at = excluded.expires_at,
                generation = excluded.generation,
                accepted_by = excluded.accepted_by,
                match_id = excluded.match_id
            """,
            (
                challenge.challenge_id,
                challenge.challenge_type.value,
                challenge.challenger_id,
                challenge.target_player_id,
                challenge.universe_id,
                challenge.game_mode,
                challenge.chat_id,
                message_id,
                challenge.status.value,
                float(challenge.created_at),
                float(challenge.expires_at),
                int(challenge.generation),
                challenge.accepted_by,
                challenge.match_id,
            ),
        )

    def set_challenge_message(self, challenge_id: str, chat_id: str, message_id: str) -> None:
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            self._conn.execute(
                "UPDATE challenges SET chat_id = ?, message_id = ? WHERE challenge_id = ?",
                (chat_id, message_id, challenge_id),
            )
            self._conn.execute("COMMIT")
        except Exception as exc:
            self._conn.execute("ROLLBACK")
            raise PersistenceError(f"Failed updating challenge message ref: {exc}") from exc

    def _row_to_challenge(self, row: sqlite3.Row) -> tuple[ChallengeRecord, str | None]:
        try:
            chl = ChallengeRecord(
                challenge_id=str(row["challenge_id"]),
                challenge_type=ChallengeType(str(row["challenge_type"])),
                challenger_id=str(row["challenger_id"]),
                target_player_id=row["target_player_id"],
                universe_id=str(row["universe_id"]),
                game_mode=str(row["game_mode"]),
                chat_id=str(row["chat_id"]),
                status=ChallengeStatus(str(row["status"])),
                created_at=float(row["created_at"]),
                expires_at=float(row["expires_at"]),
                generation=int(row["generation"]),
                accepted_by=row["accepted_by"],
                match_id=row["match_id"],
            )
            return chl, row["message_id"]
        except Exception as exc:
            raise CorruptStateError(f"Corrupt challenge row {row['challenge_id']}: {exc}") from exc

    def load_challenge(self, challenge_id: str) -> tuple[ChallengeRecord, str | None] | None:
        row = self._conn.execute(
            "SELECT * FROM challenges WHERE challenge_id = ?", (challenge_id,)
        ).fetchone()
        return self._row_to_challenge(row) if row is not None else None

    def load_open_challenges(self) -> list[tuple[ChallengeRecord, str | None]]:
        rows = self._conn.execute(
            "SELECT * FROM challenges WHERE status = ? ORDER BY created_at ASC",
            (ChallengeStatus.OPEN.value,),
        ).fetchall()
        return [self._row_to_challenge(r) for r in rows]

    # ------------------------------------------------------------------
    # Matches & Atomic Locks
    # ------------------------------------------------------------------

    def accept_challenge_and_create_match(
        self, challenge: ChallengeRecord, match: ManagedMatch
    ) -> None:
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            self._upsert_challenge_in_tx(challenge)
            for pid in match.players:
                self._conn.execute(
                    "INSERT INTO active_player_locks (player_id, match_id) VALUES (?, ?)",
                    (pid, match.match_id),
                )
            self._upsert_match_in_tx(match)
            self._conn.execute("COMMIT")
        except sqlite3.IntegrityError as exc:
            self._conn.execute("ROLLBACK")
            raise PersistenceError(f"Active match lock conflict: {exc}") from exc
        except Exception as exc:
            self._conn.execute("ROLLBACK")
            raise PersistenceError(f"Failed accepting challenge {challenge.challenge_id}: {exc}") from exc

    def save_match_transition(
        self,
        match: ManagedMatch,
        *,
        release_players: bool = False,
        history_record: HistoricalMatchRecord | None = None,
    ) -> None:
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            self._upsert_match_in_tx(match)
            if release_players:
                self._conn.execute(
                    "DELETE FROM active_player_locks WHERE match_id = ?",
                    (match.match_id,),
                )
            if history_record is not None:
                self._insert_history_in_tx(history_record)
            self._conn.execute("COMMIT")
        except Exception as exc:
            self._conn.execute("ROLLBACK")
            raise PersistenceError(f"Failed saving match {match.match_id}: {exc}") from exc

    def _upsert_match_in_tx(self, match: ManagedMatch) -> None:
        refs_json = json.dumps(
            [{"chat_id": r.chat_id, "message_id": r.message_id, "kind": r.kind} for r in match.message_refs],
            separators=(",", ":"),
        )
        policy_json = json.dumps(timeout_policy_to_dict(match.timeout_policy), separators=(",", ":"))
        ext_json = json.dumps(
            {str(k): int(v) for k, v in match.extensions_remaining.items()},
            separators=(",", ":"),
        )
        outcome_json = (
            json.dumps(outcome_to_dict(match.outcome), separators=(",", ":"))
            if match.outcome is not None
            else None
        )
        snap_json = match.draft_snapshot.to_json()
        display_json = json.dumps(display_state_to_dict(match.display_state), separators=(",", ":"))

        self._conn.execute(
            """
            INSERT INTO matches (
                match_id, challenge_id, player_1_id, player_2_id, universe_id,
                game_mode, dataset_version, status, generation, draft_revision,
                turn_started_at, turn_deadline_at, turn_number_at_start,
                inactivity_claim_offered_to, inactivity_claim_expires_at,
                created_at, updated_at, draft_snapshot_json, timeout_policy_json,
                extensions_remaining_json, message_refs_json, outcome_json, display_state_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(match_id) DO UPDATE SET
                status = excluded.status,
                generation = excluded.generation,
                draft_revision = excluded.draft_revision,
                turn_started_at = excluded.turn_started_at,
                turn_deadline_at = excluded.turn_deadline_at,
                turn_number_at_start = excluded.turn_number_at_start,
                inactivity_claim_offered_to = excluded.inactivity_claim_offered_to,
                inactivity_claim_expires_at = excluded.inactivity_claim_expires_at,
                updated_at = excluded.updated_at,
                draft_snapshot_json = excluded.draft_snapshot_json,
                timeout_policy_json = excluded.timeout_policy_json,
                extensions_remaining_json = excluded.extensions_remaining_json,
                message_refs_json = excluded.message_refs_json,
                outcome_json = excluded.outcome_json,
                display_state_json = excluded.display_state_json
            """,
            (
                match.match_id,
                match.challenge_id,
                match.players[0],
                match.players[1],
                match.universe_id,
                match.game_mode,
                match.dataset_version,
                match.status.value,
                int(match.generation),
                int(match.draft_snapshot.revision),
                float(match.turn_started_at),
                float(match.turn_deadline_at),
                int(match.turn_number_at_start),
                match.inactivity_claim_offered_to,
                float(match.inactivity_claim_expires_at)
                if match.inactivity_claim_expires_at is not None
                else None,
                float(match.created_at),
                float(match.updated_at),
                snap_json,
                policy_json,
                ext_json,
                refs_json,
                outcome_json,
                display_json,
            ),
        )

    def _row_to_match(self, row: sqlite3.Row) -> ManagedMatch:
        try:
            snap = DraftSnapshot.from_dict(json.loads(row["draft_snapshot_json"]))
            policy = timeout_policy_from_dict(json.loads(row["timeout_policy_json"]))
            ext = {str(k): int(v) for k, v in json.loads(row["extensions_remaining_json"]).items()}
            refs = tuple(
                MessageReference(
                    chat_id=str(item["chat_id"]),
                    message_id=str(item["message_id"]),
                    kind=str(item.get("kind", "game")),
                )
                for item in json.loads(row["message_refs_json"])
            )
            outcome_raw = row["outcome_json"]
            outcome = outcome_from_dict(json.loads(outcome_raw)) if outcome_raw else None
            display_raw = (
                row["display_state_json"]
                if "display_state_json" in row.keys() and row["display_state_json"]
                else None
            )
            display_state = display_state_from_dict(json.loads(display_raw)) if display_raw else display_state_from_dict(None)
            return ManagedMatch(
                match_id=str(row["match_id"]),
                challenge_id=str(row["challenge_id"]),
                players=(str(row["player_1_id"]), str(row["player_2_id"])),
                universe_id=str(row["universe_id"]),
                game_mode=str(row["game_mode"]),
                dataset_version=str(row["dataset_version"]),
                status=MatchLifecycleStatus(str(row["status"])),
                draft_snapshot=snap,
                public_view=project_public_view(snap),
                generation=int(row["generation"]),
                turn_started_at=float(row["turn_started_at"]),
                turn_deadline_at=float(row["turn_deadline_at"]),
                turn_number_at_start=int(row["turn_number_at_start"]),
                extensions_remaining=ext,
                timeout_policy=policy,
                created_at=float(row["created_at"]),
                updated_at=float(row["updated_at"]),
                inactivity_claim_offered_to=row["inactivity_claim_offered_to"],
                inactivity_claim_expires_at=row["inactivity_claim_expires_at"],
                message_refs=refs,
                outcome=outcome,
                display_state=display_state,
            )
        except Exception as exc:
            raise CorruptStateError(f"Corrupt match row {row['match_id']}: {exc}") from exc

    def load_match(self, match_id: str) -> ManagedMatch | None:
        row = self._conn.execute("SELECT * FROM matches WHERE match_id = ?", (match_id,)).fetchone()
        return self._row_to_match(row) if row is not None else None

    def load_active_matches(self) -> list[ManagedMatch]:
        rows = self._conn.execute(
            "SELECT * FROM matches WHERE status = ? ORDER BY created_at ASC",
            (MatchLifecycleStatus.DRAFTING.value,),
        ).fetchall()
        return [self._row_to_match(r) for r in rows]

    def load_active_player_locks(self) -> dict[str, str]:
        rows = self._conn.execute("SELECT player_id, match_id FROM active_player_locks").fetchall()
        return {str(r["player_id"]): str(r["match_id"]) for r in rows}

    def reconcile_orphan_locks(self) -> int:
        return 0

    # ------------------------------------------------------------------
    # Historical Match Records
    # ------------------------------------------------------------------

    def _insert_history_in_tx(self, rec: HistoricalMatchRecord) -> None:
        self._conn.execute(
            """
            INSERT INTO match_history (
                match_id, universe_id, game_mode, dataset_version,
                resolution_version, scoring_version, player_1_id, player_2_id,
                status, outcome_reason, winner_id, loser_id, affects_rating,
                wins_player_1, wins_player_2, draws, total_player_1, total_player_2,
                decided_by, completed_at, outcome_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(match_id) DO NOTHING
            """,
            (
                rec.match_id,
                rec.universe_id,
                rec.game_mode,
                rec.dataset_version,
                rec.resolution_version,
                rec.scoring_version,
                rec.player_1_id,
                rec.player_2_id,
                rec.status.value,
                rec.outcome_reason.value,
                rec.winner_id,
                rec.loser_id,
                1 if rec.affects_rating else 0,
                rec.wins_player_1,
                rec.wins_player_2,
                rec.draws,
                rec.total_player_1,
                rec.total_player_2,
                rec.decided_by,
                float(rec.completed_at),
                json.dumps(outcome_to_dict(rec.outcome), separators=(",", ":")),
            ),
        )

    def _row_to_history(self, row: sqlite3.Row) -> HistoricalMatchRecord:
        return HistoricalMatchRecord(
            match_id=str(row["match_id"]),
            universe_id=str(row["universe_id"]),
            game_mode=str(row["game_mode"]),
            dataset_version=str(row["dataset_version"]),
            resolution_version=row["resolution_version"],
            scoring_version=row["scoring_version"],
            player_1_id=str(row["player_1_id"]),
            player_2_id=str(row["player_2_id"]),
            status=MatchLifecycleStatus(str(row["status"])),
            outcome_reason=outcome_from_dict(json.loads(row["outcome_json"])).reason,
            winner_id=row["winner_id"],
            loser_id=row["loser_id"],
            affects_rating=bool(row["affects_rating"]),
            wins_player_1=row["wins_player_1"],
            wins_player_2=row["wins_player_2"],
            draws=row["draws"],
            total_player_1=row["total_player_1"],
            total_player_2=row["total_player_2"],
            decided_by=row["decided_by"],
            completed_at=float(row["completed_at"]),
            outcome=outcome_from_dict(json.loads(row["outcome_json"])),
        )

    def get_historical_match(self, match_id: str) -> HistoricalMatchRecord | None:
        row = self._conn.execute(
            "SELECT * FROM match_history WHERE match_id = ?", (match_id,)
        ).fetchone()
        return self._row_to_history(row) if row is not None else None

    def list_match_history(
        self, player_id: str | None = None, *, limit: int = 20, offset: int = 0
    ) -> list[HistoricalMatchRecord]:
        if player_id is None:
            rows = self._conn.execute(
                "SELECT * FROM match_history ORDER BY completed_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT * FROM match_history
                WHERE player_1_id = ? OR player_2_id = ?
                ORDER BY completed_at DESC LIMIT ? OFFSET ?
                """,
                (player_id, player_id, limit, offset),
            ).fetchall()
        return [self._row_to_history(r) for r in rows]

    def query_player_history(
        self,
        player_id: str,
        *,
        game_mode: str = "ranked",
        universe_id: str | None = None,
        limit: int = 5,
        offset: int = 0,
    ) -> tuple[list[HistoricalMatchRecord], int]:
        statuses = tuple(s.value for s in COUNTED_HISTORY_STATUSES)
        placeholders = ",".join("?" for _ in statuses)
        where = (
            f"(player_1_id = ? OR player_2_id = ?) AND game_mode = ? "
            f"AND status IN ({placeholders})"
        )
        params: list[Any] = [player_id, player_id, game_mode, *statuses]
        if universe_id and universe_id != "all":
            where += " AND universe_id = ?"
            params.append(universe_id)

        total_row = self._conn.execute(
            f"SELECT COUNT(*) AS cnt FROM match_history WHERE {where}",
            tuple(params),
        ).fetchone()
        total = int(total_row["cnt"]) if total_row is not None else 0

        rows = self._conn.execute(
            f"""
            SELECT * FROM match_history
            WHERE {where}
            ORDER BY completed_at DESC, match_id DESC
            LIMIT ? OFFSET ?
            """,
            (*params, max(1, int(limit)), max(0, int(offset))),
        ).fetchall()
        return [self._row_to_history(r) for r in rows], total

    def compute_player_statistics(
        self,
        player_id: str,
        *,
        game_mode: str = "ranked",
        universe_id: str | None = None,
    ) -> PlayerStatsSummary:
        statuses = tuple(s.value for s in COUNTED_HISTORY_STATUSES)
        placeholders = ",".join("?" for _ in statuses)
        where = (
            f"(player_1_id = ? OR player_2_id = ?) AND game_mode = ? "
            f"AND status IN ({placeholders})"
        )
        params: list[Any] = [player_id, player_id, game_mode, *statuses]
        if universe_id and universe_id != "all":
            where += " AND universe_id = ?"
            params.append(universe_id)
        rows = self._conn.execute(
            f"SELECT * FROM match_history WHERE {where} ORDER BY completed_at ASC, match_id ASC",
            tuple(params),
        ).fetchall()
        return summarize_player_records([self._row_to_history(r) for r in rows], player_id)

    def list_player_history_universes(self, player_id: str) -> list[str]:
        statuses = tuple(s.value for s in COUNTED_HISTORY_STATUSES)
        placeholders = ",".join("?" for _ in statuses)
        rows = self._conn.execute(
            f"""
            SELECT DISTINCT universe_id FROM match_history
            WHERE (player_1_id = ? OR player_2_id = ?) AND status IN ({placeholders})
            ORDER BY universe_id ASC
            """,
            (player_id, player_id, *statuses),
        ).fetchall()
        return [str(r["universe_id"]) for r in rows]

    def get_match_duration_seconds(self, match_id: str) -> float | None:
        row = self._conn.execute(
            "SELECT created_at, updated_at FROM matches WHERE match_id = ?",
            (match_id,),
        ).fetchone()
        if row is None:
            return None
        return max(0.0, float(row["updated_at"]) - float(row["created_at"]))

    def get_player_display_names(self, player_ids: list[str] | tuple[str, ...]) -> dict[str, str]:
        cleaned = [str(pid) for pid in player_ids if pid]
        if not cleaned:
            return {}
        placeholders = ",".join("?" for _ in cleaned)
        rows = self._conn.execute(
            f"SELECT player_id, display_name FROM player_profiles WHERE player_id IN ({placeholders})",
            tuple(cleaned),
        ).fetchall()
        return {str(r["player_id"]): str(r["display_name"]) for r in rows}

    # ------------------------------------------------------------------
    # Player Profiles & Media Cache
    # ------------------------------------------------------------------

    def upsert_player_profile(
        self, player_id: str, display_name: str, username: str | None = None
    ) -> None:
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            self._conn.execute(
                """
                INSERT INTO player_profiles (player_id, display_name, username, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(player_id) DO UPDATE SET
                    display_name = excluded.display_name,
                    username = COALESCE(excluded.username, player_profiles.username),
                    updated_at = excluded.updated_at
                """,
                (player_id, display_name, username, _utc_iso()),
            )
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")

    def load_player_names(self) -> dict[str, str]:
        rows = self._conn.execute("SELECT player_id, display_name FROM player_profiles").fetchall()
        return {str(r["player_id"]): str(r["display_name"]) for r in rows}

    def save_media_cache(
        self,
        media_key: str,
        telegram_file_id: str,
        *,
        character_id: str | None = None,
        source_ref: str = "",
    ) -> None:
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            self._conn.execute(
                """
                INSERT INTO media_cache (media_key, character_id, telegram_file_id, source_ref, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(media_key) DO UPDATE SET
                    telegram_file_id = excluded.telegram_file_id,
                    updated_at = excluded.updated_at
                """,
                (media_key, character_id, telegram_file_id, source_ref, _utc_iso()),
            )
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")

    def get_media_cache(self, media_key: str) -> str | None:
        row = self._conn.execute(
            "SELECT telegram_file_id FROM media_assets WHERE media_key = ? AND upload_status = 'uploaded'",
            (media_key,),
        ).fetchone()
        if row is not None and row["telegram_file_id"]:
            return str(row["telegram_file_id"])
        row2 = self._conn.execute(
            "SELECT telegram_file_id FROM media_cache WHERE media_key = ?", (media_key,)
        ).fetchone()
        return str(row2["telegram_file_id"]) if row2 is not None else None

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
        now = _utc_iso()
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            self._conn.execute(
                """
                INSERT INTO media_assets (
                    media_key, character_id, universe_id, source_url,
                    telegram_file_id, telegram_file_unique_id, channel_id,
                    channel_message_id, bot_username, image_hash,
                    verification_status, upload_status, attribution,
                    last_validated_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(media_key) DO UPDATE SET
                    source_url = excluded.source_url,
                    telegram_file_id = excluded.telegram_file_id,
                    telegram_file_unique_id = excluded.telegram_file_unique_id,
                    channel_id = excluded.channel_id,
                    channel_message_id = excluded.channel_message_id,
                    bot_username = excluded.bot_username,
                    image_hash = excluded.image_hash,
                    verification_status = excluded.verification_status,
                    upload_status = excluded.upload_status,
                    attribution = excluded.attribution,
                    last_validated_at = excluded.last_validated_at,
                    updated_at = excluded.updated_at
                """,
                (
                    media_key,
                    character_id,
                    universe_id,
                    source_url,
                    telegram_file_id,
                    telegram_file_unique_id,
                    channel_id,
                    channel_message_id,
                    bot_username,
                    image_hash,
                    verification_status,
                    upload_status,
                    attribution,
                    now,
                    now,
                ),
            )
            self._conn.execute("COMMIT")
        except Exception as exc:
            self._conn.execute("ROLLBACK")
            raise PersistenceError(f"Failed saving media asset {media_key}: {exc}") from exc

    def get_media_asset_by_character(self, character_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM media_assets WHERE character_id = ? ORDER BY updated_at DESC LIMIT 1",
            (character_id,),
        ).fetchone()
        return dict(row) if row is not None else None

    def get_media_stats(self, universe_id: str | None = None) -> dict[str, int]:
        where = "WHERE universe_id = ?" if universe_id else ""
        params = (universe_id,) if universe_id else ()
        rows = self._conn.execute(
            f"SELECT upload_status, COUNT(*) AS cnt FROM media_assets {where} GROUP BY upload_status",
            params,
        ).fetchall()
        counts = {str(r["upload_status"]): int(r["cnt"]) for r in rows}
        return {
            "total": sum(counts.values()),
            "uploaded": counts.get("uploaded", 0),
            "pending": counts.get("pending", 0),
            "failed": counts.get("failed", 0),
        }

    # ------------------------------------------------------------------
    # Admin Audit Log, Settings, Known Chats, Diagnostics & Stats (v2)
    # ------------------------------------------------------------------

    def record_admin_action(
        self,
        *,
        actor_id: str,
        action: str,
        target_type: str,
        target_id: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            self._conn.execute(
                """
                INSERT INTO admin_audit_log (actor_id, action, target_type, target_id, details_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    actor_id,
                    action,
                    target_type,
                    target_id,
                    json.dumps(details or {}, separators=(",", ":")),
                    _utc_iso(),
                ),
            )
            self._conn.execute("COMMIT")
        except Exception as exc:
            self._conn.execute("ROLLBACK")
            raise PersistenceError(f"Failed recording audit action: {exc}") from exc

    def list_admin_audit_log(self, *, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM admin_audit_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [
            {
                "id": int(r["id"]),
                "actor_id": str(r["actor_id"]),
                "action": str(r["action"]),
                "target_type": str(r["target_type"]),
                "target_id": str(r["target_id"]),
                "details": json.loads(r["details_json"]),
                "created_at": str(r["created_at"]),
            }
            for r in rows
        ]

    def get_setting(self, key: str, default: str = "") -> str:
        row = self._conn.execute(
            "SELECT value FROM bot_settings WHERE key = ?", (key,)
        ).fetchone()
        return str(row["value"]) if row is not None else default

    def set_setting(self, key: str, value: str) -> None:
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            self._conn.execute(
                """
                INSERT INTO bot_settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, value, _utc_iso()),
            )
            self._conn.execute("COMMIT")
        except Exception as exc:
            self._conn.execute("ROLLBACK")
            raise PersistenceError(f"Failed updating setting {key}: {exc}") from exc

    def upsert_known_chat(
        self, chat_id: str, chat_type: str, title: str | None = None
    ) -> None:
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            self._conn.execute(
                """
                INSERT INTO known_chats (chat_id, chat_type, title, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    chat_type = excluded.chat_type,
                    title = COALESCE(excluded.title, known_chats.title),
                    updated_at = excluded.updated_at
                """,
                (chat_id, chat_type, title, _utc_iso()),
            )
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")

    def list_known_chats(self, *, chat_type: str | None = None) -> list[str]:
        if chat_type is None:
            rows = self._conn.execute("SELECT chat_id FROM known_chats").fetchall()
        else:
            rows = self._conn.execute(
                "SELECT chat_id FROM known_chats WHERE chat_type = ?", (chat_type,)
            ).fetchall()
        return [str(r["chat_id"]) for r in rows]

    def integrity_check(self) -> tuple[bool, str]:
        try:
            row = self._conn.execute("PRAGMA integrity_check").fetchone()
            msg = str(row[0]) if row else "unknown"
            return msg.lower() == "ok", msg
        except Exception as exc:
            return False, type(exc).__name__

    def get_stats_snapshot(self) -> dict[str, int]:
        def _count(sql: str, params: tuple[Any, ...] = ()) -> int:
            row = self._conn.execute(sql, params).fetchone()
            return int(row[0]) if row else 0

        return {
            "total_users": _count("SELECT COUNT(*) FROM player_profiles"),
            "private_chats": _count(
                "SELECT COUNT(*) FROM known_chats WHERE chat_type = 'private'"
            ),
            "group_chats": _count(
                "SELECT COUNT(*) FROM known_chats WHERE chat_type != 'private'"
            ),
            "active_matches": _count(
                "SELECT COUNT(*) FROM matches WHERE status = ?",
                (MatchLifecycleStatus.DRAFTING.value,),
            ),
            "completed_matches": _count(
                "SELECT COUNT(*) FROM match_history WHERE status = ?",
                (MatchLifecycleStatus.COMPLETED.value,),
            ),
            "total_history": _count("SELECT COUNT(*) FROM match_history"),
            "open_challenges": _count(
                "SELECT COUNT(*) FROM challenges WHERE status = ?",
                (ChallengeStatus.OPEN.value,),
            ),
        }
