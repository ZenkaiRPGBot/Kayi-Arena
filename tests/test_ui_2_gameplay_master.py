"""Comprehensive regression tests for UI 2.0 Gameplay Master (Modules 09-17)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from aiogram.exceptions import TelegramForbiddenError

from app.database import CharacterDatabase, SpeciesKind
from app.engine import DraftPhase
from app.matches import MatchLifecycleStatus, MatchManager, MatchOutcomeReason
from app.persistence import SqliteMatchStore
from app.scoring import DatasetKind, SCORING_ROLES
from app.telegram import (
    BotConfig,
    create_dispatcher,
    encode_cb,
)
from app.telegram.constants import (
    ROLE_ORDER,
    SECTION_SEPARATOR,
    STATUS_CURRENT_TURN,
    STATUS_DEFEAT,
    STATUS_DRAW,
    STATUS_NO_RESPONSE,
    STATUS_SKIPPED,
    STATUS_TIMEOUT,
    STATUS_VICTORY,
    to_bold_sans,
    to_bold_serif_upper,
)
from app.telegram.gameplay_logs import GameplayLogger
from app.telegram.keyboards import (
    build_active_game_keyboard,
    build_awaiting_shuffle_keyboard,
    build_character_revealed_keyboard,
    build_detailed_results_keyboard,
    build_draft_board_keyboard,
    build_forfeit_confirm_keyboard,
    build_inactivity_keyboard,
    build_match_results_keyboard,
    build_no_active_game_keyboard,
    build_recover_confirm_keyboard,
    build_recover_success_keyboard,
)
from app.telegram.texts import (
    render_active_game,
    render_awaiting_shuffle_card,
    render_detailed_result_page,
    render_draft_board,
    render_forfeit_confirmation,
    render_match_results,
    render_no_active_game,
    render_recover_confirmation,
    render_recover_failed,
    render_recover_success,
    render_revealed_character_card,
    render_turn_expired_card,
)
from tests.test_telegram_ui import (
    FakeClock,
    MockBotRecorder,
    _make_callback_update,
    _make_message_update,
    _make_user,
    _seed_naruto_db,
)


def _btn_styles(markup: Any) -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []
    for row in markup.inline_keyboard:
        for btn in row:
            dumped = btn.model_dump(exclude_none=True)
            out.append((btn.text, dumped.get("style")))
    return out


# ---------------------------------------------------------------------------
# Section 46 — Rendering Regression Tests (Screens 01-16 & Typography)
# ---------------------------------------------------------------------------


def test_typography_and_all_16_screen_templates() -> None:
    assert to_bold_serif_upper("KAYI ARENA") == "𝐊𝐀𝐘𝐈 𝐀𝐑𝐄𝐍𝐀"
    assert to_bold_serif_upper("CHARACTER DRAFT") == "𝐂𝐇𝐀𝐑𝐀𝐂𝐓𝐄𝐑 𝐃𝐑𝐀𝐅𝐓"
    assert to_bold_serif_upper("ARENA RESULT") == "𝐀𝐑𝐄𝐍𝐀 𝐑𝐄𝐒𝐔𝐋𝐓"
    assert to_bold_serif_upper("BATTLE BREAKDOWN") == "𝐁𝐀𝐓𝐓𝐋𝐄 𝐁𝐑𝐄𝐀𝐊𝐃𝐎𝐖𝐍"
    # Preserves non-Latin Unicode characters without corruption
    assert to_bold_serif_upper("Itachi 忍") == "𝐈𝐓𝐀𝐂𝐇𝐈 忍"

    db = CharacterDatabase(":memory:")
    _seed_naruto_db(db)
    clock = FakeClock()
    mgr = MatchManager(db, dataset_kind=DatasetKind.PRODUCTION, clock=clock)

    async def _run() -> None:
        chl = (
            await mgr.create_challenge(
                challenger_id="101", chat_id="-1001234567890", universe_id="naruto", game_mode="ranked"
            )
        ).challenge
        assert chl is not None
        match = (await mgr.accept_challenge(challenge_id=chl.challenge_id, player_id="202")).match
        assert match is not None

        names = {"101": "Obito <Uchiha>", "202": "Kiyomi"}
        char_lookup = {
            c.character_id: c for c in db.list_characters(universe_id="naruto")
        }

        # Screen 01 — Initial Draft Board
        board0 = render_draft_board(
            match,
            universe_name="Naruto",
            player_names=names,
            char_lookup=char_lookup,
            seconds_remaining=120.0,
        )
        assert "𝐊𝐀𝐘𝐈 𝐀𝐑𝐄𝐍𝐀" in board0
        assert "◆ <b>Universe</b> — 🍥 Naruto" in board0
        assert "◆ <b>Mode</b> — 🏆 Ranked" in board0
        assert SECTION_SEPARATOR in board0
        assert f"✦ {STATUS_CURRENT_TURN}" in board0
        assert "<i>No characters assigned.</i>" in board0
        assert "Draft progress" not in board0
        assert match.match_id not in board0
        assert "Obito &lt;Uchiha&gt;" in board0
        assert 'tg://user?id=101' in board0

        board_kb = build_draft_board_keyboard(match)
        assert _btn_styles(board_kb) == [(f"⚑ {to_bold_sans('Forfeit')}", "danger")]

        # Screen 02 — Initial Shuffle
        s02 = render_awaiting_shuffle_card(match, player_names=names, seconds_remaining=120.0)
        assert "🎲 𝐂𝐇𝐀𝐑𝐀𝐂𝐓𝐄𝐑 𝐃𝐑𝐀𝐅𝐓" in s02
        assert "Shuffle to reveal your first character." in s02
        assert "2 minutes" in s02
        s02_kb = build_awaiting_shuffle_keyboard(match)
        assert _btn_styles(s02_kb) == [(f"🎲 {to_bold_sans('Shuffle')}", "primary")]

        # Screen 03 — Character Obtained
        active = match.draft_snapshot.active_player_id or "101"
        sh = await mgr.shuffle_match(
            match_id=match.match_id,
            player_id=active,
            expected_revision=match.draft_snapshot.revision,
            expected_generation=match.generation,
        )
        assert sh.accepted and sh.match is not None
        m_obt = sh.match
        held = m_obt.draft_snapshot.held_character
        assert held is not None
        rec = char_lookup[held.character_id]
        s03 = render_revealed_character_card(
            m_obt, character=rec, universe_name="Naruto", player_names=names, seconds_remaining=102.0
        )
        assert f"✦ {to_bold_serif_upper(rec.name)}" in s03
        assert "choose a role for your character." in s03
        assert "1m 42s" in s03
        assert "Power" not in s03 and "Fit" not in s03

        s03_kb = build_character_revealed_keyboard(m_obt)
        styles03 = _btn_styles(s03_kb)
        assert styles03[-1] == (f"⏭ {to_bold_sans('SKIP')}", "danger")
        assert all(st is None for _, st in styles03[:-1])
        assert f"👑 {to_bold_sans('Captain')}" == styles03[0][0]

        # Screen 05 — Character Skipped
        sk = await mgr.skip_match_character(
            match_id=m_obt.match_id,
            player_id=active,
            expected_revision=m_obt.draft_snapshot.revision,
            expected_generation=m_obt.generation,
        )
        assert sk.accepted and sk.match is not None
        s05 = render_awaiting_shuffle_card(sk.match, player_names=names, seconds_remaining=75.0)
        assert STATUS_SKIPPED in s05
        assert "Shuffle to reveal another character." in s05
        assert "1/2" in s05

        # Screen 06 — Turn Expired (with extension, then without extension)
        clock.advance(125.0)
        to = await mgr.handle_turn_timeout(
            match_id=sk.match.match_id,
            expected_revision=sk.match.draft_snapshot.revision,
            expected_turn_number=sk.match.turn_number_at_start,
        )
        assert to.accepted and to.match is not None
        s06 = render_turn_expired_card(to.match, player_names=names)
        assert "⌛ 𝐓𝐈𝐌𝐄'𝐒 𝐔𝐏" in s06
        assert "claim victory or grant extra time." in s06
        s06_kb = build_inactivity_keyboard(to.match)
        assert _btn_styles(s06_kb) == [
            (f"🏆 {to_bold_sans('Claim Victory')}", "success"),
            (f"⏳ {to_bold_sans('Wait 1m')}", "primary"),
        ]

        # Screen 07 — Extra Time Granted (Variation C: skipped)
        opp = "202" if active == "101" else "101"
        ex = await mgr.grant_turn_extension(
            match_id=to.match.match_id,
            granting_player_id=opp,
            expected_generation=to.match.generation,
        )
        assert ex.accepted and ex.match is not None
        s07c = render_awaiting_shuffle_card(ex.match, player_names=names, seconds_remaining=60.0)
        assert "granted an extra minute." in s07c
        assert "This is your final extension." in s07c

        # Second timeout -> Wait 1m hidden
        clock.advance(70.0)
        to2 = await mgr.handle_turn_timeout(
            match_id=ex.match.match_id,
            expected_revision=ex.match.draft_snapshot.revision,
            expected_turn_number=ex.match.turn_number_at_start,
        )
        assert to2.accepted and to2.match is not None
        s06_no_ext = render_turn_expired_card(to2.match, player_names=names)
        assert "No further extensions are available." in s06_no_ext
        assert _btn_styles(build_inactivity_keyboard(to2.match)) == [
            (f"🏆 {to_bold_sans('Claim Victory')}", "success")
        ]

        # Screen 09 — Match Abandoned
        clock.advance(65.0)
        ab = await mgr.handle_claim_window_timeout(
            match_id=to2.match.match_id, expected_generation=to2.match.generation
        )
        assert ab.accepted and ab.match is not None
        s09 = render_match_results(ab.match, universe_name="Naruto", player_names=names, char_lookup=char_lookup)
        assert STATUS_TIMEOUT in s09
        assert STATUS_NO_RESPONSE in s09
        assert "Match abandoned" in s09
        assert build_match_results_keyboard(ab.match, player_names=names) is None

        # Screen 13, 15, 16
        s13 = render_forfeit_confirmation(
            requester_id="101", requester_name="Obito", opponent_id="202", opponent_name="Kiyomi"
        )
        assert "𝐂𝐎𝐍𝐅𝐈𝐑𝐌 𝐒𝐔𝐑𝐑𝐄𝐍𝐃𝐄𝐑" in s13
        assert _btn_styles(build_forfeit_confirm_keyboard(match, requester_id="101")) == [
            (to_bold_sans("FORFEIT"), "danger"),
            (f"✕ {to_bold_sans('Cancel')}", None),
        ]

        s15 = render_active_game(
            match,
            requester_id="101",
            universe_name="Naruto",
            player_names=names,
            group_title="Chulbuli Duniya",
        )
        assert "𝐀𝐂𝐓𝐈𝐕𝐄 𝐌𝐀𝐓𝐂𝐇" in s15
        assert "Chulbuli Duniya" in s15
        assert _btn_styles(
            build_active_game_keyboard(match, game_link="https://t.me/c/1234567890/55")
        ) == [
            (f"↗ {to_bold_sans('Go to Match')}", "primary"),
            (f"🔄 {to_bold_sans('Recover')}", None),
            (f"⚑ {to_bold_sans('Forfeit')}", "danger"),
        ]
        # No invented link when game_link is None
        assert len(build_active_game_keyboard(match, game_link=None).inline_keyboard) == 1
        assert "𝐑𝐄𝐂𝐎𝐕𝐄𝐑 𝐌𝐀𝐓𝐂𝐇" in render_recover_confirmation()
        assert _btn_styles(build_recover_confirm_keyboard(match)) == [
            (to_bold_sans("Recover"), "primary"),
            (f"« {to_bold_sans('Back')}", None),
        ]
        assert "𝐌𝐀𝐓𝐂𝐇 𝐑𝐄𝐂𝐎𝐕𝐄𝐑𝐄𝐃" in render_recover_success(group_title="Chulbuli Duniya")
        assert "𝐑𝐄𝐂𝐎𝐕𝐄𝐑𝐘 𝐈𝐍𝐂𝐎𝐌𝐏𝐋𝐄𝐓𝐄" in render_recover_failed()
        assert build_recover_success_keyboard(game_link=None) is None
        assert "𝐍𝐎 𝐀𝐂𝐓𝐈𝐕𝐄 𝐌𝐀𝐓𝐂𝐇" in render_no_active_game()
        assert build_no_active_game_keyboard() is None

    asyncio.run(_run())
    db.close()


# ---------------------------------------------------------------------------
# Section 47 — Artwork Lifecycle & Restart DisplayState Persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_artwork_lifecycle_retention_and_restart_persistence(tmp_path: Any) -> None:
    db = CharacterDatabase(":memory:")
    _seed_naruto_db(db)
    store = SqliteMatchStore(tmp_path / "state.sqlite3")
    clock = FakeClock()
    mgr = MatchManager(db, dataset_kind=DatasetKind.PRODUCTION, clock=clock, store=store)
    bot = MockBotRecorder()
    dp, coord = create_dispatcher(
        bot=bot, config=BotConfig(bot_token="fake:t"), db=db, manager=mgr, store=store
    )
    u1 = _make_user(101, "Obito")
    u2 = _make_user(202, "Kiyomi")
    coord.register_user(u1)
    coord.register_user(u2)

    chl = (
        await mgr.create_challenge(challenger_id="101", chat_id="-1001234567890", universe_id="naruto")
    ).challenge
    match = (await mgr.accept_challenge(challenge_id=chl.challenge_id, player_id="202")).match
    assert match is not None

    # Pre-seed media cache so character artwork resolves cleanly to file_id
    for c in db.list_characters(universe_id="naruto"):
        store.upsert_media_asset(
            media_key=f"k:{c.character_id}",
            character_id=c.character_id,
            universe_id="naruto",
            source_url=c.image.url_or_ref,
            telegram_file_id=f"tg_fid_{c.character_id}",
            upload_status="uploaded",
        )

    ui = await coord.start_match_ui(match, chat_id="-1001234567890")
    assert ui is not None
    # Initial Shuffle is text-only
    assert ui.card_is_photo is False

    # First Shuffle upgrades Action Card to photo
    active = match.draft_snapshot.active_player_id or "101"
    active_user = u1 if active == "101" else u2
    await dp.feed_update(
        bot,
        _make_callback_update(
            1,
            chat_id=-1001234567890,
            chat_type="supergroup",
            message_id=ui.card_message_id,
            user=active_user,
            data=encode_cb("sh", match.match_id, match.generation),
            recorder=bot,
        ),
    )
    m1 = mgr.get_match(match.match_id)
    assert m1 is not None and m1.display_state.last_action == "obtained"
    assert m1.display_state.card_is_photo is True
    assert ui.card_is_photo is True

    # Assign role -> Screen 04 retains artwork!
    await dp.feed_update(
        bot,
        _make_callback_update(
            2,
            chat_id=-1001234567890,
            chat_type="supergroup",
            message_id=ui.card_message_id,
            user=active_user,
            data=encode_cb("as", m1.match_id, m1.generation, 0),
            recorder=bot,
        ),
    )
    m2 = mgr.get_match(match.match_id)
    assert m2 is not None
    assert m2.display_state.last_action == "assigned"
    assert m2.display_state.assigned_role == "Captain"
    assert m2.display_state.last_character_id == m1.display_state.last_character_id
    assert m2.display_state.card_is_photo is True
    # Assigned character cannot be assigned again
    re_assign = await mgr.assign_match_role(
        match_id=m2.match_id,
        player_id=m2.draft_snapshot.active_player_id or "202",
        role="Strategist",
        expected_revision=m2.draft_snapshot.revision,
        expected_generation=m2.generation,
    )
    assert not re_assign.accepted

    # Restart preserves display_state from SQLite
    loaded = store.load_match(match.match_id)
    assert loaded is not None
    assert loaded.display_state == m2.display_state

    await coord.shutdown()
    store.close()
    db.close()


# ---------------------------------------------------------------------------
# Section 49 & 50 — Full-Match Recovery, Stale Callbacks, Partial Recovery, Forfeit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_recovery_stale_callbacks_cross_chat_and_partial_failure() -> None:
    db = CharacterDatabase(":memory:")
    _seed_naruto_db(db)
    clock = FakeClock()
    mgr = MatchManager(db, dataset_kind=DatasetKind.PRODUCTION, clock=clock)
    bot = MockBotRecorder()
    dp, coord = create_dispatcher(bot=bot, config=BotConfig(bot_token="fake:t"), db=db, manager=mgr)
    u1 = _make_user(101, "Obito")
    u2 = _make_user(202, "Kiyomi")
    outsider = _make_user(303, "Outsider")
    coord.register_user(u1)
    coord.register_user(u2)
    coord.register_user(outsider)

    chl = (
        await mgr.create_challenge(challenger_id="101", chat_id="-1001234567890", universe_id="naruto")
    ).challenge
    match = (await mgr.accept_challenge(challenge_id=chl.challenge_id, player_id="202")).match
    assert match is not None
    old_ui = await coord.start_match_ui(match, chat_id="-1001234567890")
    assert old_ui is not None
    old_gen = match.generation

    # Cross-chat callback replay is rejected
    await dp.feed_update(
        bot,
        _make_callback_update(
            1,
            chat_id=-1009999999999,
            chat_type="supergroup",
            message_id=old_ui.card_message_id,
            user=u1,
            data=encode_cb("sh", match.match_id, old_gen),
            recorder=bot,
        ),
    )
    assert "outdated" in bot.callback_answers[-1]["text"].lower()

    # /game -> Recover confirmation -> Back -> Recover confirm
    await dp.feed_update(
        bot, _make_message_update(2, chat_id=101, chat_type="private", user=u1, text="/game")
    )
    game_msg_id = 100 + len(bot.sent_messages)
    await dp.feed_update(
        bot,
        _make_callback_update(
            3, chat_id=101, chat_type="private", message_id=game_msg_id, user=u1, data=encode_cb("gr", match.match_id), recorder=bot
        ),
    )
    assert "𝐑𝐄𝐂𝐎𝐕𝐄𝐑 𝐌𝐀𝐓𝐂𝐇" in bot.edited_messages[-1]["text"]

    await dp.feed_update(
        bot,
        _make_callback_update(
            4, chat_id=101, chat_type="private", message_id=game_msg_id, user=u1, data=encode_cb("grb", match.match_id), recorder=bot
        ),
    )
    assert "𝐀𝐂𝐓𝐈𝐕𝐄 𝐌𝐀𝐓𝐂𝐇" in bot.edited_messages[-1]["text"]

    # Confirm recovery
    await dp.feed_update(
        bot,
        _make_callback_update(
            5,
            chat_id=101,
            chat_type="private",
            message_id=game_msg_id,
            user=u1,
            data=encode_cb("grc", match.match_id, old_gen),
            recorder=bot,
        ),
    )
    assert "𝐌𝐀𝐓𝐂𝐇 𝐑𝐄𝐂𝐎𝐕𝐄𝐑𝐄𝐃" in bot.edited_messages[-1]["text"]
    new_ui = coord._match_ui[match.match_id]
    assert new_ui.board_message_id != old_ui.board_message_id
    assert new_ui.card_message_id != old_ui.card_message_id

    # Old Shuffle, old Forfeit, and old Recovery callbacks are ALL rejected
    await dp.feed_update(
        bot,
        _make_callback_update(
            6, chat_id=-1001234567890, chat_type="supergroup", message_id=old_ui.card_message_id, user=u1, data=encode_cb("sh", match.match_id, old_gen), recorder=bot
        ),
    )
    assert "outdated" in bot.callback_answers[-1]["text"].lower()

    await dp.feed_update(
        bot,
        _make_callback_update(
            7, chat_id=-1001234567890, chat_type="supergroup", message_id=old_ui.board_message_id, user=u1, data=encode_cb("gf", match.match_id, old_gen), recorder=bot
        ),
    )
    assert "outdated" in bot.callback_answers[-1]["text"].lower()

    await dp.feed_update(
        bot,
        _make_callback_update(
            8, chat_id=101, chat_type="private", message_id=game_msg_id, user=u1, data=encode_cb("grc", match.match_id, old_gen), recorder=bot
        ),
    )
    assert "outdated" in bot.callback_answers[-1]["text"].lower()

    # Duplicate forfeit confirmation prevented & non-requester cannot confirm
    latest_m = mgr.get_match(match.match_id)
    assert latest_m is not None
    await dp.feed_update(
        bot,
        _make_callback_update(
            9, chat_id=-1001234567890, chat_type="supergroup", message_id=new_ui.board_message_id, user=u1, data=encode_cb("gf", match.match_id, latest_m.generation), recorder=bot
        ),
    )
    fc_msg_id = 100 + len(bot.sent_messages)
    await dp.feed_update(
        bot,
        _make_callback_update(
            10, chat_id=-1001234567890, chat_type="supergroup", message_id=new_ui.board_message_id, user=u1, data=encode_cb("gf", match.match_id, latest_m.generation), recorder=bot
        ),
    )
    assert "already have an open forfeit confirmation" in bot.callback_answers[-1]["text"].lower()

    # Opponent cannot confirm u1's surrender
    await dp.feed_update(
        bot,
        _make_callback_update(
            11, chat_id=-1001234567890, chat_type="supergroup", message_id=fc_msg_id, user=u2, data=encode_cb("gfc", match.match_id, latest_m.generation, "101"), recorder=bot
        ),
    )
    assert "only the player who requested" in bot.callback_answers[-1]["text"].lower()

    await coord.shutdown()
    db.close()


# ---------------------------------------------------------------------------
# Section 51 — Dedicated Gameplay Logging Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gameplay_logger_formats_dedups_and_isolates_failures() -> None:
    db = CharacterDatabase(":memory:")
    _seed_naruto_db(db)
    mgr = MatchManager(db, dataset_kind=DatasetKind.PRODUCTION)
    bot = MockBotRecorder()

    # Disabled logger (channel_id=0) is a safe no-op
    disabled = GameplayLogger(bot, channel_id=0)
    assert disabled.enabled is False

    chl = (await mgr.create_challenge(challenger_id="101", chat_id="-1001234567890", universe_id="naruto")).challenge
    match = (await mgr.accept_challenge(challenge_id=chl.challenge_id, player_id="202")).match
    assert match is not None

    logger_inst = GameplayLogger(bot, channel_id=-100999888777)
    names = {"101": "Obito", "202": "Kiyomi"}
    ok1 = await logger_inst.log_match_started(
        match,
        universe_name="Naruto",
        player_names=names,
        chat_id="-1001234567890",
        group_title="Chulbuli Duniya",
    )
    assert ok1 is True
    assert "#MATCH_STARTED" in bot.sent_messages[-1]["text"]
    assert "<code>101</code>" in bot.sent_messages[-1]["text"]

    # Duplicate #MATCH_STARTED for same match is suppressed
    ok_dup = await logger_inst.log_match_started(
        match,
        universe_name="Naruto",
        player_names=names,
        chat_id="-1001234567890",
        group_title="Chulbuli Duniya",
    )
    assert ok_dup is False

    # Failure isolation (TelegramForbiddenError never raises)
    async def _raise_forbidden(**_kwargs: Any) -> Any:
        raise TelegramForbiddenError(method=SimpleNamespace(), message="Forbidden")

    bot.send_message = _raise_forbidden  # type: ignore[method-assign]
    ok_fail = await logger_inst.log_error(match_id=match.match_id, context="test", error_name="TestErr")
    assert ok_fail is False

    db.close()


@pytest.mark.asyncio
async def test_ui_2_1_board_spacing_bullets_and_fresh_conclusion_message() -> None:
    db = CharacterDatabase(":memory:")
    _seed_naruto_db(db)
    clock = FakeClock()
    mgr = MatchManager(db, dataset_kind=DatasetKind.PRODUCTION, clock=clock)
    bot = MockBotRecorder()
    dp, coord = create_dispatcher(bot=bot, config=BotConfig(bot_token="fake:t"), db=db, manager=mgr)
    u1 = _make_user(101, "Obito")
    u2 = _make_user(202, "Kiyomi")
    coord.register_user(u1)
    coord.register_user(u2)

    chl = (
        await mgr.create_challenge(challenger_id="101", chat_id="-1001234567890", universe_id="naruto")
    ).challenge
    match = (await mgr.accept_challenge(challenge_id=chl.challenge_id, player_id="202")).match
    assert match is not None
    ui = await coord.start_match_ui(match, chat_id="-1001234567890")
    assert ui is not None
    old_board_id = ui.board_message_id
    old_card_id = ui.card_message_id

    # Draft 2 roles for player 1 and 2 roles for player 2 to check Draft Board spacing & bullets
    for turn in range(4):
        cur = mgr.get_match(match.match_id)
        assert cur is not None
        active = cur.draft_snapshot.active_player_id or "101"
        sh = await mgr.shuffle_match(
            match_id=cur.match_id,
            player_id=active,
            expected_revision=cur.draft_snapshot.revision,
            expected_generation=cur.generation,
        )
        assert sh.accepted and sh.match is not None
        role_idx = turn // 2
        asg = await mgr.assign_match_role(
            match_id=sh.match.match_id,
            player_id=active,
            role=ROLE_ORDER[role_idx],
            expected_revision=sh.match.draft_snapshot.revision,
            expected_generation=sh.match.generation,
        )
        assert asg.accepted and asg.match is not None

    mid = mgr.get_match(match.match_id)
    assert mid is not None
    board_text = render_draft_board(
        mid,
        universe_name="Naruto",
        player_names=coord.player_names_for_match(mid),
        char_lookup=coord.char_lookup_for_match(mid),
    )
    # 1. Exactly one empty line between assigned roles for both players
    lines = board_text.splitlines()
    role_indices = [i for i, ln in enumerate(lines) if ln.startswith("✦ ") and "<b>Captain</b>" in ln or ln.startswith("✦ ") and "<b>Strategist</b>" in ln]
    assert len(role_indices) == 4
    assert lines[role_indices[0] + 1] == "" and role_indices[1] == role_indices[0] + 2
    assert lines[role_indices[2] + 1] == "" and role_indices[3] == role_indices[2] + 2

    # 2. Lighter ▸ bullets on Available and Skips left for both players (not ▪)
    assert board_text.count("▸ <b>Available:</b>") == 2
    assert board_text.count("▸ <b>Skips left:</b>") == 2
    assert "▪ <b>Available:</b>" not in board_text
    assert "▪ <b>Skips left:</b>" not in board_text

    # 3. Complete the draft -> fresh result message sent, old board & card deleted, duplicate sync suppressed
    while True:
        cur = mgr.get_match(match.match_id)
        assert cur is not None
        if cur.status is not MatchLifecycleStatus.DRAFTING:
            break
        active = cur.draft_snapshot.active_player_id or "101"
        sh = await mgr.shuffle_match(
            match_id=cur.match_id,
            player_id=active,
            expected_revision=cur.draft_snapshot.revision,
            expected_generation=cur.generation,
        )
        assert sh.accepted and sh.match is not None
        open_roles = [r for r in ROLE_ORDER if sh.match.public_view.teams[active].get(r) is None]
        asg = await mgr.assign_match_role(
            match_id=sh.match.match_id,
            player_id=active,
            role=open_roles[0],
            expected_revision=sh.match.draft_snapshot.revision,
            expected_generation=sh.match.generation,
        )
        assert asg.accepted and asg.match is not None

    done_match = mgr.get_match(match.match_id)
    assert done_match is not None and done_match.status is MatchLifecycleStatus.COMPLETED
    sent_before = len(bot.sent_messages)
    await coord.sync_match_ui(done_match, update_board=True, update_card=True)
    assert len(bot.sent_messages) == sent_before + 1
    fresh_result_id = bot.next_msg_id
    assert fresh_result_id != old_board_id
    assert "𝐀𝐑𝐄𝐍𝐀 𝐑𝐄𝐒𝐔𝐋𝐓" in bot.sent_messages[-1]["text"]
    deleted_ids = {d["message_id"] for d in bot.deleted_messages}
    assert old_board_id in deleted_ids
    assert old_card_id in deleted_ids

    # Duplicate terminal sync does NOT send a second result message
    await coord.sync_match_ui(done_match, update_board=True, update_card=True)
    assert len(bot.sent_messages) == sent_before + 1

    # Battle Breakdown & Back to Result edit the newly sent result message
    await dp.feed_update(
        bot,
        _make_callback_update(
            50,
            chat_id=-1001234567890,
            chat_type="supergroup",
            message_id=fresh_result_id,
            user=u1,
            data=encode_cb("dr", done_match.match_id, 0),
            recorder=bot,
        ),
    )
    assert bot.edited_messages[-1]["message_id"] == fresh_result_id
    assert "𝐁𝐀𝐓𝐓𝐋𝐄 𝐁𝐑𝐄𝐀𝐊𝐃𝐎𝐖𝐍" in bot.edited_messages[-1]["text"]

    await dp.feed_update(
        bot,
        _make_callback_update(
            51,
            chat_id=-1001234567890,
            chat_type="supergroup",
            message_id=fresh_result_id,
            user=u1,
            data=encode_cb("mr", done_match.match_id),
            recorder=bot,
        ),
    )
    assert bot.edited_messages[-1]["message_id"] == fresh_result_id
    assert "𝐀𝐑𝐄𝐍𝐀 𝐑𝐄𝐒𝐔𝐋𝐓" in bot.edited_messages[-1]["text"]

    await coord.shutdown()
    db.close()
