"""Comprehensive tests for Player Profile 2.0 (Part IX — Sections 34-39)."""

from __future__ import annotations

import asyncio
import time
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from app.database import CharacterDatabase
from app.matches import MatchLifecycleStatus, MatchManager
from app.persistence import SqliteMatchStore
from app.persistence.models import summarize_player_records
from app.scoring import DatasetKind, SCORING_ROLES
from app.telegram import BotConfig, create_dispatcher, encode_cb
from app.telegram.constants import ROLE_ORDER, STATUS_DEFEAT, STATUS_DRAW, STATUS_VICTORY, to_bold_sans
from app.telegram.profile_card import (
    PlayerCardCache,
    render_player_card_async,
    render_player_card_png,
)
from tests.test_telegram_ui import (
    FakeClock,
    MockBotRecorder,
    _make_callback_update,
    _make_message_update,
    _make_user,
    _seed_naruto_db,
)


def _make_sample_avatar_bytes() -> bytes:
    im = Image.new("RGBA", (320, 320), (30, 120, 220, 255))
    buf = BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Section 34 — Card Renderer Tests
# ---------------------------------------------------------------------------


def test_player_card_renderer_sizes_unicode_zero_large_and_corrupt_avatar() -> None:
    avatar = _make_sample_avatar_bytes()
    cases = [
        ("Obito", 32, 14, 2, avatar),
        ("NewPlayer", 0, 0, 0, None),
        ("Ace", 10, 0, 0, avatar),  # 100.0% win rate
        ("Very Long Esports Player Name That Must Auto Scale Cleanly", 1234, 567, 89, avatar),
        ("𝐎𝐛𝐢𝐭𝐨 忍🔥", 120000, 45000, 3000, b"not-valid-image-bytes"),
    ]
    for name, w, l, d, av in cases:
        png = render_player_card_png(name=name, wins=w, losses=l, draws=d, avatar_bytes=av)
        im = Image.open(BytesIO(png))
        assert im.size == (1900, 600)
        assert im.format == "PNG"


@pytest.mark.asyncio
async def test_player_card_cache_isolation_and_invalidation() -> None:
    cache = PlayerCardCache(max_entries=4)
    av1 = _make_sample_avatar_bytes()
    k1, c1 = await render_player_card_async(
        cache=cache, player_id="101", name="Obito", wins=5, losses=2, draws=0, avatar_bytes=av1
    )
    cache.set_file_id(k1, "tg_card_101")
    k1_again, c1_again = await render_player_card_async(
        cache=cache, player_id="101", name="Obito", wins=5, losses=2, draws=0, avatar_bytes=av1
    )
    assert k1_again == k1
    assert c1_again.telegram_file_id == "tg_card_101"

    # Unrelated player does NOT invalidate 101's cache
    k2, c2 = await render_player_card_async(
        cache=cache, player_id="202", name="Kiyomi", wins=1, losses=0, draws=0, avatar_bytes=None
    )
    assert k2 != k1 and c2.telegram_file_id is None
    assert cache.get(k1) is not None and cache.get(k1).telegram_file_id == "tg_card_101"

    # Changing 101's Ranked stats invalidates 101's key cleanly
    k1_updated, c1_updated = await render_player_card_async(
        cache=cache, player_id="101", name="Obito", wins=6, losses=2, draws=0, avatar_bytes=av1
    )
    assert k1_updated != k1 and c1_updated.telegram_file_id is None


# ---------------------------------------------------------------------------
# Section 35, 36, 37, 38 — Stats, History, Navigation, Security & Immutability
# ---------------------------------------------------------------------------


async def _play_completed_match(
    mgr: MatchManager,
    *,
    p1: str,
    p2: str,
    universe_id: str = "naruto",
    game_mode: str = "ranked",
    clock: FakeClock,
) -> Any:
    chl = (
        await mgr.create_challenge(
            challenger_id=p1, chat_id="-1001800918110", universe_id=universe_id, game_mode=game_mode
        )
    ).challenge
    assert chl is not None
    m = (await mgr.accept_challenge(challenge_id=chl.challenge_id, player_id=p2)).match
    assert m is not None
    while m.status is MatchLifecycleStatus.DRAFTING:
        active = m.draft_snapshot.active_player_id or p1
        sh = await mgr.shuffle_match(
            match_id=m.match_id,
            player_id=active,
            expected_revision=m.draft_snapshot.revision,
            expected_generation=m.generation,
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
        m = asg.match
        clock.advance(5.0)
    return m


@pytest.mark.asyncio
async def test_profile_2_0_stats_history_navigation_security_and_immutability(tmp_path: Path) -> None:
    db = CharacterDatabase(":memory:")
    _seed_naruto_db(db)
    store = SqliteMatchStore(tmp_path / "state.sqlite3")
    clock = FakeClock()
    mgr = MatchManager(db, dataset_kind=DatasetKind.PRODUCTION, clock=clock, store=store)
    bot = MockBotRecorder()
    dp, coord = create_dispatcher(bot=bot, config=BotConfig(bot_token="fake:t"), db=db, manager=mgr, store=store)

    u1 = _make_user(101, "Obito")
    u2 = _make_user(202, "Kiyomi")
    outsider = _make_user(303, "Watcher")
    coord.register_user(u1)
    coord.register_user(u2)
    coord.register_user(outsider)

    # Play 2 Ranked completed matches, 1 Friendly completed match, 1 Ranked forfeit, 1 Ranked abandoned
    m1 = await _play_completed_match(mgr, p1="101", p2="202", game_mode="ranked", clock=clock)
    clock.advance(10.0)
    m2 = await _play_completed_match(mgr, p1="202", p2="101", game_mode="ranked", clock=clock)
    clock.advance(10.0)
    await _play_completed_match(mgr, p1="101", p2="202", game_mode="friendly", clock=clock)
    clock.advance(10.0)

    # Ranked forfeit by 202 -> 101 wins
    chl_f = (await mgr.create_challenge(challenger_id="101", chat_id="-1001800918110", universe_id="naruto", game_mode="ranked")).challenge
    mf = (await mgr.accept_challenge(challenge_id=chl_f.challenge_id, player_id="202")).match
    await mgr.forfeit_match(match_id=mf.match_id, player_id="202", expected_generation=mf.generation)
    clock.advance(10.0)

    # Ranked abandoned -> must NOT be counted in stats or history
    chl_a = (await mgr.create_challenge(challenger_id="101", chat_id="-1001800918110", universe_id="naruto", game_mode="ranked")).challenge
    ma = (await mgr.accept_challenge(challenge_id=chl_a.challenge_id, player_id="202")).match
    clock.advance(125.0)
    to = (await mgr.handle_turn_timeout(match_id=ma.match_id, expected_revision=ma.draft_snapshot.revision, expected_turn_number=ma.turn_number_at_start)).match
    clock.advance(65.0)
    await mgr.handle_claim_window_timeout(match_id=to.match_id, expected_generation=to.generation)

    # Verify stats consistency
    ranked_stats = store.compute_player_statistics("101", game_mode="ranked")
    assert ranked_stats.battles_played == 3  # m1, m2, forfeit (abandoned excluded!)
    assert ranked_stats.victories + ranked_stats.defeats + ranked_stats.draws == 3
    assert ranked_stats.highest_team_score is not None and ranked_stats.highest_team_score <= 700
    friendly_stats = store.compute_player_statistics("101", game_mode="friendly")
    assert friendly_stats.battles_played == 1

    # 1. /profile sends 1900x600 photo card with NO caption stats
    await dp.feed_update(bot, _make_message_update(1, chat_id=-1001800918110, chat_type="supergroup", user=u1, text="/profile"))
    assert len(bot.sent_photos) == 1
    assert bot.sent_photos[-1]["caption"] == ""
    card_msg_id = bot.next_msg_id
    session = next(iter(coord._profile_sessions.values()))
    assert session.owner_id == "101" and session.requester_id == "101"

    # Unauthorized user cannot navigate u1's profile session
    await dp.feed_update(
        bot,
        _make_callback_update(
            2,
            chat_id=-1001800918110,
            chat_type="supergroup",
            message_id=card_msg_id,
            user=outsider,
            data=encode_cb("pf", session.session_id, session.revision, "st"),
            recorder=bot,
        ),
    )
    assert "only the player who opened" in bot.callback_answers[-1]["text"].lower()

    # Cross-chat replay rejected
    await dp.feed_update(
        bot,
        _make_callback_update(
            3,
            chat_id=101,
            chat_type="private",
            message_id=card_msg_id,
            user=u1,
            data=encode_cb("pf", session.session_id, session.revision, "st"),
            recorder=bot,
        ),
    )
    assert "outdated" in bot.callback_answers[-1]["text"].lower()

    # 2. Card -> Statistics (photo -> text replacement)
    await dp.feed_update(
        bot,
        _make_callback_update(
            4,
            chat_id=-1001800918110,
            chat_type="supergroup",
            message_id=card_msg_id,
            user=u1,
            data=encode_cb("pf", session.session_id, session.revision, "st"),
            recorder=bot,
        ),
    )
    assert "𝐏𝐋𝐀𝐘𝐄𝐑 𝐒𝐓𝐀𝐓𝐈𝐒𝐓𝐈𝐂𝐒" in bot.sent_messages[-1]["text"]
    assert f"▸ <b>Battles played:</b> {ranked_stats.battles_played}" in bot.sent_messages[-1]["text"]
    stats_msg_id = session.message_id
    assert stats_msg_id != card_msg_id

    # Stale card callback rejected after transition
    await dp.feed_update(
        bot,
        _make_callback_update(
            5,
            chat_id=-1001800918110,
            chat_type="supergroup",
            message_id=card_msg_id,
            user=u1,
            data=encode_cb("pf", session.session_id, 1, "hs"),
            recorder=bot,
        ),
    )
    assert "outdated" in bot.callback_answers[-1]["text"].lower()

    # 3. Statistics -> Universe Selection -> select Naruto -> back to Statistics
    await dp.feed_update(
        bot,
        _make_callback_update(
            6,
            chat_id=-1001800918110,
            chat_type="supergroup",
            message_id=stats_msg_id,
            user=u1,
            data=encode_cb("pf", session.session_id, session.revision, "uv"),
            recorder=bot,
        ),
    )
    assert "𝐒𝐄𝐋𝐄𝐂𝐓 𝐔𝐍𝐈𝐕𝐄𝐑𝐒𝐄" in bot.edited_messages[-1]["text"]
    await dp.feed_update(
        bot,
        _make_callback_update(
            7,
            chat_id=-1001800918110,
            chat_type="supergroup",
            message_id=stats_msg_id,
            user=u1,
            data=encode_cb("pf", session.session_id, session.revision, "us", "naruto"),
            recorder=bot,
        ),
    )
    assert "◆ <b>Universe:</b> Naruto" in bot.edited_messages[-1]["text"]

    # 4. Back to Card (text -> photo), then History -> Details -> Breakdown -> Back -> Back -> Close
    await dp.feed_update(
        bot,
        _make_callback_update(
            8,
            chat_id=-1001800918110,
            chat_type="supergroup",
            message_id=stats_msg_id,
            user=u1,
            data=encode_cb("pf", session.session_id, session.revision, "bk"),
            recorder=bot,
        ),
    )
    assert session.screen == "card" and session.is_photo is True
    card_msg_id_2 = session.message_id

    await dp.feed_update(
        bot,
        _make_callback_update(
            9,
            chat_id=-1001800918110,
            chat_type="supergroup",
            message_id=card_msg_id_2,
            user=u1,
            data=encode_cb("pf", session.session_id, session.revision, "hs"),
            recorder=bot,
        ),
    )
    hist_txt = bot.sent_messages[-1]["text"]
    assert "𝐌𝐀𝐓𝐂𝐇 𝐇𝐈𝐒𝐓𝐎𝐑𝐘" in hist_txt
    assert "ꜰᴏʀꜰᴇɪᴛ" in hist_txt
    hist_msg_id = session.message_id

    # Open record 1 (forfeit) -> verify NO Battle Breakdown button; then open record 2 (m2) -> Breakdown
    await dp.feed_update(
        bot,
        _make_callback_update(
            10,
            chat_id=-1001800918110,
            chat_type="supergroup",
            message_id=hist_msg_id,
            user=u1,
            data=encode_cb("pf", session.session_id, session.revision, "hm", 0),
            recorder=bot,
        ),
    )
    assert "𝐁𝐀𝐓𝐓𝐋𝐄 𝐑𝐄𝐂𝐎𝐑𝐃" in bot.edited_messages[-1]["text"]
    assert "Forfeit" in bot.edited_messages[-1]["text"]

    await dp.feed_update(
        bot,
        _make_callback_update(
            11,
            chat_id=-1001800918110,
            chat_type="supergroup",
            message_id=hist_msg_id,
            user=u1,
            data=encode_cb("pf", session.session_id, session.revision, "bk"),
            recorder=bot,
        ),
    )
    assert "𝐌𝐀𝐓𝐂𝐇 𝐇𝐈𝐒𝐓𝐎𝐑𝐘" in bot.edited_messages[-1]["text"]

    await dp.feed_update(
        bot,
        _make_callback_update(
            12,
            chat_id=-1001800918110,
            chat_type="supergroup",
            message_id=hist_msg_id,
            user=u1,
            data=encode_cb("pf", session.session_id, session.revision, "hm", 1),
            recorder=bot,
        ),
    )
    detail_before_pub = bot.edited_messages[-1]["text"]
    assert "𝐁𝐀𝐓𝐓𝐋𝐄 𝐑𝐄𝐂𝐎𝐑𝐃" in detail_before_pub

    await dp.feed_update(
        bot,
        _make_callback_update(
            13,
            chat_id=-1001800918110,
            chat_type="supergroup",
            message_id=hist_msg_id,
            user=u1,
            data=encode_cb("pf", session.session_id, session.revision, "bd"),
            recorder=bot,
        ),
    )
    assert "𝐁𝐀𝐓𝐓𝐋𝐄 𝐁𝐑𝐄𝐀𝐊𝐃𝐎𝐖𝐍" in bot.edited_messages[-1]["text"]
    assert "Power / Role Fit / Score" in bot.edited_messages[-1]["text"]

    # Mutate character ratings & publish new dataset -> historical details MUST stay immutable!
    c0 = db.list_characters(universe_id="naruto")[0]
    db.reopen_to_draft(c0.character_id)
    db.update_character_evaluation(
        c0.character_id, power=1, fit={r: 1 for r in SCORING_ROLES}
    )
    db.submit_for_review(c0.character_id)
    db.approve_character(c0.character_id)
    db.publish_dataset("naruto", "naruto-v2", kind=DatasetKind.PRODUCTION)

    await dp.feed_update(
        bot,
        _make_callback_update(
            14,
            chat_id=-1001800918110,
            chat_type="supergroup",
            message_id=hist_msg_id,
            user=u1,
            data=encode_cb("pf", session.session_id, session.revision, "bk"),
            recorder=bot,
        ),
    )
    assert bot.edited_messages[-1]["text"] == detail_before_pub

    # Close dismisses the interface and invalidates session
    await dp.feed_update(
        bot,
        _make_callback_update(
            15,
            chat_id=-1001800918110,
            chat_type="supergroup",
            message_id=hist_msg_id,
            user=u1,
            data=encode_cb("pf", session.session_id, session.revision, "cl"),
            recorder=bot,
        ),
    )
    assert session.closed is True

    await coord.shutdown()
    store.close()
    db.close()
