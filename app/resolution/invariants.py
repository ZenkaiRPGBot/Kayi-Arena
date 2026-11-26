"""Resolution invariant verification (I1-I7)."""

from __future__ import annotations

from app.resolution.models import (
    DecidedBy,
    MatchOutcome,
    MatchResolutionSuccess,
    MatchupWinner,
)
from app.scoring import SCORING_ROLES


class ResolutionInvariantError(RuntimeError):
    """Raised when a match resolution output violates invariants I1-I7."""


def validate_resolution_invariants(result: MatchResolutionSuccess) -> None:
    """Verify invariants I1-I7 on ``result``."""
    summary = result.summary

    # I1: wins_player_1 + wins_player_2 + draws == 7
    if summary.wins_player_1 + summary.wins_player_2 + summary.draws != 7:
        raise ResolutionInvariantError("Matchup counts do not sum to 7 (I1)")

    # I2: exactly seven matchups, one per canonical role in canonical order
    if tuple(m.role for m in result.matchups) != SCORING_ROLES:
        raise ResolutionInvariantError("Matchups do not match canonical 7-role order (I2)")

    # I3: all role scores are valid strict integers
    for m in result.matchups:
        if type(m.player_1.score) is not int or type(m.player_2.score) is not int:
            raise ResolutionInvariantError("Role scores must be integers (I3)")
        if m.winner is MatchupWinner.PLAYER_1 and not (m.player_1.score > m.player_2.score):
            raise ResolutionInvariantError("Inconsistent player_1 matchup winner")
        if m.winner is MatchupWinner.PLAYER_2 and not (m.player_2.score > m.player_1.score):
            raise ResolutionInvariantError("Inconsistent player_2 matchup winner")
        if m.winner is MatchupWinner.DRAW and not (m.player_1.score == m.player_2.score):
            raise ResolutionInvariantError("Inconsistent draw matchup winner")

    # I4, I5, I6: victory method vs counts & totals
    if summary.wins_player_1 != summary.wins_player_2:
        if result.decided_by is not DecidedBy.MATCHUP_COUNT:
            raise ResolutionInvariantError("Expected decided_by=matchup_count (I4)")
        expected_outcome = (
            MatchOutcome.PLAYER_1_WIN
            if summary.wins_player_1 > summary.wins_player_2
            else MatchOutcome.PLAYER_2_WIN
        )
        if result.outcome is not expected_outcome:
            raise ResolutionInvariantError("Outcome disagrees with matchup counts (I4)")
    else:
        # I7: equal victory counts require odd drawn-matchup count (1, 3, 5, or 7)
        if summary.draws not in (1, 3, 5, 7):
            raise ResolutionInvariantError(
                f"Equal victory counts require odd draws, got {summary.draws} (I7)"
            )
        if summary.total_player_1 != summary.total_player_2:
            if result.decided_by is not DecidedBy.COMBINED_SCORE:
                raise ResolutionInvariantError("Expected decided_by=combined_score (I5)")
            expected_outcome = (
                MatchOutcome.PLAYER_1_WIN
                if summary.total_player_1 > summary.total_player_2
                else MatchOutcome.PLAYER_2_WIN
            )
            if result.outcome is not expected_outcome:
                raise ResolutionInvariantError("Outcome disagrees with combined totals (I5)")
        else:
            if result.decided_by is not DecidedBy.NONE or result.outcome is not MatchOutcome.DRAW:
                raise ResolutionInvariantError("Expected draw with decided_by=none (I6)")
