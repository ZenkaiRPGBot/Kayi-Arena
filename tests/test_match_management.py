"""Comprehensive tests for Module 5 (Challenge & Match Management)."""

from __future__ import annotations

import asyncio
import random

import pytest

from app.database import CharacterDatabase
from app.engine import SeededDrawSource, TerminationReason
from app.matches import (
    ChallengeStatus,
    ChallengeType,
    MatchLifecycleStatus,
    MatchManagementErrorCode,
    MatchManager,
    MatchOutcomeReason,
    MessageReference,
    ProvisionalTimeoutPolicy,
)
from app.scoring import SCORING_ROLES
from tests.test_database_foundation import _populate_approved_universe


class _FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _setup_db_with_two_universes() -> CharacterDatabase:
    db = CharacterDatabase()
    _populate_approved_universe(db, "naruto", count=16)
    db.publish_dataset("naruto", "naruto-v1")
    _populate_approved_universe(db, "bleach", count=16)
    db.publish_dataset("bleach", "bleach-v1")
    # Inactive universe & unpublished universe must not be eligible
    _populate_approved_universe(db, "inactive_u", count=16)
    db.publish_dataset("inactive_u", "inactive-v1")
    db.set_universe_active("inactive_u", False)
    db.create_universe("unpub_u", "Unpublished")
    return db


@pytest.mark.asyncio
async def test_draft_commands_direct_open_random_and_global_active_lock() -> None:
    db = _setup_db_with_two_universes()
    clock = _FakeClock()
    mgr = MatchManager(
        db,
        clock=clock,
        draw_source=SeededDrawSource(seed=10),
        universe_rng=random.Random(42),
    )

    # /draft -> lists only eligible active universes with published datasets
    sel, err = await mgr.handle_draft_command(player_id="p1", chat_id="c1")
    assert err is None and sel is not None
    assert sel.action == "list_universes"
    assert set(sel.eligible_universes) == {"naruto", "bleach"}

    # /draft random -> picks an eligible universe
    sel_rand, res_rand = await mgr.handle_draft_command(
        player_id="p1", chat_id="c1", universe_arg="random"
    )
    assert res_rand is not None and res_rand.accepted
    assert sel_rand is not None and sel_rand.challenge is not None
    assert sel_rand.challenge.universe_id in {"naruto", "bleach"}
    assert sel_rand.challenge.game_mode == "ranked"  # default mode

    # Self-challenge forbidden
    _, self_res = await mgr.handle_draft_command(
        player_id="p1",
        chat_id="c1",
        universe_arg="Naruto",
        reply_to_user_id="p1",
    )
    assert self_res is not None and not self_res.accepted
    assert self_res.error_code is MatchManagementErrorCode.SELF_CHALLENGE_FORBIDDEN

    # Direct challenge (/draft Naruto replying to p2)
    _, dir_res = await mgr.handle_draft_command(
        player_id="p1",
        chat_id="c1",
        universe_arg="Naruto",
        reply_to_user_id="p2",
    )
    assert dir_res is not None and dir_res.accepted
    direct_chl = dir_res.challenge
    assert direct_chl is not None
    assert direct_chl.challenge_type is ChallengeType.DIRECT

    # Non-target p3 cannot accept direct challenge; non-challenger p2 cannot cancel
    bad_acc = await mgr.accept_challenge(challenge_id=direct_chl.challenge_id, player_id="p3")
    assert not bad_acc.accepted and bad_acc.error_code is MatchManagementErrorCode.NOT_CHALLENGE_TARGET

    bad_can = await mgr.cancel_challenge(challenge_id=direct_chl.challenge_id, player_id="p2")
    assert not bad_can.accepted and bad_can.error_code is MatchManagementErrorCode.NOT_CHALLENGER

    # p2 accepts direct challenge -> match starts
    ok_acc = await mgr.accept_challenge(challenge_id=direct_chl.challenge_id, player_id="p2")
    assert ok_acc.accepted and ok_acc.match is not None
    assert mgr.get_active_match_for_player("p1") is not None
    assert mgr.get_active_match_for_player("p2") is not None

    # Neither p1 nor p2 can enter another match in a different chat or universe
    dup_create = await mgr.create_challenge(
        challenger_id="p1", chat_id="other_chat", universe_id="bleach"
    )
    assert not dup_create.accepted and dup_create.error_code is MatchManagementErrorCode.PLAYER_ALREADY_IN_MATCH

    # Even accepting the earlier open challenge fails because p1 is now in an active match
    late_acc = await mgr.accept_challenge(
        challenge_id=sel_rand.challenge.challenge_id, player_id="p3"
    )
    assert not late_acc.accepted and late_acc.error_code is MatchManagementErrorCode.PLAYER_ALREADY_IN_MATCH


@pytest.mark.asyncio
async def test_end_to_end_complete_draft_friendly_vs_ranked_and_pinned_dataset() -> None:
    db = _setup_db_with_two_universes()

    async def play_full_match(mode: str, seed: int) -> tuple[MatchManager, str]:
        mgr = MatchManager(db, clock=_FakeClock(), draw_source=SeededDrawSource(seed))
        c_res = await mgr.create_challenge(
            challenger_id="alice",
            chat_id="chat-1",
            universe_id="naruto",
            game_mode=mode,
        )
        assert c_res.accepted and c_res.challenge is not None
        acc = await mgr.accept_challenge(challenge_id=c_res.challenge.challenge_id, player_id="bob")
        assert acc.accepted and acc.match is not None
        match = acc.match
        assert match.dataset_version == "naruto-v1"

        # Publish naruto-v2 mid-match; active match must keep pinned naruto-v1
        db.reopen_to_draft("naruto_char_00")
        db.update_character_evaluation("naruto_char_00", power=5, fit={r: 5 for r in SCORING_ROLES})
        db.submit_for_review("naruto_char_00")
        db.approve_character("naruto_char_00")
        db.publish_dataset("naruto", "naruto-v2", predecessor_version="naruto-v1")

        # Attach /game message reference
        await mgr.attach_message_reference(match.match_id, MessageReference("chat-1", "msg-99"))

        skipped_once = False
        while match.status is MatchLifecycleStatus.DRAFTING:
            actor = match.public_view.active_player_id
            assert actor is not None
            sh = await mgr.shuffle_match(
                match_id=match.match_id,
                player_id=actor,
                expected_revision=match.public_view.revision,
                expected_generation=match.generation,
            )
            assert sh.accepted and sh.match is not None
            match = sh.match

            if not skipped_once and match.public_view.can_skip:
                skipped_once = True
                sk = await mgr.skip_match_character(
                    match_id=match.match_id,
                    player_id=actor,
                    expected_revision=match.public_view.revision,
                )
                assert sk.accepted and sk.match is not None
                match = sk.match
                continue

            role = match.public_view.remaining_roles[actor][0]
            asg = await mgr.assign_match_role(
                match_id=match.match_id,
                player_id=actor,
                role=role,
                expected_revision=match.public_view.revision,
            )
            assert asg.accepted and asg.match is not None
            match = asg.match

        assert match.status is MatchLifecycleStatus.COMPLETED
        assert match.dataset_version == "naruto-v1"
        assert match.outcome is not None
        assert match.outcome.resolution is not None
        assert match.outcome.resolution.dataset_version == "naruto-v1"
        assert mgr.get_active_match_for_player("alice") is None
        assert mgr.get_active_match_for_player("bob") is None
        assert len(match.message_refs) == 1

        # Idempotent resolution lookup
        res_again = await mgr.resolve_match_now(match.match_id)
        assert res_again.accepted and res_again.idempotent
        return mgr, match.match_id

    mgr_r, id_r = await play_full_match("ranked", 55)
    # Reset DB to v1 for identical seed comparison in friendly mode
    db2 = _setup_db_with_two_universes()
    mgr_f = MatchManager(db2, clock=_FakeClock(), draw_source=SeededDrawSource(55))
    c_f = await mgr_f.create_challenge(challenger_id="alice", chat_id="chat-1", universe_id="naruto", game_mode="friendly")
    a_f = await mgr_f.accept_challenge(challenge_id=c_f.challenge.challenge_id, player_id="bob")
    m_f = a_f.match
    skipped = False
    while m_f.status is MatchLifecycleStatus.DRAFTING:
        actor = m_f.public_view.active_player_id
        m_f = (await mgr_f.shuffle_match(match_id=m_f.match_id, player_id=actor, expected_revision=m_f.public_view.revision)).match
        if not skipped and m_f.public_view.can_skip:
            skipped = True
            m_f = (await mgr_f.skip_match_character(match_id=m_f.match_id, player_id=actor, expected_revision=m_f.public_view.revision)).match
            continue
        m_f = (await mgr_f.assign_match_role(match_id=m_f.match_id, player_id=actor, role=m_f.public_view.remaining_roles[actor][0], expected_revision=m_f.public_view.revision)).match

    ranked_res = mgr_r.get_match(id_r)
    assert ranked_res.outcome.affects_rating is True
    assert m_f.outcome.affects_rating is False
    assert ranked_res.outcome.resolution.summary == m_f.outcome.resolution.summary
    assert ranked_res.outcome.resolution.outcome == m_f.outcome.resolution.outcome


@pytest.mark.asyncio
async def test_inactivity_skip_does_not_reset_timer_stale_timeout_and_abandonment() -> None:
    db = _setup_db_with_two_universes()
    clock = _FakeClock(start=1000.0)
    policy = ProvisionalTimeoutPolicy(challenge_ttl_seconds=60.0, turn_timeout_seconds=30.0, claim_window_seconds=20.0)
    mgr = MatchManager(db, timeout_policy=policy, clock=clock, draw_source=SeededDrawSource(9))

    c_res = await mgr.create_challenge(challenger_id="p1", chat_id="c1", universe_id="naruto")
    acc = await mgr.accept_challenge(challenge_id=c_res.challenge.challenge_id, player_id="p2")
    match = acc.match
    initial_turn_start = match.turn_started_at
    actor = match.public_view.active_player_id
    opponent = "p2" if actor == "p1" else "p1"

    # Skip does NOT reset turn_started_at
    clock.advance(20.0)
    sh = await mgr.shuffle_match(match_id=match.match_id, player_id=actor, expected_revision=match.public_view.revision)
    assert sh.accepted
    sk = await mgr.skip_match_character(match_id=match.match_id, player_id=actor, expected_revision=sh.match.public_view.revision)
    assert sk.accepted
    assert sk.match.turn_started_at == initial_turn_start

    # Stale timeout callback referencing revision=0 fails without modifying match
    clock.advance(15.0)  # total elapsed = 35s >= 30s
    stale_to = await mgr.handle_turn_timeout(
        match_id=match.match_id,
        expected_revision=0,
        expected_turn_number=1,
    )
    assert not stale_to.accepted and stale_to.error_code is MatchManagementErrorCode.STALE_TIMEOUT_EVENT

    # Current timeout succeeds -> offers victory claim to opponent
    valid_to = await mgr.handle_turn_timeout(
        match_id=match.match_id,
        expected_revision=sk.match.public_view.revision,
        expected_turn_number=1,
    )
    assert valid_to.accepted
    assert valid_to.match.inactivity_claim_offered_to == opponent

    # Claim window expires without opponent claiming -> ABANDONED (no winner)
    clock.advance(25.0)
    ab = await mgr.handle_claim_window_timeout(
        match_id=match.match_id,
        expected_generation=valid_to.match.generation,
    )
    assert ab.accepted and ab.match.status is MatchLifecycleStatus.ABANDONED
    assert ab.match.outcome.reason is MatchOutcomeReason.MUTUAL_INACTIVITY_ABANDONMENT
    assert ab.match.outcome.winner_id is None
    assert ab.match.outcome.affects_rating is False
    assert ab.match.outcome.resolution is None

    # Terminated/abandoned match cannot enter normal resolution
    res_bad = await mgr.resolve_match_now(match.match_id)
    assert not res_bad.accepted and res_bad.error_code is MatchManagementErrorCode.TERMINATED_MATCH_CANNOT_RESOLVE


@pytest.mark.asyncio
async def test_forfeit_inactivity_win_and_concurrency_races() -> None:
    db = _setup_db_with_two_universes()
    clock = _FakeClock()
    mgr = MatchManager(db, clock=clock, draw_source=SeededDrawSource(3))

    # Race 1: 3 players try to accept one open challenge simultaneously -> exactly 1 wins
    c_open = await mgr.create_challenge(challenger_id="p1", chat_id="c1", universe_id="naruto")
    r_a, r_b, r_c = await asyncio.gather(
        mgr.accept_challenge(challenge_id=c_open.challenge.challenge_id, player_id="p2"),
        mgr.accept_challenge(challenge_id=c_open.challenge.challenge_id, player_id="p3"),
        mgr.accept_challenge(challenge_id=c_open.challenge.challenge_id, player_id="p4"),
    )
    winners = [r for r in (r_a, r_b, r_c) if r.accepted]
    assert len(winners) == 1
    match = winners[0].match
    opponent = match.players[1]

    # Race 2: Voluntary forfeit & stale generation button click
    stale_gen = match.generation
    forfeit_res, shuffle_res = await asyncio.gather(
        mgr.forfeit_match(match_id=match.match_id, player_id="p1", expected_generation=stale_gen),
        mgr.shuffle_match(match_id=match.match_id, player_id=match.public_view.active_player_id, expected_revision=0, expected_generation=stale_gen),
    )
    assert forfeit_res.accepted
    if shuffle_res.accepted:
        # If shuffle ran first, forfeit incremented generation & terminated
        assert forfeit_res.match.status is MatchLifecycleStatus.FORFEITED
    else:
        assert shuffle_res.error_code in {
            MatchManagementErrorCode.MATCH_NOT_ACTIVE,
            MatchManagementErrorCode.STALE_CONTROL_GENERATION,
        }
    final_m = mgr.get_match(match.match_id)
    assert final_m.status is MatchLifecycleStatus.FORFEITED
    assert final_m.outcome.winner_id == opponent
    assert final_m.outcome.resolution is None

    # Idempotent forfeit repeat
    idem = await mgr.forfeit_match(match_id=match.match_id, player_id="p1")
    assert idem.accepted and idem.idempotent

    # Race 3: Accept vs Cancel on a fresh challenge -> exactly 1 succeeds
    c2 = await mgr.create_challenge(challenger_id="p1", chat_id="c1", universe_id="bleach")
    acc2, can2 = await asyncio.gather(
        mgr.accept_challenge(challenge_id=c2.challenge.challenge_id, player_id="p5"),
        mgr.cancel_challenge(challenge_id=c2.challenge.challenge_id, player_id="p1"),
    )
    assert (acc2.accepted and not can2.accepted) or (can2.accepted and not acc2.accepted)
