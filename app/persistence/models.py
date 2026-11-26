"""Serialization models and recovery reports for Module 7 persistence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from app.engine import DraftSnapshot, TerminalRecord, TerminationReason
from app.matches.models import (
    ChallengeRecord,
    ChallengeStatus,
    ChallengeType,
    ManagedMatch,
    MatchLifecycleStatus,
    MatchOutcomeReason,
    MatchOutcomeSummary,
    MessageReference,
    TimeoutPolicy,
)
from app.resolution import (
    DecidedBy,
    MatchOutcome,
    MatchResolutionSuccess,
    MatchupParticipant,
    MatchupWinner,
    ResolutionSummary,
    RoleMatchup,
)


class PersistenceError(RuntimeError):
    """Raised when persistent storage cannot commit or read state safely."""


class CorruptStateError(PersistenceError):
    """Raised when persisted JSON or schema state is corrupt or invalid."""


@dataclass(frozen=True, slots=True)
class HistoricalMatchRecord:
    """Permanent terminal match record ready for Module 8 progression."""

    match_id: str
    universe_id: str
    game_mode: str
    dataset_version: str
    resolution_version: str | None
    scoring_version: str | None
    player_1_id: str
    player_2_id: str
    status: MatchLifecycleStatus
    outcome_reason: MatchOutcomeReason
    winner_id: str | None
    loser_id: str | None
    affects_rating: bool
    wins_player_1: int | None
    wins_player_2: int | None
    draws: int | None
    total_player_1: int | None
    total_player_2: int | None
    decided_by: str | None
    completed_at: float
    outcome: MatchOutcomeSummary

    @classmethod
    def from_managed_match(cls, match: ManagedMatch) -> HistoricalMatchRecord:
        if match.outcome is None:
            raise ValueError("Cannot build HistoricalMatchRecord without an outcome")
        out = match.outcome
        res = out.resolution
        return cls(
            match_id=match.match_id,
            universe_id=match.universe_id,
            game_mode=match.game_mode,
            dataset_version=match.dataset_version,
            resolution_version=res.resolution_version if res is not None else None,
            scoring_version=res.scoring_version if res is not None else None,
            player_1_id=match.players[0],
            player_2_id=match.players[1],
            status=match.status,
            outcome_reason=out.reason,
            winner_id=out.winner_id,
            loser_id=out.loser_id,
            affects_rating=out.affects_rating,
            wins_player_1=res.summary.wins_player_1 if res is not None else None,
            wins_player_2=res.summary.wins_player_2 if res is not None else None,
            draws=res.summary.draws if res is not None else None,
            total_player_1=res.summary.total_player_1 if res is not None else None,
            total_player_2=res.summary.total_player_2 if res is not None else None,
            decided_by=res.decided_by.value if res is not None else None,
            completed_at=match.updated_at,
            outcome=out,
        )


@dataclass(frozen=True, slots=True)
class StartupRecoveryReport:
    """Accurate, non-sensitive summary of startup recovery actions."""

    restored_matches: int = 0
    pending_challenges: int = 0
    expired_challenges: int = 0
    abandoned_matches: int = 0
    inactivity_prompted_matches: int = 0
    recovery_errors: tuple[str, ...] = ()

    @property
    def has_activity(self) -> bool:
        return any(
            (
                self.restored_matches,
                self.pending_challenges,
                self.expired_challenges,
                self.abandoned_matches,
                self.inactivity_prompted_matches,
                self.recovery_errors,
            )
        )


def timeout_policy_to_dict(policy: TimeoutPolicy) -> dict[str, Any]:
    return {
        "challenge_ttl_seconds": float(policy.challenge_ttl_seconds),
        "turn_timeout_seconds": float(policy.turn_timeout_seconds),
        "claim_window_seconds": float(policy.claim_window_seconds),
        "extension_seconds": float(policy.extension_seconds),
        "extensions_per_player": int(policy.extensions_per_player),
        "allow_inactivity_claim": bool(policy.allow_inactivity_claim),
    }


def timeout_policy_from_dict(data: Mapping[str, Any]) -> TimeoutPolicy:
    return TimeoutPolicy(
        challenge_ttl_seconds=float(data["challenge_ttl_seconds"]),
        turn_timeout_seconds=float(data["turn_timeout_seconds"]),
        claim_window_seconds=float(data["claim_window_seconds"]),
        extension_seconds=float(data["extension_seconds"]),
        extensions_per_player=int(data["extensions_per_player"]),
        allow_inactivity_claim=bool(data["allow_inactivity_claim"]),
    )


def resolution_to_dict(res: MatchResolutionSuccess) -> dict[str, Any]:
    return res.to_dict()


def resolution_from_dict(data: Mapping[str, Any]) -> MatchResolutionSuccess:
    matchups = tuple(
        RoleMatchup(
            role=str(m["role"]),
            player_1=MatchupParticipant(
                character_id=str(m["player_1"]["character_id"]),
                power=int(m["player_1"]["power"]),
                fit=int(m["player_1"]["fit"]),
                score=int(m["player_1"]["score"]),
            ),
            player_2=MatchupParticipant(
                character_id=str(m["player_2"]["character_id"]),
                power=int(m["player_2"]["power"]),
                fit=int(m["player_2"]["fit"]),
                score=int(m["player_2"]["score"]),
            ),
            winner=MatchupWinner(str(m["winner"])),
            margin=int(m["margin"]),
        )
        for m in data["matchups"]
    )
    s = data["summary"]
    summary = ResolutionSummary(
        wins_player_1=int(s["wins_player_1"]),
        wins_player_2=int(s["wins_player_2"]),
        draws=int(s["draws"]),
        total_player_1=int(s["total_player_1"]),
        total_player_2=int(s["total_player_2"]),
        total_margin=int(s["total_margin"]),
    )
    return MatchResolutionSuccess(
        resolution_version=str(data["resolution_version"]),
        scoring_version=str(data["scoring_version"]),
        dataset_version=str(data["dataset_version"]),
        match_id=str(data["match_id"]),
        universe_id=str(data["universe_id"]),
        game_mode=str(data["game_mode"]),
        starting_player=str(data["starting_player"]),
        players=dict(data["players"]),
        outcome=MatchOutcome(str(data["outcome"])),
        decided_by=DecidedBy(str(data["decided_by"])),
        summary=summary,
        matchups=matchups,
    )


def outcome_to_dict(outcome: MatchOutcomeSummary) -> dict[str, Any]:
    return {
        "reason": outcome.reason.value,
        "winner_id": outcome.winner_id,
        "loser_id": outcome.loser_id,
        "affects_rating": bool(outcome.affects_rating),
        "forfeiting_player_id": outcome.forfeiting_player_id,
        "inactive_player_id": outcome.inactive_player_id,
        "resolution": (
            resolution_to_dict(outcome.resolution) if outcome.resolution is not None else None
        ),
        "terminal_record": (
            outcome.terminal_record.to_dict() if outcome.terminal_record is not None else None
        ),
    }


def outcome_from_dict(data: Mapping[str, Any]) -> MatchOutcomeSummary:
    res_raw = data.get("resolution")
    term_raw = data.get("terminal_record")
    return MatchOutcomeSummary(
        reason=MatchOutcomeReason(str(data["reason"])),
        winner_id=data.get("winner_id"),
        loser_id=data.get("loser_id"),
        affects_rating=bool(data["affects_rating"]),
        forfeiting_player_id=data.get("forfeiting_player_id"),
        inactive_player_id=data.get("inactive_player_id"),
        resolution=resolution_from_dict(res_raw) if res_raw is not None else None,
        terminal_record=TerminalRecord.from_dict(term_raw) if term_raw is not None else None,
    )
