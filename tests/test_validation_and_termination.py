"""Tests for every validation error code, immutability on rejection, and termination."""

from __future__ import annotations

import pytest

from app.engine import (
    DraftPhase,
    ErrorCode,
    MatchStatus,
    ScriptedDrawSource,
    SeededDrawSource,
    TerminationReason,
    assign_role,
    shuffle,
    skip_character,
    start_draft,
    terminate_draft,
    validate_snapshot_invariants,
)
from tests.conftest import DEFAULT_WEIGHTS, make_catalog


def _assert_rejected_unchanged(res, original_snap, code: ErrorCode) -> None:
    assert res.accepted is False
    assert res.error_code is code
    assert res.events == ()
    assert res.snapshot.to_json() == original_snap.to_json()
    assert res.snapshot.revision == original_snap.revision


def test_all_drafting_error_codes_and_unchanged_state() -> None:
    catalog = make_catalog(16)
    source = SeededDrawSource(seed=12)
    snap = start_draft(
        match_id="m-err",
        players=("p1", "p2"),
        universe_id="u1",
        mode="ranked",
        catalog=catalog,
        rarity_weights=DEFAULT_WEIGHTS,
        dataset_version="ds-1",
        draw_source=source,
        forced_starter="p1",
    ).snapshot

    # UNKNOWN_PLAYER
    _assert_rejected_unchanged(
        shuffle(snap, player_id="intruder", expected_revision=snap.revision, draw_source=source),
        snap,
        ErrorCode.UNKNOWN_PLAYER,
    )
    # STALE_REVISION
    _assert_rejected_unchanged(
        shuffle(snap, player_id="p1", expected_revision=99, draw_source=source),
        snap,
        ErrorCode.STALE_REVISION,
    )
    # NOT_YOUR_TURN
    _assert_rejected_unchanged(
        shuffle(snap, player_id="p2", expected_revision=snap.revision, draw_source=source),
        snap,
        ErrorCode.NOT_YOUR_TURN,
    )
    # NO_CHARACTER_DRAWN (assign & skip while AWAITING_SHUFFLE)
    _assert_rejected_unchanged(
        assign_role(snap, player_id="p1", role="Captain", expected_revision=snap.revision),
        snap,
        ErrorCode.NO_CHARACTER_DRAWN,
    )
    _assert_rejected_unchanged(
        skip_character(snap, player_id="p1", expected_revision=snap.revision),
        snap,
        ErrorCode.NO_CHARACTER_DRAWN,
    )

    # Shuffle -> AWAITING_DECISION
    snap = shuffle(snap, player_id="p1", expected_revision=snap.revision, draw_source=source).snapshot

    # WRONG_PHASE (second shuffle while holding a character)
    _assert_rejected_unchanged(
        shuffle(snap, player_id="p1", expected_revision=snap.revision, draw_source=source),
        snap,
        ErrorCode.WRONG_PHASE,
    )
    # INVALID_ROLE
    _assert_rejected_unchanged(
        assign_role(snap, player_id="p1", role="Wizard", expected_revision=snap.revision),
        snap,
        ErrorCode.INVALID_ROLE,
    )

    # Assign Captain -> p2's turn -> back to p1 -> try ROLE_OCCUPIED
    snap = assign_role(snap, player_id="p1", role="Captain", expected_revision=snap.revision).snapshot
    snap = shuffle(snap, player_id="p2", expected_revision=snap.revision, draw_source=source).snapshot
    snap = assign_role(snap, player_id="p2", role="Captain", expected_revision=snap.revision).snapshot
    snap = shuffle(snap, player_id="p1", expected_revision=snap.revision, draw_source=source).snapshot
    _assert_rejected_unchanged(
        assign_role(snap, player_id="p1", role="Captain", expected_revision=snap.revision),
        snap,
        ErrorCode.ROLE_OCCUPIED,
    )


@pytest.mark.parametrize("reason", list(TerminationReason))
@pytest.mark.parametrize("while_holding", [False, True])
def test_terminate_all_reasons_and_phases_releases_held_character(
    reason: TerminationReason, while_holding: bool
) -> None:
    catalog = make_catalog(16)
    source = ScriptedDrawSource(starting_player="p1", draws=["char_000", "char_001"])
    snap = start_draft(
        match_id=f"term-{reason.value}-{while_holding}",
        players=("p1", "p2"),
        universe_id="u1",
        mode="ranked",
        catalog=catalog,
        rarity_weights=DEFAULT_WEIGHTS,
        dataset_version="ds-1",
        draw_source=source,
    ).snapshot

    if while_holding:
        snap = shuffle(snap, player_id="p1", expected_revision=snap.revision, draw_source=source).snapshot
        assert snap.phase is DraftPhase.AWAITING_DECISION
        held_id = snap.held_character.character_id
    else:
        held_id = None

    # Invalid reason and unknown subject player rejected without modifying state
    _assert_rejected_unchanged(
        terminate_draft(snap, reason="bogus"),
        snap,
        ErrorCode.INVALID_REASON,
    )
    _assert_rejected_unchanged(
        terminate_draft(snap, reason=reason, subject_player_id="stranger"),
        snap,
        ErrorCode.UNKNOWN_PLAYER,
    )

    term = terminate_draft(
        snap,
        reason=reason,
        subject_player_id="p1",
        source_label="match_mgr",
        caller_reference="req-123",
    )
    assert term.accepted
    term_snap = term.snapshot
    validate_snapshot_invariants(term_snap)
    assert term_snap.status is MatchStatus.TERMINATED
    assert term_snap.held_character is None
    assert term_snap.last_skipped_id is None
    assert term_snap.terminal_record is not None
    assert term_snap.terminal_record.reason is reason
    if held_id is not None:
        assert term_snap.terminal_record.held_character_at_termination.character_id == held_id
        assert any(c.character_id == held_id for c in term_snap.available_pool())

    # Public terminal summary omits internal caller metadata
    assert term.public_view.terminal_summary is not None
    assert term.public_view.terminal_summary.reason is reason
    assert term.public_view.terminal_summary.subject_player_id == "p1"
    assert not hasattr(term.public_view.terminal_summary, "caller_reference")

    # Subsequent actions rejected with MATCH_NOT_ACTIVE
    _assert_rejected_unchanged(
        shuffle(term_snap, player_id="p1", expected_revision=term_snap.revision, draw_source=source),
        term_snap,
        ErrorCode.MATCH_NOT_ACTIVE,
    )
    _assert_rejected_unchanged(
        terminate_draft(term_snap, reason=TerminationReason.CANCELLED),
        term_snap,
        ErrorCode.MATCH_NOT_ACTIVE,
    )
