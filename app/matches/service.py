"""Application-layer Challenge, Matchmaking, and Match Lifecycle Manager (Module 5)."""

from __future__ import annotations

import asyncio
import random
import secrets
import time
import uuid
from typing import Callable

from app.database import CharacterDatabase
from app.engine import (
    DrawSource,
    MatchStatus,
    TerminationReason,
    assign_role,
    shuffle,
    skip_character,
    start_draft,
    terminate_draft,
)
from app.matches.errors import MatchManagementErrorCode
from app.matches.models import (
    ChallengeOperationResult,
    ChallengeRecord,
    ChallengeStatus,
    ChallengeType,
    DraftCommandSelection,
    ManagedMatch,
    MatchLifecycleStatus,
    MatchOperationResult,
    MatchOutcomeReason,
    MatchOutcomeSummary,
    MessageReference,
    TimeoutPolicy,
)
from app.resolution import DecidedBy, MatchOutcome, resolve_completed_draft
from app.scoring import DatasetKind

_VALID_GAME_MODES = frozenset({"ranked", "friendly"})


class MatchManager:
    """Coordinates challenges, matchmaking, draft lifecycle, timeouts, and resolution."""

    def __init__(
        self,
        db: CharacterDatabase,
        *,
        dataset_kind: DatasetKind = DatasetKind.PRODUCTION,
        timeout_policy: TimeoutPolicy | None = None,
        clock: Callable[[], float] | None = None,
        draw_source: DrawSource | None = None,
        universe_rng: random.Random | None = None,
        eligibility_checker: Callable[[str], bool] | None = None,
    ) -> None:
        self.db = db
        self.dataset_kind = dataset_kind
        self.timeout_policy = timeout_policy or TimeoutPolicy()
        self.clock = clock or time.monotonic
        self.draw_source = draw_source
        self._universe_rng = universe_rng or secrets.SystemRandom()
        self._eligibility_checker = eligibility_checker or (lambda _pid: True)

        self._global_lock = asyncio.Lock()
        self._match_locks: dict[str, asyncio.Lock] = {}
        self._challenges: dict[str, ChallengeRecord] = {}
        self._matches: dict[str, ManagedMatch] = {}
        self._active_match_by_player: dict[str, str] = {}

    def _lock_for_match(self, match_id: str) -> asyncio.Lock:
        lock = self._match_locks.get(match_id)
        if lock is None:
            lock = asyncio.Lock()
            self._match_locks[match_id] = lock
        return lock

    def _is_player_eligible(self, player_id: str) -> bool:
        return bool(player_id and player_id.strip() and self._eligibility_checker(player_id))

    def _resolve_universe_id(self, universe_arg: str) -> str | None:
        eligible = self.db.list_eligible_universes(kind=self.dataset_kind)
        arg = universe_arg.strip()
        if not arg:
            return None
        if arg.lower() == "random":
            if not eligible:
                return None
            return self._universe_rng.choice(eligible).universe_id
        for u in eligible:
            if u.universe_id.lower() == arg.lower() or u.name.lower() == arg.lower():
                return u.universe_id
        return None

    # ------------------------------------------------------------------
    # Challenge commands & lifecycle
    # ------------------------------------------------------------------

    async def handle_draft_command(
        self,
        *,
        player_id: str,
        chat_id: str,
        universe_arg: str | None = None,
        reply_to_user_id: str | None = None,
        game_mode: str = "ranked",
    ) -> tuple[DraftCommandSelection | None, ChallengeOperationResult | None]:
        """Logical /draft handler: list universes, /draft <universe>, or /draft random."""
        if universe_arg is None or not universe_arg.strip():
            eligible = tuple(
                u.universe_id for u in self.db.list_eligible_universes(kind=self.dataset_kind)
            )
            return DraftCommandSelection(
                action="list_universes", eligible_universes=eligible
            ), None

        arg = universe_arg.strip()
        if arg.lower() == "random":
            eligible = self.db.list_eligible_universes(kind=self.dataset_kind)
            if not eligible:
                return None, ChallengeOperationResult(
                    accepted=False,
                    error_code=MatchManagementErrorCode.NO_ELIGIBLE_UNIVERSES,
                    message="No active eligible universes are available",
                )
            chosen = self._universe_rng.choice(eligible).universe_id
        else:
            chosen = self._resolve_universe_id(arg)
            if chosen is None:
                return None, ChallengeOperationResult(
                    accepted=False,
                    error_code=MatchManagementErrorCode.UNIVERSE_NOT_ELIGIBLE,
                    message=f"Universe {arg!r} is not active or has no published dataset",
                )

        res = await self.create_challenge(
            challenger_id=player_id,
            chat_id=chat_id,
            universe_id=chosen,
            target_player_id=reply_to_user_id,
            game_mode=game_mode,
        )
        if not res.accepted:
            return None, res
        return DraftCommandSelection(
            action="challenge_created",
            eligible_universes=(chosen,),
            challenge=res.challenge,
        ), res

    async def create_challenge(
        self,
        *,
        challenger_id: str,
        chat_id: str,
        universe_id: str,
        target_player_id: str | None = None,
        game_mode: str = "ranked",
    ) -> ChallengeOperationResult:
        if game_mode not in _VALID_GAME_MODES:
            return ChallengeOperationResult(
                accepted=False,
                error_code=MatchManagementErrorCode.INVALID_GAME_MODE,
                message="game_mode must be 'ranked' or 'friendly'",
            )
        if not self._is_player_eligible(challenger_id):
            return ChallengeOperationResult(
                accepted=False,
                error_code=MatchManagementErrorCode.PLAYER_NOT_ELIGIBLE,
                message="Challenger is not eligible",
            )
        if target_player_id is not None:
            if target_player_id == challenger_id:
                return ChallengeOperationResult(
                    accepted=False,
                    error_code=MatchManagementErrorCode.SELF_CHALLENGE_FORBIDDEN,
                    message="Cannot challenge yourself",
                )
            if not self._is_player_eligible(target_player_id):
                return ChallengeOperationResult(
                    accepted=False,
                    error_code=MatchManagementErrorCode.PLAYER_NOT_ELIGIBLE,
                    message="Target player is not eligible",
                )

        async with self._global_lock:
            if challenger_id in self._active_match_by_player:
                return ChallengeOperationResult(
                    accepted=False,
                    error_code=MatchManagementErrorCode.PLAYER_ALREADY_IN_MATCH,
                    message="Challenger already has an active match",
                )
            if target_player_id is not None and target_player_id in self._active_match_by_player:
                return ChallengeOperationResult(
                    accepted=False,
                    error_code=MatchManagementErrorCode.PLAYER_ALREADY_IN_MATCH,
                    message="Target player already has an active match",
                )

            eligible_ids = {
                u.universe_id for u in self.db.list_eligible_universes(kind=self.dataset_kind)
            }
            if universe_id not in eligible_ids:
                return ChallengeOperationResult(
                    accepted=False,
                    error_code=MatchManagementErrorCode.UNIVERSE_NOT_ELIGIBLE,
                    message=f"Universe {universe_id!r} is not eligible",
                )

            now = self.clock()
            cid = f"chl-{uuid.uuid4().hex[:12]}"
            ctype = ChallengeType.DIRECT if target_player_id is not None else ChallengeType.OPEN
            record = ChallengeRecord(
                challenge_id=cid,
                challenge_type=ctype,
                challenger_id=challenger_id,
                target_player_id=target_player_id,
                universe_id=universe_id,
                game_mode=game_mode,
                chat_id=chat_id,
                status=ChallengeStatus.OPEN,
                created_at=now,
                expires_at=now + self.timeout_policy.challenge_ttl_seconds,
                generation=0,
            )
            self._challenges[cid] = record
            return ChallengeOperationResult(accepted=True, challenge=record)

    async def accept_challenge(
        self,
        *,
        challenge_id: str,
        player_id: str,
        expected_generation: int | None = None,
    ) -> ChallengeOperationResult:
        async with self._global_lock:
            chl = self._challenges.get(challenge_id)
            if chl is None:
                return ChallengeOperationResult(
                    accepted=False,
                    error_code=MatchManagementErrorCode.CHALLENGE_NOT_FOUND,
                    message="Challenge not found",
                )

            now = self.clock()
            if chl.status is ChallengeStatus.OPEN and now >= chl.expires_at:
                expired = ChallengeRecord(
                    **{
                        **{f: getattr(chl, f) for f in chl.__slots__},
                        "status": ChallengeStatus.EXPIRED,
                        "generation": chl.generation + 1,
                    }
                )
                self._challenges[challenge_id] = expired
                return ChallengeOperationResult(
                    accepted=False,
                    error_code=MatchManagementErrorCode.CHALLENGE_EXPIRED,
                    message="Challenge has expired",
                    challenge=expired,
                )

            if chl.status is not ChallengeStatus.OPEN:
                return ChallengeOperationResult(
                    accepted=False,
                    error_code=MatchManagementErrorCode.CHALLENGE_NOT_OPEN,
                    message=f"Challenge is already {chl.status.value}",
                    challenge=chl,
                )
            if expected_generation is not None and expected_generation != chl.generation:
                return ChallengeOperationResult(
                    accepted=False,
                    error_code=MatchManagementErrorCode.STALE_CONTROL_GENERATION,
                    message="Challenge control is outdated",
                    challenge=chl,
                )
            if player_id == chl.challenger_id:
                return ChallengeOperationResult(
                    accepted=False,
                    error_code=MatchManagementErrorCode.SELF_CHALLENGE_FORBIDDEN,
                    message="Challenger cannot accept their own challenge",
                    challenge=chl,
                )
            if chl.challenge_type is ChallengeType.DIRECT and player_id != chl.target_player_id:
                return ChallengeOperationResult(
                    accepted=False,
                    error_code=MatchManagementErrorCode.NOT_CHALLENGE_TARGET,
                    message="Only the challenged player may accept",
                    challenge=chl,
                )

            # Revalidate both players' eligibility at acceptance time
            if not (self._is_player_eligible(chl.challenger_id) and self._is_player_eligible(player_id)):
                return ChallengeOperationResult(
                    accepted=False,
                    error_code=MatchManagementErrorCode.PLAYER_NOT_ELIGIBLE,
                    message="One or both players are no longer eligible",
                    challenge=chl,
                )
            if chl.challenger_id in self._active_match_by_player or player_id in self._active_match_by_player:
                return ChallengeOperationResult(
                    accepted=False,
                    error_code=MatchManagementErrorCode.PLAYER_ALREADY_IN_MATCH,
                    message="A player is already in an active match",
                    challenge=chl,
                )

            # Pin exact dataset_version & rarity configuration at match creation
            dver = self.db.get_latest_published_version(chl.universe_id, kind=self.dataset_kind)
            universe = self.db.get_universe(chl.universe_id)
            if dver is None or (self.dataset_kind is DatasetKind.PRODUCTION and not universe.active):
                return ChallengeOperationResult(
                    accepted=False,
                    error_code=MatchManagementErrorCode.UNIVERSE_NOT_ELIGIBLE,
                    message="Universe no longer has an eligible published dataset",
                    challenge=chl,
                )

            catalog, rarity_weights, pinned_version = self.db.export_draft_catalog(dver)
            match_id = f"match-{uuid.uuid4().hex[:12]}"
            players = (chl.challenger_id, player_id)
            draft_res = start_draft(
                match_id=match_id,
                players=players,
                universe_id=chl.universe_id,
                mode=chl.game_mode,
                catalog=catalog,
                rarity_weights=rarity_weights,
                dataset_version=pinned_version,
                draw_source=self.draw_source,
            )

            match = ManagedMatch(
                match_id=match_id,
                challenge_id=challenge_id,
                players=players,
                universe_id=chl.universe_id,
                game_mode=chl.game_mode,
                dataset_version=pinned_version,
                status=MatchLifecycleStatus.DRAFTING,
                draft_snapshot=draft_res.snapshot,
                public_view=draft_res.public_view,
                generation=0,
                turn_started_at=now,
                turn_deadline_at=now + self.timeout_policy.turn_timeout_seconds,
                turn_number_at_start=draft_res.snapshot.turn_number or 1,
                extensions_remaining={
                    players[0]: self.timeout_policy.extensions_per_player,
                    players[1]: self.timeout_policy.extensions_per_player,
                },
                timeout_policy=self.timeout_policy,
                created_at=now,
                updated_at=now,
            )
            accepted_chl = ChallengeRecord(
                **{
                    **{f: getattr(chl, f) for f in chl.__slots__},
                    "status": ChallengeStatus.ACCEPTED,
                    "accepted_by": player_id,
                    "match_id": match_id,
                    "generation": chl.generation + 1,
                }
            )
            self._challenges[challenge_id] = accepted_chl
            self._matches[match_id] = match
            self._active_match_by_player[chl.challenger_id] = match_id
            self._active_match_by_player[player_id] = match_id
            return ChallengeOperationResult(
                accepted=True, challenge=accepted_chl, match=match
            )

    async def cancel_challenge(
        self,
        *,
        challenge_id: str,
        player_id: str,
        expected_generation: int | None = None,
    ) -> ChallengeOperationResult:
        async with self._global_lock:
            chl = self._challenges.get(challenge_id)
            if chl is None:
                return ChallengeOperationResult(
                    accepted=False,
                    error_code=MatchManagementErrorCode.CHALLENGE_NOT_FOUND,
                    message="Challenge not found",
                )
            if player_id != chl.challenger_id:
                return ChallengeOperationResult(
                    accepted=False,
                    error_code=MatchManagementErrorCode.NOT_CHALLENGER,
                    message="Only the challenger may cancel",
                    challenge=chl,
                )
            if chl.status is ChallengeStatus.CANCELLED:
                return ChallengeOperationResult(accepted=True, challenge=chl)
            if chl.status is not ChallengeStatus.OPEN:
                return ChallengeOperationResult(
                    accepted=False,
                    error_code=MatchManagementErrorCode.CHALLENGE_NOT_OPEN,
                    message=f"Challenge is already {chl.status.value}",
                    challenge=chl,
                )
            if expected_generation is not None and expected_generation != chl.generation:
                return ChallengeOperationResult(
                    accepted=False,
                    error_code=MatchManagementErrorCode.STALE_CONTROL_GENERATION,
                    message="Challenge control is outdated",
                    challenge=chl,
                )
            cancelled = ChallengeRecord(
                **{
                    **{f: getattr(chl, f) for f in chl.__slots__},
                    "status": ChallengeStatus.CANCELLED,
                    "generation": chl.generation + 1,
                }
            )
            self._challenges[challenge_id] = cancelled
            return ChallengeOperationResult(accepted=True, challenge=cancelled)

    async def expire_challenge(self, challenge_id: str) -> ChallengeOperationResult:
        async with self._global_lock:
            chl = self._challenges.get(challenge_id)
            if chl is None:
                return ChallengeOperationResult(
                    accepted=False,
                    error_code=MatchManagementErrorCode.CHALLENGE_NOT_FOUND,
                    message="Challenge not found",
                )
            if chl.status is ChallengeStatus.EXPIRED:
                return ChallengeOperationResult(accepted=True, challenge=chl)
            if chl.status is not ChallengeStatus.OPEN:
                return ChallengeOperationResult(
                    accepted=False,
                    error_code=MatchManagementErrorCode.CHALLENGE_NOT_OPEN,
                    message=f"Challenge is already {chl.status.value}",
                    challenge=chl,
                )
            if self.clock() < chl.expires_at:
                return ChallengeOperationResult(
                    accepted=False,
                    error_code=MatchManagementErrorCode.INACTIVITY_NOT_ELAPSED,
                    message="Challenge TTL has not elapsed",
                    challenge=chl,
                )
            expired = ChallengeRecord(
                **{
                    **{f: getattr(chl, f) for f in chl.__slots__},
                    "status": ChallengeStatus.EXPIRED,
                    "generation": chl.generation + 1,
                }
            )
            self._challenges[challenge_id] = expired
            return ChallengeOperationResult(accepted=True, challenge=expired)

    # ------------------------------------------------------------------
    # Draft actions
    # ------------------------------------------------------------------

    def _release_players(self, players: tuple[str, str], match_id: str) -> None:
        for pid in players:
            if self._active_match_by_player.get(pid) == match_id:
                del self._active_match_by_player[pid]

    def _validate_active_participant(
        self,
        match: ManagedMatch | None,
        *,
        player_id: str,
        expected_generation: int | None,
    ) -> MatchOperationResult | None:
        if match is None:
            return MatchOperationResult(
                accepted=False,
                error_code=MatchManagementErrorCode.MATCH_NOT_FOUND,
                message="Match not found",
            )
        if player_id not in match.players:
            return MatchOperationResult(
                accepted=False,
                error_code=MatchManagementErrorCode.NOT_MATCH_PARTICIPANT,
                message="Player is not a participant in this match",
                match=match,
            )
        if match.status is not MatchLifecycleStatus.DRAFTING:
            return MatchOperationResult(
                accepted=False,
                error_code=MatchManagementErrorCode.MATCH_NOT_ACTIVE,
                message=f"Match is already {match.status.value}",
                match=match,
            )
        if expected_generation is not None and expected_generation != match.generation:
            return MatchOperationResult(
                accepted=False,
                error_code=MatchManagementErrorCode.STALE_CONTROL_GENERATION,
                message="Obsolete match control generation",
                match=match,
            )
        return None

    async def shuffle_match(
        self,
        *,
        match_id: str,
        player_id: str,
        expected_revision: int,
        expected_generation: int | None = None,
    ) -> MatchOperationResult:
        async with self._lock_for_match(match_id):
            match = self._matches.get(match_id)
            err = self._validate_active_participant(
                match, player_id=player_id, expected_generation=expected_generation
            )
            if err is not None:
                return err
            assert match is not None

            res = shuffle(
                match.draft_snapshot,
                player_id=player_id,
                expected_revision=expected_revision,
                draw_source=self.draw_source,
            )
            if not res.accepted:
                return MatchOperationResult(
                    accepted=False,
                    error_code=MatchManagementErrorCode.DRAFT_ACTION_REJECTED,
                    draft_error_code=res.error_code,
                    message=f"Draft shuffle rejected: {res.error_code.value}",
                    match=match,
                )
            now = self.clock()
            updated = ManagedMatch(
                **{
                    **{f: getattr(match, f) for f in match.__slots__},
                    "draft_snapshot": res.snapshot,
                    "public_view": res.public_view,
                    "generation": match.generation + 1,
                    "updated_at": now,
                }
            )
            self._matches[match_id] = updated
            return MatchOperationResult(accepted=True, match=updated)

    async def skip_match_character(
        self,
        *,
        match_id: str,
        player_id: str,
        expected_revision: int,
        expected_generation: int | None = None,
    ) -> MatchOperationResult:
        """Skip held character without resetting turn_started_at (Section 5)."""
        async with self._lock_for_match(match_id):
            match = self._matches.get(match_id)
            err = self._validate_active_participant(
                match, player_id=player_id, expected_generation=expected_generation
            )
            if err is not None:
                return err
            assert match is not None

            res = skip_character(
                match.draft_snapshot,
                player_id=player_id,
                expected_revision=expected_revision,
            )
            if not res.accepted:
                return MatchOperationResult(
                    accepted=False,
                    error_code=MatchManagementErrorCode.DRAFT_ACTION_REJECTED,
                    draft_error_code=res.error_code,
                    message=f"Draft skip rejected: {res.error_code.value}",
                    match=match,
                )
            now = self.clock()
            # Note: turn_started_at is preserved so skip never resets the turn timer.
            updated = ManagedMatch(
                **{
                    **{f: getattr(match, f) for f in match.__slots__},
                    "draft_snapshot": res.snapshot,
                    "public_view": res.public_view,
                    "generation": match.generation + 1,
                    "updated_at": now,
                }
            )
            self._matches[match_id] = updated
            return MatchOperationResult(accepted=True, match=updated)

    async def assign_match_role(
        self,
        *,
        match_id: str,
        player_id: str,
        role: str,
        expected_revision: int,
        expected_generation: int | None = None,
    ) -> MatchOperationResult:
        async with self._lock_for_match(match_id):
            match = self._matches.get(match_id)
            err = self._validate_active_participant(
                match, player_id=player_id, expected_generation=expected_generation
            )
            if err is not None:
                return err
            assert match is not None

            res = assign_role(
                match.draft_snapshot,
                player_id=player_id,
                role=role,
                expected_revision=expected_revision,
            )
            if not res.accepted:
                return MatchOperationResult(
                    accepted=False,
                    error_code=MatchManagementErrorCode.DRAFT_ACTION_REJECTED,
                    draft_error_code=res.error_code,
                    message=f"Draft assign rejected: {res.error_code.value}",
                    match=match,
                )

            now = self.clock()
            if res.snapshot.status is MatchStatus.COMPLETED and res.completed_output is not None:
                resolved = resolve_completed_draft(
                    res.completed_output, self.db, player_order=match.players
                )
                if not resolved.ok:
                    return MatchOperationResult(
                        accepted=False,
                        error_code=MatchManagementErrorCode.RESOLUTION_FAILED,
                        message=f"Resolution failed: {resolved.error_code.value}",
                        match=match,
                    )

                if resolved.decided_by is DecidedBy.MATCHUP_COUNT:
                    reason = MatchOutcomeReason.NORMAL_MATCHUP_COUNT
                elif resolved.decided_by is DecidedBy.COMBINED_SCORE:
                    reason = MatchOutcomeReason.NORMAL_COMBINED_SCORE
                else:
                    reason = MatchOutcomeReason.NORMAL_DRAW

                p1, p2 = match.players
                if resolved.outcome is MatchOutcome.PLAYER_1_WIN:
                    winner_id, loser_id = p1, p2
                elif resolved.outcome is MatchOutcome.PLAYER_2_WIN:
                    winner_id, loser_id = p2, p1
                else:
                    winner_id, loser_id = None, None

                outcome = MatchOutcomeSummary(
                    reason=reason,
                    winner_id=winner_id,
                    loser_id=loser_id,
                    affects_rating=(match.game_mode == "ranked"),
                    resolution=resolved,
                )
                completed_match = ManagedMatch(
                    **{
                        **{f: getattr(match, f) for f in match.__slots__},
                        "status": MatchLifecycleStatus.COMPLETED,
                        "draft_snapshot": res.snapshot,
                        "public_view": res.public_view,
                        "generation": match.generation + 1,
                        "inactivity_claim_offered_to": None,
                        "inactivity_claim_expires_at": None,
                        "outcome": outcome,
                        "updated_at": now,
                    }
                )
                self._matches[match_id] = completed_match
                async with self._global_lock:
                    self._release_players(match.players, match_id)
                return MatchOperationResult(accepted=True, match=completed_match)

            # Turn passed cleanly -> start new turn timer and clear any prior inactivity offer
            updated = ManagedMatch(
                **{
                    **{f: getattr(match, f) for f in match.__slots__},
                    "draft_snapshot": res.snapshot,
                    "public_view": res.public_view,
                    "generation": match.generation + 1,
                    "turn_started_at": now,
                    "turn_deadline_at": now + match.timeout_policy.turn_timeout_seconds,
                    "turn_number_at_start": res.snapshot.turn_number or match.turn_number_at_start,
                    "inactivity_claim_offered_to": None,
                    "inactivity_claim_expires_at": None,
                    "updated_at": now,
                }
            )
            self._matches[match_id] = updated
            return MatchOperationResult(accepted=True, match=updated)

    # ------------------------------------------------------------------
    # Forfeiture, inactivity, and external termination
    # ------------------------------------------------------------------

    async def forfeit_match(
        self,
        *,
        match_id: str,
        player_id: str,
        expected_generation: int | None = None,
    ) -> MatchOperationResult:
        async with self._lock_for_match(match_id):
            match = self._matches.get(match_id)
            if match is None:
                return MatchOperationResult(
                    accepted=False,
                    error_code=MatchManagementErrorCode.MATCH_NOT_FOUND,
                    message="Match not found",
                )
            if player_id not in match.players:
                return MatchOperationResult(
                    accepted=False,
                    error_code=MatchManagementErrorCode.NOT_MATCH_PARTICIPANT,
                    message="Player is not in this match",
                    match=match,
                )
            if (
                match.status is MatchLifecycleStatus.FORFEITED
                and match.outcome is not None
                and match.outcome.forfeiting_player_id == player_id
            ):
                return MatchOperationResult(accepted=True, idempotent=True, match=match)

            err = self._validate_active_participant(
                match, player_id=player_id, expected_generation=expected_generation
            )
            if err is not None:
                return err

            term_res = terminate_draft(
                match.draft_snapshot,
                reason=TerminationReason.FORFEIT,
                subject_player_id=player_id,
                source_label="match_manager",
                caller_reference=f"forfeit:{player_id}",
            )
            opponent = match.players[1] if match.players[0] == player_id else match.players[0]
            outcome = MatchOutcomeSummary(
                reason=MatchOutcomeReason.VOLUNTARY_FORFEITURE,
                winner_id=opponent,
                loser_id=player_id,
                affects_rating=(match.game_mode == "ranked"),
                forfeiting_player_id=player_id,
                resolution=None,
                terminal_record=term_res.terminal_record,
            )
            now = self.clock()
            updated = ManagedMatch(
                **{
                    **{f: getattr(match, f) for f in match.__slots__},
                    "status": MatchLifecycleStatus.FORFEITED,
                    "draft_snapshot": term_res.snapshot,
                    "public_view": term_res.public_view,
                    "generation": match.generation + 1,
                    "inactivity_claim_offered_to": None,
                    "inactivity_claim_expires_at": None,
                    "outcome": outcome,
                    "updated_at": now,
                }
            )
            self._matches[match_id] = updated
            async with self._global_lock:
                self._release_players(match.players, match_id)
            return MatchOperationResult(accepted=True, match=updated)

    async def handle_turn_timeout(
        self,
        *,
        match_id: str,
        expected_revision: int,
        expected_turn_number: int,
    ) -> MatchOperationResult:
        """Revalidate timeout atomically; stale callbacks never alter advanced matches."""
        async with self._lock_for_match(match_id):
            match = self._matches.get(match_id)
            if match is None:
                return MatchOperationResult(
                    accepted=False,
                    error_code=MatchManagementErrorCode.MATCH_NOT_FOUND,
                    message="Match not found",
                )
            if match.status is not MatchLifecycleStatus.DRAFTING:
                return MatchOperationResult(
                    accepted=False,
                    error_code=MatchManagementErrorCode.STALE_TIMEOUT_EVENT,
                    message="Match is no longer active",
                    match=match,
                )
            if (
                match.draft_snapshot.revision != expected_revision
                or match.draft_snapshot.turn_number != expected_turn_number
            ):
                return MatchOperationResult(
                    accepted=False,
                    error_code=MatchManagementErrorCode.STALE_TIMEOUT_EVENT,
                    message="Match has already advanced past this timeout event",
                    match=match,
                )
            now = self.clock()
            if now < match.turn_deadline_at:
                return MatchOperationResult(
                    accepted=False,
                    error_code=MatchManagementErrorCode.INACTIVITY_NOT_ELAPSED,
                    message="Turn timeout has not elapsed",
                    match=match,
                )

            active = match.draft_snapshot.active_player_id
            opponent = match.players[1] if match.players[0] == active else match.players[0]
            updated = ManagedMatch(
                **{
                    **{f: getattr(match, f) for f in match.__slots__},
                    "generation": match.generation + 1,
                    "inactivity_claim_offered_to": opponent,
                    "inactivity_claim_expires_at": now + match.timeout_policy.claim_window_seconds,
                    "updated_at": now,
                }
            )
            self._matches[match_id] = updated
            return MatchOperationResult(accepted=True, match=updated)

    async def grant_turn_extension(
        self,
        *,
        match_id: str,
        granting_player_id: str,
        expected_generation: int | None = None,
    ) -> MatchOperationResult:
        """Grant one 60s extension to the active player (only by their opponent)."""
        async with self._lock_for_match(match_id):
            match = self._matches.get(match_id)
            err = self._validate_active_participant(
                match,
                player_id=granting_player_id,
                expected_generation=expected_generation,
            )
            if err is not None:
                return err
            assert match is not None

            active = match.draft_snapshot.active_player_id
            assert active is not None
            if granting_player_id == active:
                return MatchOperationResult(
                    accepted=False,
                    error_code=MatchManagementErrorCode.SELF_EXTENSION_FORBIDDEN,
                    message="Only the opponent may grant a turn extension",
                    match=match,
                )
            remaining = match.extensions_remaining.get(active, 0)
            if remaining <= 0:
                return MatchOperationResult(
                    accepted=False,
                    error_code=MatchManagementErrorCode.NO_EXTENSIONS_REMAINING,
                    message="Active player has already used their match extension",
                    match=match,
                )

            now = self.clock()
            new_ext = dict(match.extensions_remaining)
            new_ext[active] = remaining - 1
            new_deadline = max(now, match.turn_deadline_at) + match.timeout_policy.extension_seconds
            updated = ManagedMatch(
                **{
                    **{f: getattr(match, f) for f in match.__slots__},
                    "generation": match.generation + 1,
                    "turn_deadline_at": new_deadline,
                    "extensions_remaining": new_ext,
                    "inactivity_claim_offered_to": None,
                    "inactivity_claim_expires_at": None,
                    "updated_at": now,
                }
            )
            self._matches[match_id] = updated
            return MatchOperationResult(accepted=True, match=updated)

    async def claim_inactivity_victory(
        self,
        *,
        match_id: str,
        player_id: str,
        expected_generation: int | None = None,
    ) -> MatchOperationResult:
        async with self._lock_for_match(match_id):
            match = self._matches.get(match_id)
            if (
                match is not None
                and match.status is MatchLifecycleStatus.INACTIVITY_WIN
                and match.outcome is not None
                and match.outcome.winner_id == player_id
            ):
                return MatchOperationResult(accepted=True, idempotent=True, match=match)

            err = self._validate_active_participant(
                match, player_id=player_id, expected_generation=expected_generation
            )
            if err is not None:
                return err
            assert match is not None

            if match.inactivity_claim_offered_to != player_id:
                return MatchOperationResult(
                    accepted=False,
                    error_code=MatchManagementErrorCode.NO_INACTIVITY_CLAIM_PENDING,
                    message="No inactivity victory claim is offered to this player",
                    match=match,
                )

            inactive_player = (
                match.players[1] if match.players[0] == player_id else match.players[0]
            )
            term_res = terminate_draft(
                match.draft_snapshot,
                reason=TerminationReason.INACTIVITY,
                subject_player_id=inactive_player,
                source_label="match_manager",
                caller_reference=f"inactivity_claim:{player_id}",
            )
            outcome = MatchOutcomeSummary(
                reason=MatchOutcomeReason.INACTIVITY_VICTORY,
                winner_id=player_id,
                loser_id=inactive_player,
                affects_rating=(match.game_mode == "ranked"),
                inactive_player_id=inactive_player,
                resolution=None,
                terminal_record=term_res.terminal_record,
            )
            now = self.clock()
            updated = ManagedMatch(
                **{
                    **{f: getattr(match, f) for f in match.__slots__},
                    "status": MatchLifecycleStatus.INACTIVITY_WIN,
                    "draft_snapshot": term_res.snapshot,
                    "public_view": term_res.public_view,
                    "generation": match.generation + 1,
                    "inactivity_claim_offered_to": None,
                    "inactivity_claim_expires_at": None,
                    "outcome": outcome,
                    "updated_at": now,
                }
            )
            self._matches[match_id] = updated
            async with self._global_lock:
                self._release_players(match.players, match_id)
            return MatchOperationResult(accepted=True, match=updated)

    async def handle_claim_window_timeout(
        self,
        *,
        match_id: str,
        expected_generation: int,
    ) -> MatchOperationResult:
        """Abandon match without winner when opponent also fails to respond."""
        async with self._lock_for_match(match_id):
            match = self._matches.get(match_id)
            if match is None:
                return MatchOperationResult(
                    accepted=False,
                    error_code=MatchManagementErrorCode.MATCH_NOT_FOUND,
                    message="Match not found",
                )
            if match.status is MatchLifecycleStatus.ABANDONED:
                return MatchOperationResult(accepted=True, idempotent=True, match=match)
            if match.status is not MatchLifecycleStatus.DRAFTING:
                return MatchOperationResult(
                    accepted=False,
                    error_code=MatchManagementErrorCode.STALE_TIMEOUT_EVENT,
                    message="Match is no longer drafting",
                    match=match,
                )
            if match.generation != expected_generation or match.inactivity_claim_expires_at is None:
                return MatchOperationResult(
                    accepted=False,
                    error_code=MatchManagementErrorCode.STALE_TIMEOUT_EVENT,
                    message="Stale claim-window timeout",
                    match=match,
                )
            now = self.clock()
            if now < match.inactivity_claim_expires_at:
                return MatchOperationResult(
                    accepted=False,
                    error_code=MatchManagementErrorCode.INACTIVITY_NOT_ELAPSED,
                    message="Claim window has not elapsed",
                    match=match,
                )

            term_res = terminate_draft(
                match.draft_snapshot,
                reason=TerminationReason.BOTH_INACTIVE,
                source_label="match_manager",
                caller_reference="mutual_inactivity",
            )
            outcome = MatchOutcomeSummary(
                reason=MatchOutcomeReason.MUTUAL_INACTIVITY_ABANDONMENT,
                winner_id=None,
                loser_id=None,
                affects_rating=False,
                resolution=None,
                terminal_record=term_res.terminal_record,
            )
            updated = ManagedMatch(
                **{
                    **{f: getattr(match, f) for f in match.__slots__},
                    "status": MatchLifecycleStatus.ABANDONED,
                    "draft_snapshot": term_res.snapshot,
                    "public_view": term_res.public_view,
                    "generation": match.generation + 1,
                    "inactivity_claim_offered_to": None,
                    "inactivity_claim_expires_at": None,
                    "outcome": outcome,
                    "updated_at": now,
                }
            )
            self._matches[match_id] = updated
            async with self._global_lock:
                self._release_players(match.players, match_id)
            return MatchOperationResult(accepted=True, match=updated)

    async def terminate_match_externally(
        self,
        *,
        match_id: str,
        reason: TerminationReason = TerminationReason.ADMINISTRATIVE,
        source_label: str = "admin",
        caller_reference: str = "",
    ) -> MatchOperationResult:
        async with self._lock_for_match(match_id):
            match = self._matches.get(match_id)
            if match is None:
                return MatchOperationResult(
                    accepted=False,
                    error_code=MatchManagementErrorCode.MATCH_NOT_FOUND,
                    message="Match not found",
                )
            if match.status in {
                MatchLifecycleStatus.TERMINATED_ADMIN,
                MatchLifecycleStatus.TERMINATED_TECHNICAL,
            }:
                return MatchOperationResult(accepted=True, idempotent=True, match=match)
            if match.status is not MatchLifecycleStatus.DRAFTING:
                return MatchOperationResult(
                    accepted=False,
                    error_code=MatchManagementErrorCode.MATCH_NOT_ACTIVE,
                    message=f"Match is already {match.status.value}",
                    match=match,
                )

            term_res = terminate_draft(
                match.draft_snapshot,
                reason=reason,
                source_label=source_label,
                caller_reference=caller_reference,
            )
            is_admin = reason is TerminationReason.ADMINISTRATIVE
            lifecycle = (
                MatchLifecycleStatus.TERMINATED_ADMIN
                if is_admin
                else MatchLifecycleStatus.TERMINATED_TECHNICAL
            )
            outcome_reason = (
                MatchOutcomeReason.ADMINISTRATIVE_TERMINATION
                if is_admin
                else MatchOutcomeReason.TECHNICAL_TERMINATION
            )
            outcome = MatchOutcomeSummary(
                reason=outcome_reason,
                winner_id=None,
                loser_id=None,
                affects_rating=False,
                resolution=None,
                terminal_record=term_res.terminal_record,
            )
            now = self.clock()
            updated = ManagedMatch(
                **{
                    **{f: getattr(match, f) for f in match.__slots__},
                    "status": lifecycle,
                    "draft_snapshot": term_res.snapshot,
                    "public_view": term_res.public_view,
                    "generation": match.generation + 1,
                    "inactivity_claim_offered_to": None,
                    "inactivity_claim_expires_at": None,
                    "outcome": outcome,
                    "updated_at": now,
                }
            )
            self._matches[match_id] = updated
            async with self._global_lock:
                self._release_players(match.players, match_id)
            return MatchOperationResult(accepted=True, match=updated)

    async def resolve_match_now(self, match_id: str) -> MatchOperationResult:
        """Idempotent resolution lookup; explicitly rejects terminated matches."""
        async with self._lock_for_match(match_id):
            match = self._matches.get(match_id)
            if match is None:
                return MatchOperationResult(
                    accepted=False,
                    error_code=MatchManagementErrorCode.MATCH_NOT_FOUND,
                    message="Match not found",
                )
            if match.status is MatchLifecycleStatus.COMPLETED:
                return MatchOperationResult(accepted=True, idempotent=True, match=match)
            if match.status is MatchLifecycleStatus.DRAFTING:
                return MatchOperationResult(
                    accepted=False,
                    error_code=MatchManagementErrorCode.MATCH_NOT_ACTIVE,
                    message="Draft is not yet completed",
                    match=match,
                )
            return MatchOperationResult(
                accepted=False,
                error_code=MatchManagementErrorCode.TERMINATED_MATCH_CANNOT_RESOLVE,
                message=f"Terminated match ({match.status.value}) cannot enter normal resolution",
                match=match,
            )

    # ------------------------------------------------------------------
    # Retrieval & /game recovery interfaces
    # ------------------------------------------------------------------

    def get_challenge(self, challenge_id: str) -> ChallengeRecord | None:
        return self._challenges.get(challenge_id)

    def get_match(self, match_id: str) -> ManagedMatch | None:
        return self._matches.get(match_id)

    def get_active_match_for_player(self, player_id: str) -> ManagedMatch | None:
        match_id = self._active_match_by_player.get(player_id)
        return self._matches.get(match_id) if match_id is not None else None

    async def attach_message_reference(
        self, match_id: str, ref: MessageReference
    ) -> MatchOperationResult:
        async with self._lock_for_match(match_id):
            match = self._matches.get(match_id)
            if match is None:
                return MatchOperationResult(
                    accepted=False,
                    error_code=MatchManagementErrorCode.MATCH_NOT_FOUND,
                    message="Match not found",
                )
            updated = ManagedMatch(
                **{
                    **{f: getattr(match, f) for f in match.__slots__},
                    "message_refs": match.message_refs + (ref,),
                }
            )
            self._matches[match_id] = updated
            return MatchOperationResult(accepted=True, match=updated)
