"""Lightweight serialized persistence adapter & commit-before-reveal harness."""

from __future__ import annotations

import asyncio
from typing import Any, Mapping, Protocol

from app.engine.engine import (
    assign_role,
    project_public_view,
    restore_snapshot,
    shuffle,
    skip_character,
    start_draft,
    terminate_draft,
)
from app.engine.errors import ErrorCode
from app.engine.models import (
    ActionResult,
    CatalogEntry,
    DEFAULT_SKIPS_PER_PLAYER,
    DraftSnapshot,
    PublicDraftView,
    ROLES,
    TerminationReason,
)
from app.engine.randomness import DrawSource


class PersistenceWriteError(RuntimeError):
    """Raised when saving a new revision fails before reveal."""


class DraftStore(Protocol):
    """Persistence contract for serialized match snapshots (Module 7 boundary)."""

    def load(self, match_id: str) -> DraftSnapshot | None: ...

    def save_initial(self, snapshot: DraftSnapshot) -> None: ...

    def compare_and_set(self, expected_revision: int, snapshot: DraftSnapshot) -> bool: ...


class InMemoryDraftStore:
    """In-memory JSON snapshot store supporting CAS and failure injection."""

    def __init__(self) -> None:
        self._records: dict[str, str] = {}
        self.fail_next_save: bool = False
        self.fail_on_revision: int | None = None

    def load(self, match_id: str) -> DraftSnapshot | None:
        raw = self._records.get(match_id)
        return restore_snapshot(raw) if raw is not None else None

    def save_initial(self, snapshot: DraftSnapshot) -> None:
        if snapshot.match_id in self._records:
            raise PersistenceWriteError(f"Match {snapshot.match_id!r} already exists")
        if self.fail_next_save:
            self.fail_next_save = False
            raise PersistenceWriteError("Simulated initial persistence failure")
        self._records[snapshot.match_id] = snapshot.to_json()

    def compare_and_set(self, expected_revision: int, snapshot: DraftSnapshot) -> bool:
        if self.fail_next_save:
            self.fail_next_save = False
            raise PersistenceWriteError("Simulated CAS persistence failure")
        if self.fail_on_revision is not None and snapshot.revision == self.fail_on_revision:
            raise PersistenceWriteError(
                f"Simulated failure saving revision {snapshot.revision}"
            )
        current = self.load(snapshot.match_id)
        if current is None or current.revision != expected_revision:
            return False
        self._records[snapshot.match_id] = snapshot.to_json()
        return True


class SerializedDraftService:
    """Per-match serialized action processor enforcing commit-before-reveal."""

    def __init__(
        self,
        store: DraftStore | None = None,
        *,
        draw_source: DrawSource | None = None,
    ) -> None:
        self.store: DraftStore = store or InMemoryDraftStore()
        self.draw_source = draw_source
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock_for(self, match_id: str) -> asyncio.Lock:
        lock = self._locks.get(match_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[match_id] = lock
        return lock

    def get_public_view(self, match_id: str) -> PublicDraftView | None:
        snap = self.store.load(match_id)
        return project_public_view(snap) if snap is not None else None

    async def start_match(
        self,
        *,
        match_id: str,
        players: tuple[str, str],
        universe_id: str,
        mode: str,
        catalog: tuple[CatalogEntry, ...] | list[CatalogEntry],
        rarity_weights: Mapping[str, float],
        dataset_version: str,
        skips_per_player: int = DEFAULT_SKIPS_PER_PLAYER,
        roles: tuple[str, ...] = ROLES,
        forced_starter: str | None = None,
        timestamp: Mapping[str, Any] | None = None,
    ) -> ActionResult:
        async with self._lock_for(match_id):
            result = start_draft(
                match_id=match_id,
                players=players,
                universe_id=universe_id,
                mode=mode,
                catalog=catalog,
                rarity_weights=rarity_weights,
                dataset_version=dataset_version,
                skips_per_player=skips_per_player,
                roles=roles,
                draw_source=self.draw_source,
                forced_starter=forced_starter,
                timestamp=timestamp,
            )
            self.store.save_initial(result.snapshot)
            return result

    async def _apply(self, match_id: str, transition) -> ActionResult:
        async with self._lock_for(match_id):
            current = self.store.load(match_id)
            if current is None:
                raise KeyError(f"Unknown match {match_id!r}")
            result: ActionResult = transition(current)
            if not result.accepted:
                return result
            committed = self.store.compare_and_set(current.revision, result.snapshot)
            if not committed:
                raise PersistenceWriteError(
                    f"CAS conflict saving match {match_id!r} at revision {current.revision}"
                )
            return result

    async def shuffle(
        self,
        *,
        match_id: str,
        player_id: str,
        expected_revision: int,
        timestamp: Mapping[str, Any] | None = None,
    ) -> ActionResult:
        return await self._apply(
            match_id,
            lambda snap: shuffle(
                snap,
                player_id=player_id,
                expected_revision=expected_revision,
                draw_source=self.draw_source,
                timestamp=timestamp,
            ),
        )

    async def assign_role(
        self,
        *,
        match_id: str,
        player_id: str,
        role: str,
        expected_revision: int,
        timestamp: Mapping[str, Any] | None = None,
    ) -> ActionResult:
        return await self._apply(
            match_id,
            lambda snap: assign_role(
                snap,
                player_id=player_id,
                role=role,
                expected_revision=expected_revision,
                timestamp=timestamp,
            ),
        )

    async def skip_character(
        self,
        *,
        match_id: str,
        player_id: str,
        expected_revision: int,
        timestamp: Mapping[str, Any] | None = None,
    ) -> ActionResult:
        return await self._apply(
            match_id,
            lambda snap: skip_character(
                snap,
                player_id=player_id,
                expected_revision=expected_revision,
                timestamp=timestamp,
            ),
        )

    async def terminate(
        self,
        *,
        match_id: str,
        reason: TerminationReason | str,
        subject_player_id: str | None = None,
        source_label: str = "",
        caller_reference: str = "",
        timestamp: Mapping[str, Any] | None = None,
    ) -> ActionResult:
        return await self._apply(
            match_id,
            lambda snap: terminate_draft(
                snap,
                reason=reason,
                subject_player_id=subject_player_id,
                source_label=source_label,
                caller_reference=caller_reference,
                timestamp=timestamp,
            ),
        )
