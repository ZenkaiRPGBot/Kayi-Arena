"""Comprehensive tests for KAYI ARENA — ARENA LOGS 2.0 (Compact Administrative Logging)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from aiogram.exceptions import TelegramForbiddenError

from app.database import CharacterDatabase
from app.matches import (
    MatchLifecycleStatus,
    MatchManager,
    MatchOutcomeReason,
    MatchOutcomeSummary,
)
from app.persistence import SqliteMatchStore
from app.resolution import (
    DecidedBy,
    MatchOutcome,
    MatchResolutionSuccess,
    MatchupParticipant,
    MatchupWinner,
    ResolutionSummary,
    RoleMatchup,
)
from app.scoring import DatasetKind
from app.telegram import BotConfig, create_dispatcher
from app.telegram.constants import (
    ROLE_ORDER,
    SECTION_SEPARATOR,
    STATUS_DEFEAT,
    STATUS_DRAW,
    STATUS_NO_RESPONSE,
    STATUS_TIMEOUT,
    STATUS_VICTORY,
)
from app.telegram.gameplay_logs import GameplayLogger, IST
from tests.test_telegram_ui import FakeClock, MockBotRecorder, _make_user, _seed_naruto_db


def _fixed_clock() -> datetime:
    return datetime(2026, 11, 27, 19, 19, 24, tzinfo=IST)


@pytest.mark.asyncio
async def test_match_started_not_sent_to_channel_but_persisted_in_db(tmp_path: Any) -> None:
    db = CharacterDatabase(":memory:")
    _seed_naruto_db(db)
    store = SqliteMatchStore(tmp_path / "state.sqlite3")
    mgr = MatchManager(db, dataset_kind=DatasetKind.PRODUCTION, store=store)
    bot = MockBotRecorder()
    cfg = BotConfig(bot_token="fake:t", arena_log_channel_id=-100999888777)
    _, coord = create_dispatcher(bot=bot, config=cfg, db=db, manager=mgr, store=store)
    coord.register_user(_make_user(101, "Obito"))
    coord.register_user(_make_user(202, "Kiyomi"))

    chl = (
        await mgr.create_challenge(challenger_id="101", chat_id="-1001800918110", universe_id="naruto")
    ).challenge
    match = (await mgr.accept_challenge(challenge_id=chl.challenge_id, player_id="202")).match
    assert match is not None

    await coord.start_match_ui(match, chat_id="-1001800918110")
    # Only group board + card sent; zero messages sent to ARENA_LOG_CHANNEL_ID
    channel_msgs = [m for m in bot.sent_messages if m["chat_id"] == -100999888777]
    assert len(channel_msgs) == 0
    # Authoritative DB still holds the match & challenge metadata
    assert store.load_match(match.match_id) is not None

    await coord.shutdown()
    store.close()
    db.close()


@pytest.mark.asyncio
async def test_completed_tiebreaker_and_draw_log_formats() -> None:
    db = CharacterDatabase(":memory:")
    _seed_naruto_db(db)
    clock = FakeClock()
    mgr = MatchManager(db, dataset_kind=DatasetKind.PRODUCTION, clock=clock)
    bot = MockBotRecorder()
    logger_inst = GameplayLogger(bot, channel_id=-100999888777, clock=_fixed_clock)

    chl = (
        await mgr.create_challenge(challenger_id="6110294479", chat_id="-1001800918110", universe_id="naruto")
    ).challenge
    match = (await mgr.accept_challenge(challenge_id=chl.challenge_id, player_id="986380678")).match
    assert match is not None

    chars = {c.character_id: c for c in db.list_characters(universe_id="naruto")}
    cids = list(chars.keys())
    names = {"6110294479": "Kiyomi <Pro>", "986380678": "Obito 忍"}

    # Build a completed resolution with 1 draw (Strategist), p1 winning 2, p2 winning 4
    matchups = []
    for idx, role in enumerate(ROLE_ORDER):
        c1, c2 = cids[idx * 2], cids[idx * 2 + 1]
        if idx == 1:
            s1, s2, w = 91, 91, MatchupWinner.DRAW
        elif idx in {0, 5}:
            s1, s2, w = 76, 32, MatchupWinner.PLAYER_1
        else:
            s1, s2, w = 40, 90, MatchupWinner.PLAYER_2
        matchups.append(
            RoleMatchup(
                role=role,
                player_1=MatchupParticipant(character_id=c1, power=4, fit=4, score=s1),
                player_2=MatchupParticipant(character_id=c2, power=4, fit=4, score=s2),
                winner=w,
                margin=abs(s1 - s2),
            )
        )

    res = MatchResolutionSuccess(
        resolution_version="RES-1.0",
        scoring_version="SCORE-1.0",
        dataset_version=match.dataset_version,
        match_id=match.match_id,
        universe_id="naruto",
        game_mode="ranked",
        starting_player="6110294479",
        players={"6110294479": {}, "986380678": {}},
        outcome=MatchOutcome.PLAYER_2_WIN,
        decided_by=DecidedBy.MATCHUP_COUNT,
        summary=ResolutionSummary(
            wins_player_1=2,
            wins_player_2=4,
            draws=1,
            total_player_1=363,
            total_player_2=440,
            total_margin=77,
        ),
        matchups=tuple(matchups),
    )
    completed = replace(
        match,
        status=MatchLifecycleStatus.COMPLETED,
        updated_at=match.created_at + 254.0,
        outcome=MatchOutcomeSummary(
            reason=MatchOutcomeReason.NORMAL_MATCHUP_COUNT,
            winner_id="986380678",
            loser_id="6110294479",
            affects_rating=True,
            resolution=res,
        ),
    )

    ok = await logger_inst.log_match_terminal(
        completed,
        universe_name="Naruto",
        player_names=names,
        char_lookup=chars,
        chat_id="-1001800918110",
        group_title="Chulbuli Duniya & Friends",
        group_link="https://t.me/c/1800918110",
    )
    assert ok is True
    txt = bot.sent_messages[-1]["text"]
    assert "📋 𝐌𝐀𝐓𝐂𝐇 𝐂𝐎𝐌𝐏𝐋𝐄𝐓𝐄𝐃" in txt and "#COMPLETED" in txt
    assert f"<code>{match.match_id}</code>" in txt
    assert "🍥 Naruto · Ranked · 4m 14s" in txt
    assert '<a href="https://t.me/c/1800918110">Chulbuli Duniya &amp; Friends</a> (<code>-1001800918110</code>)' in txt
    assert f'🔵 <b><a href="tg://user?id=6110294479">Kiyomi &lt;Pro&gt;</a></b> 〔{STATUS_DEFEAT}〕 · <code>6110294479</code>' in txt
    assert f'🔴 <b><a href="tg://user?id=986380678">Obito 忍</a></b> 〔{STATUS_VICTORY}〕 · <code>986380678</code>' in txt
    assert "▸ <b>Score:</b> 363/700 · <b>Roles won:</b> 2" in txt
    assert "▸ <b>Score:</b> 440/700 · <b>Roles won:</b> 4" in txt
    assert "▸ <b>Drawn roles:</b> 1" in txt
    assert "▸ <b>Decided by:</b> Role wins" in txt
    assert "𝐑𝐎𝐋𝐄 𝐀𝐒𝐒𝐈𝐆𝐍𝐌𝐄𝐍𝐓𝐒" in txt
    # Winning bracket on Captain, NO bracket on drawn Strategist
    assert f"<b>〔{chars[cids[0]].name} · 76〕</b> — {chars[cids[1]].name} · 32" in txt
    assert f"🧠 <b>Strategist:</b> {chars[cids[2]].name} · 91 — {chars[cids[3]].name} · 91" in txt
    assert f"<b>Dataset:</b> <code>{match.dataset_version}</code>" in txt
    assert "27 Nov 2026 · 07:19:24 PM IST" in txt
    # Removed redundant fields must NOT appear
    for forbidden in ("Challenge ID", "𝐆𝐑𝐎𝐔𝐏 𝐈𝐍𝐅𝐎", "𝐏𝐋𝐀𝐘𝐄𝐑𝐒", "𝐂𝐎𝐍𝐂𝐋𝐔𝐒𝐈𝐎𝐍", "Starting Player", "Username", "🟡", "⚪"):
        assert forbidden not in txt

    # Duplicate terminal log suppressed
    assert await logger_inst.log_match_terminal(
        completed,
        universe_name="Naruto",
        player_names=names,
        char_lookup=chars,
        chat_id="-1001800918110",
    ) is False

    # Tiebreaker & Complete Draw (fresh match IDs so dedup allows)
    tie_res = replace(
        res,
        decided_by=DecidedBy.COMBINED_SCORE,
        summary=ResolutionSummary(3, 3, 1, 410, 440, 30),
    )
    tie_m = replace(
        completed,
        match_id="match-tie-001",
        outcome=MatchOutcomeSummary(
            reason=MatchOutcomeReason.NORMAL_COMBINED_SCORE,
            winner_id="986380678",
            loser_id="6110294479",
            affects_rating=True,
            resolution=tie_res,
        ),
    )
    assert await logger_inst.log_match_terminal(
        tie_m, universe_name="One Piece", player_names=names, char_lookup=chars, chat_id="-1001800918110"
    ) is True
    assert "▸ <b>Decided by:</b> Total team score" in bot.sent_messages[-1]["text"]

    draw_res = replace(
        res,
        outcome=MatchOutcome.DRAW,
        decided_by=DecidedBy.NONE,
        summary=ResolutionSummary(3, 3, 1, 420, 420, 0),
    )
    draw_m = replace(
        completed,
        match_id="match-draw-001",
        universe_id="one_piece",
        game_mode="friendly",
        outcome=MatchOutcomeSummary(
            reason=MatchOutcomeReason.NORMAL_DRAW,
            winner_id=None,
            loser_id=None,
            affects_rating=False,
            resolution=draw_res,
        ),
    )
    assert await logger_inst.log_match_terminal(
        draw_m, universe_name="One Piece", player_names=names, char_lookup=chars, chat_id="-1001800918110"
    ) is True
    draw_txt = bot.sent_messages[-1]["text"]
    assert "🏴‍☠️ One Piece · Friendly" in draw_txt
    assert draw_txt.count(f"〔{STATUS_DRAW}〕") == 2
    assert "▸ <b>Decided by:</b> Equal role wins and team scores" in draw_txt
    db.close()


@pytest.mark.asyncio
async def test_forfeit_inactivity_abandoned_and_partial_vs_empty_drafts() -> None:
    db = CharacterDatabase(":memory:")
    _seed_naruto_db(db)
    clock = FakeClock()
    mgr = MatchManager(db, dataset_kind=DatasetKind.PRODUCTION, clock=clock)
    bot = MockBotRecorder()
    logger_inst = GameplayLogger(bot, channel_id=-100999888777, clock=_fixed_clock)
    chars = {c.character_id: c for c in db.list_characters(universe_id="naruto")}
    names = {"6110294479": "Kiyomi", "986380678": "Obito"}

    # 1. Forfeit with 0 assigned characters -> ROLE ASSIGNMENTS section omitted
    chl1 = (await mgr.create_challenge(challenger_id="6110294479", chat_id="-1001", universe_id="naruto")).challenge
    m1 = (await mgr.accept_challenge(challenge_id=chl1.challenge_id, player_id="986380678")).match
    f_res = (await mgr.forfeit_match(match_id=m1.match_id, player_id="986380678", expected_generation=m1.generation)).match
    assert f_res is not None
    await logger_inst.log_match_terminal(
        f_res, universe_name="Naruto", player_names=names, char_lookup=chars, chat_id="-1001", group_title="Chulbuli Duniya"
    )
    ftxt = bot.sent_messages[-1]["text"]
    assert "🏳️ 𝐌𝐀𝐓𝐂𝐇 𝐅𝐎𝐑𝐅𝐄𝐈𝐓𝐄𝐃" in ftxt and "#FORFEITED" in ftxt
    assert "▸ <b>Assigned:</b> 0/7" in ftxt
    assert "surrendered." in ftxt
    assert "𝐑𝐎𝐋𝐄 𝐀𝐒𝐒𝐈𝐆𝐍𝐌𝐄𝐍𝐓𝐒" not in ftxt

    # 2. Forfeit with 1 partial role -> shows "Unassigned" on empty side, no brackets
    chl2 = (await mgr.create_challenge(challenger_id="6110294479", chat_id="-1001", universe_id="naruto")).challenge
    m2 = (await mgr.accept_challenge(challenge_id=chl2.challenge_id, player_id="986380678")).match
    active = m2.draft_snapshot.active_player_id or "6110294479"
    sh = (await mgr.shuffle_match(match_id=m2.match_id, player_id=active, expected_revision=m2.draft_snapshot.revision, expected_generation=m2.generation)).match
    asg = (await mgr.assign_match_role(match_id=sh.match_id, player_id=active, role="Captain", expected_revision=sh.draft_snapshot.revision, expected_generation=sh.generation)).match
    f2 = (await mgr.forfeit_match(match_id=asg.match_id, player_id="986380678", expected_generation=asg.generation)).match
    await logger_inst.log_match_terminal(
        f2, universe_name="Naruto", player_names=names, char_lookup=chars, chat_id="-1001", group_title="Chulbuli Duniya"
    )
    f2txt = bot.sent_messages[-1]["text"]
    assert "𝐑𝐎𝐋𝐄 𝐀𝐒𝐒𝐈𝐆𝐍𝐌𝐄𝐍𝐓𝐒" in f2txt
    assert "👑 <b>Captain:</b>" in f2txt
    assert "Unassigned" in f2txt
    assert "〔" not in f2txt.split("𝐑𝐎𝐋𝐄 𝐀𝐒𝐒𝐈𝐆𝐍𝐌𝐄𝐍𝐓𝐒")[1]

    # 3. Inactivity Victory & Abandoned
    chl3 = (await mgr.create_challenge(challenger_id="6110294479", chat_id="-1001", universe_id="naruto")).challenge
    m3 = (await mgr.accept_challenge(challenge_id=chl3.challenge_id, player_id="986380678")).match
    clock.advance(125.0)
    to = (await mgr.handle_turn_timeout(match_id=m3.match_id, expected_revision=m3.draft_snapshot.revision, expected_turn_number=m3.turn_number_at_start)).match
    opp = to.inactivity_claim_offered_to or "986380678"
    cv = (await mgr.claim_inactivity_victory(match_id=to.match_id, player_id=opp, expected_generation=to.generation)).match
    await logger_inst.log_match_terminal(
        cv, universe_name="Naruto", player_names=names, char_lookup=chars, chat_id="-1001", group_title="Chulbuli Duniya"
    )
    itxt = bot.sent_messages[-1]["text"]
    assert "⌛ 𝐈𝐍𝐀𝐂𝐓𝐈𝐕𝐈𝐓𝐘 𝐕𝐈𝐂𝐓𝐎𝐑𝐘" in itxt and "#INACTIVITY" in itxt
    assert "'s turn expired." in itxt
    assert "▸ <b>Decision:</b> Victory claimed by" in itxt

    chl4 = (await mgr.create_challenge(challenger_id="6110294479", chat_id="-1001", universe_id="naruto")).challenge
    m4 = (await mgr.accept_challenge(challenge_id=chl4.challenge_id, player_id="986380678")).match
    clock.advance(125.0)
    to4 = (await mgr.handle_turn_timeout(match_id=m4.match_id, expected_revision=m4.draft_snapshot.revision, expected_turn_number=m4.turn_number_at_start)).match
    clock.advance(65.0)
    ab = (await mgr.handle_claim_window_timeout(match_id=to4.match_id, expected_generation=to4.generation)).match
    await logger_inst.log_match_terminal(
        ab, universe_name="Naruto", player_names=names, char_lookup=chars, chat_id="-1001", group_title="Chulbuli Duniya"
    )
    atxt = bot.sent_messages[-1]["text"]
    assert "🚫 𝐌𝐀𝐓𝐂𝐇 𝐀𝐁𝐀𝐍𝐃𝐎𝐍𝐄𝐃" in atxt and "#ABANDONED" in atxt
    assert STATUS_TIMEOUT in atxt and STATUS_NO_RESPONSE in atxt
    assert STATUS_VICTORY not in atxt and STATUS_DEFEAT not in atxt and STATUS_DRAW not in atxt
    assert "▸ <b>Reason:</b> Response window expired." in atxt
    assert "▸ <b>Result:</b> No win or loss recorded." in atxt
    db.close()


@pytest.mark.asyncio
async def test_recovery_success_failure_error_and_isolation() -> None:
    db = CharacterDatabase(":memory:")
    _seed_naruto_db(db)
    mgr = MatchManager(db, dataset_kind=DatasetKind.PRODUCTION)
    bot = MockBotRecorder()
    logger_inst = GameplayLogger(bot, channel_id=-100999888777, clock=_fixed_clock)
    names = {"101": "Obito"}

    chl = (await mgr.create_challenge(challenger_id="101", chat_id="-1001800918110", universe_id="naruto")).challenge
    match = (await mgr.accept_challenge(challenge_id=chl.challenge_id, player_id="202")).match
    assert match is not None

    assert await logger_inst.log_recovery(
        match,
        succeeded=True,
        requester_id="101",
        player_names=names,
        chat_id="-1001800918110",
        group_title="Chulbuli Duniya",
        group_link="https://t.me/c/1800918110",
    ) is True
    rtxt = bot.sent_messages[-1]["text"]
    assert "🔄 𝐌𝐀𝐓𝐂𝐇 𝐑𝐄𝐂𝐎𝐕𝐄𝐑𝐄𝐃" in rtxt and "#RECOVERED" in rtxt
    assert "Generation" not in rtxt and "𝐆𝐑𝐎𝐔𝐏 𝐈𝐍𝐅𝐎" not in rtxt

    assert await logger_inst.log_recovery(
        match,
        succeeded=False,
        requester_id="101",
        player_names=names,
        chat_id="-1001800918110",
        group_title="Chulbuli Duniya",
        stage="Action Card restoration",
        detail="Telegram API request failed",
    ) is True
    ftxt = bot.sent_messages[-1]["text"]
    assert "⚠️ 𝐑𝐄𝐂𝐎𝐕𝐄𝐑𝐘 𝐅𝐀𝐈𝐋𝐄𝐃" in ftxt and "#RECOVERY_FAILED" in ftxt
    assert "▸ <b>Stage:</b> Action Card restoration" in ftxt
    assert "▸ <b>State:</b> Match preserved; recovery incomplete" in ftxt

    assert await logger_inst.log_error(
        match_id=match.match_id,
        context="Final result delivery",
        error_name="TelegramBadRequest",
        chat_id="-1001800918110",
        group_title="Chulbuli Duniya",
        state_note="Match outcome persisted",
    ) is True
    etxt = bot.sent_messages[-1]["text"]
    assert "⚠️ 𝐆𝐀𝐌𝐄𝐏𝐋𝐀𝐘 𝐄𝐑𝐑𝐎𝐑" in etxt and "#ERROR" in etxt
    assert "▸ <b>Operation:</b> Final result delivery" in etxt
    assert "▸ <b>State:</b> Match outcome persisted" in etxt

    async def _raise_forbidden(**_kwargs: Any) -> Any:
        raise TelegramForbiddenError(method=SimpleNamespace(), message="Forbidden")

    bot.send_message = _raise_forbidden  # type: ignore[method-assign]
    assert await logger_inst.log_error(context="test", error_name="TestErr") is False
    db.close()
