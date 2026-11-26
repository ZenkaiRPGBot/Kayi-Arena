"""Comprehensive automated tests for Module 6 (Telegram UI & UX)."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.types import CallbackQuery, Chat, Message, Update, User

from app.database import (
    CharacterDatabase,
    ImageMetadata,
    ImageValidationStatus,
    SpeciesKind,
)
from app.engine import ROLES
from app.matches import (
    ChallengeStatus,
    MatchLifecycleStatus,
    MatchManager,
    MatchManagementErrorCode,
    MatchOutcomeReason,
)
from app.scoring import DatasetKind, SCORING_ROLES
from app.telegram import (
    BotConfig,
    PUBLIC_BOT_COMMANDS,
    RestartNotifier,
    create_dispatcher,
    decode_cb,
    encode_cb,
)
from app.telegram.constants import MAX_CALLBACK_DATA_BYTES, MAX_CAPTION_LENGTH, MAX_MESSAGE_LENGTH
from app.telegram.keyboards import (
    build_awaiting_shuffle_keyboard,
    build_challenge_keyboard,
    build_character_revealed_keyboard,
    build_home_keyboard,
    build_inactivity_keyboard,
    build_universe_selection_keyboard,
)
from app.telegram.safe_api import edit_message_text_safe, send_photo_or_text_safe
from app.telegram.texts import (
    render_catalogue_page,
    render_detailed_result_page,
    render_draft_board,
    render_match_results,
    render_revealed_character_card,
)


def _seed_naruto_db(db: CharacterDatabase, *, count: int = 18) -> None:
    db.create_universe(universe_id="naruto", name="Naruto", active=True)
    rarities = ["Common", "Uncommon", "Rare", "Epic", "Legendary"]
    for i in range(count):
        cid = f"naruto_c{i:02d}"
        # Unique power/fit combinations so scores are realistic
        fits = {r: (i % 5) + 1 if idx == (i % 7) else ((i + idx) % 4) + 1 for idx, r in enumerate(SCORING_ROLES)}
        db.add_character(
            character_id=cid,
            universe_id="naruto",
            name=f"Ninja {i:02d}",
            species=SpeciesKind.HUMAN,
            rarity=rarities[i % len(rarities)],
            power=(i % 5) + 1,
            fit=fits,
            canonical_version="Shippuden",
            image=ImageMetadata(
                url_or_ref=f"https://example.com/{cid}.jpg",
                status=ImageValidationStatus.VERIFIED,
            ),
        )
        db.submit_for_review(cid)
        db.approve_character(cid)
    db.publish_dataset(
        universe_id="naruto",
        dataset_version="naruto-prod-v1",
        kind=DatasetKind.PRODUCTION,
    )


class FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class MockBotRecorder:
    """Mock aiogram Bot capturing sent/edited messages and callback answers."""

    def __init__(self) -> None:
        self.id = 999999
        self.next_msg_id = 100
        self.sent_messages: list[dict[str, Any]] = []
        self.edited_messages: list[dict[str, Any]] = []
        self.sent_photos: list[dict[str, Any]] = []
        self.edited_media: list[dict[str, Any]] = []
        self.edited_captions: list[dict[str, Any]] = []
        self.callback_answers: list[dict[str, Any]] = []
        self.fail_photos: bool = False

    def _make_message(self, chat_id: int | str, text: str = "", reply_markup: Any = None) -> MagicMock:
        self.next_msg_id += 1
        msg = MagicMock(spec=Message)
        msg.message_id = self.next_msg_id
        msg.chat = MagicMock(spec=Chat)
        msg.chat.id = int(chat_id)
        msg.chat.type = "private" if int(chat_id) > 0 else "supergroup"
        msg.text = text
        msg.reply_markup = reply_markup
        return msg

    async def send_message(self, **kwargs: Any) -> MagicMock:
        self.sent_messages.append(kwargs)
        return self._make_message(
            kwargs["chat_id"],
            text=kwargs.get("text", ""),
            reply_markup=kwargs.get("reply_markup"),
        )

    async def edit_message_text(self, **kwargs: Any) -> MagicMock:
        self.edited_messages.append(kwargs)
        return self._make_message(
            kwargs["chat_id"],
            text=kwargs.get("text", ""),
            reply_markup=kwargs.get("reply_markup"),
        )

    async def send_photo(self, **kwargs: Any) -> MagicMock:
        if self.fail_photos:
            raise TelegramBadRequest(method=MagicMock(), message="Bad Request: wrong file identifier")
        self.sent_photos.append(kwargs)
        return self._make_message(
            kwargs["chat_id"],
            text=kwargs.get("caption", ""),
            reply_markup=kwargs.get("reply_markup"),
        )

    async def edit_message_media(self, **kwargs: Any) -> MagicMock:
        if self.fail_photos:
            raise TelegramBadRequest(method=MagicMock(), message="Bad Request: invalid media")
        self.edited_media.append(kwargs)
        return self._make_message(kwargs["chat_id"])

    async def edit_message_caption(self, **kwargs: Any) -> MagicMock:
        self.edited_captions.append(kwargs)
        return self._make_message(kwargs["chat_id"])

    async def delete_message(self, **kwargs: Any) -> bool:
        return True

    async def __call__(self, method: Any, **kwargs: Any) -> Any:
        from aiogram.methods import AnswerCallbackQuery

        if isinstance(method, AnswerCallbackQuery):
            self.callback_answers.append({"text": method.text, "show_alert": bool(method.show_alert)})
            return True
        return True


def _make_user(uid: int, name: str, *, is_bot: bool = False) -> User:
    return User(id=uid, is_bot=is_bot, first_name=name, username=name.lower())


def _make_message_update(
    update_id: int,
    *,
    chat_id: int,
    chat_type: str,
    user: User,
    text: str,
    reply_to_user: User | None = None,
) -> Update:
    reply_msg = None
    if reply_to_user is not None:
        reply_msg = Message(
            message_id=50,
            date=datetime.datetime.now(datetime.timezone.utc),
            chat=Chat(id=chat_id, type=chat_type),
            from_user=reply_to_user,
            text="hello",
        )
    msg = Message(
        message_id=51 + update_id,
        date=datetime.datetime.now(datetime.timezone.utc),
        chat=Chat(id=chat_id, type=chat_type),
        from_user=user,
        text=text,
        reply_to_message=reply_msg,
    )
    return Update(update_id=update_id, message=msg)


def _make_callback_update(
    update_id: int,
    *,
    chat_id: int,
    chat_type: str,
    message_id: int,
    user: User,
    data: str,
    recorder: MockBotRecorder,
) -> Update:
    msg = Message(
        message_id=message_id,
        date=datetime.datetime.now(datetime.timezone.utc),
        chat=Chat(id=chat_id, type=chat_type),
        from_user=_make_user(999999, "KayiArenaBot", is_bot=True),
        text="placeholder",
    )
    cb = CallbackQuery(
        id=f"cb_{update_id}",
        from_user=user,
        chat_instance="inst_1",
        message=msg,
        data=data,
    )
    return Update(update_id=update_id, callback_query=cb)


def test_callback_encoding_and_limits() -> None:
    payload = encode_cb("as", "match_12345678", 12, 6)
    assert len(payload.encode("utf-8")) <= MAX_CALLBACK_DATA_BYTES
    parsed = decode_cb(payload)
    assert parsed is not None
    assert parsed.action == "as"
    assert parsed.args == ("match_12345678", "12", "6")
    assert decode_cb("invalid:payload") is None
    with pytest.raises(ValueError):
        encode_cb("x" * 70)


def test_public_commands_use_arena_not_draft() -> None:
    names = {c.command for c in PUBLIC_BOT_COMMANDS}
    assert "arena" in names
    assert "draft" not in names


def test_home_keyboard_and_button_styles() -> None:
    cfg = BotConfig(
        bot_token="fake:token",
        bot_username="KayiArenaBot",
        developer_url="https://t.me/qouba",
        updates_url="https://t.me/KayiBots",
        support_url="https://t.me/KayiBots",
    )
    kb = build_home_keyboard(cfg)
    flat = [b for row in kb.inline_keyboard for b in row]
    assert flat[0].text == "⚔️ Enter Arena"
    assert flat[0].model_dump(exclude_none=True)["style"] == "primary"
    assert any(b.url == "https://t.me/KayiArenaBot?startgroup=true" for b in flat)
    assert any(b.url == "https://t.me/KayiBots" for b in flat)
    assert any(b.url == "https://t.me/qouba" for b in flat)


@pytest.mark.asyncio
async def test_start_arena_challenge_and_full_e2e_match() -> None:
    db = CharacterDatabase(":memory:")
    _seed_naruto_db(db)
    clock = FakeClock()
    mgr = MatchManager(db, dataset_kind=DatasetKind.PRODUCTION, clock=clock)
    bot = MockBotRecorder()
    cfg = BotConfig(bot_token="fake:token", bot_username="KayiArenaBot")
    dp, coordinator = create_dispatcher(bot=bot, config=cfg, db=db, manager=mgr)

    alex = _make_user(101, "Alex <Pro>")
    kai = _make_user(202, "Kai & Co")
    spectator = _make_user(303, "Watcher")

    # 1. /start in private & group
    await dp.feed_update(bot, _make_message_update(1, chat_id=101, chat_type="private", user=alex, text="/start"))
    assert "KAYI ARENA" in bot.sent_messages[-1]["text"]
    assert bot.sent_messages[-1]["reply_markup"] is not None

    await dp.feed_update(bot, _make_message_update(2, chat_id=-1001, chat_type="supergroup", user=alex, text="/start"))
    assert bot.sent_messages[-1]["reply_markup"] is None

    # 2. Duplicate update_id is dropped
    await dp.feed_update(bot, _make_message_update(2, chat_id=-1001, chat_type="supergroup", user=alex, text="/ping"))
    assert len(bot.sent_messages) == 2

    # 3. /arena menu with reply-to-player preserves target across mode switch
    await dp.feed_update(
        bot,
        _make_message_update(3, chat_id=-1001, chat_type="supergroup", user=alex, text="/arena", reply_to_user=kai),
    )
    menu_msg_id = 100 + len(bot.sent_messages)
    assert "Direct challenge target" in bot.sent_messages[-1]["text"]
    assert "Kai &amp; Co" in bot.sent_messages[-1]["text"]  # Escaped!

    # Toggle to Friendly mode on universe menu
    await dp.feed_update(
        bot,
        _make_callback_update(
            4, chat_id=-1001, chat_type="supergroup", message_id=menu_msg_id, user=alex, data=encode_cb("um", 0, "f"), recorder=bot
        ),
    )
    assert "Friendly" in bot.edited_messages[-1]["text"]
    assert "Kai &amp; Co" in bot.edited_messages[-1]["text"]

    # Select Naruto universe -> creates direct challenge
    await dp.feed_update(
        bot,
        _make_callback_update(
            5, chat_id=-1001, chat_type="supergroup", message_id=menu_msg_id, user=alex, data=encode_cb("u", 0, "f", "naruto"), recorder=bot
        ),
    )
    chl_msg_id = 100 + len(bot.sent_messages)
    assert "ARENA CHALLENGE" in bot.sent_messages[-1]["text"]
    assert "Direct Challenge" in bot.sent_messages[-1]["text"]

    # Find challenge ID
    chl = next(iter(mgr._challenges.values()))
    assert chl.game_mode == "friendly"
    original_expires_at = chl.expires_at

    # Switch challenge mode back to Ranked without resetting expiration
    clock.advance(25.0)
    await dp.feed_update(
        bot,
        _make_callback_update(
            6,
            chat_id=-1001,
            chat_type="supergroup",
            message_id=chl_msg_id,
            user=alex,
            data=encode_cb("cm", chl.challenge_id, chl.generation),
            recorder=bot,
        ),
    )
    chl = mgr.get_challenge(chl.challenge_id)
    assert chl is not None
    assert chl.game_mode == "ranked"
    assert chl.expires_at == original_expires_at

    # Spectator cannot accept direct challenge
    await dp.feed_update(
        bot,
        _make_callback_update(
            7,
            chat_id=-1001,
            chat_type="supergroup",
            message_id=chl_msg_id,
            user=spectator,
            data=encode_cb("ca", chl.challenge_id, chl.generation),
            recorder=bot,
        ),
    )
    assert bot.callback_answers[-1]["show_alert"] is True

    # Intended opponent (Kai) accepts
    await dp.feed_update(
        bot,
        _make_callback_update(
            8,
            chat_id=-1001,
            chat_type="supergroup",
            message_id=chl_msg_id,
            user=kai,
            data=encode_cb("ca", chl.challenge_id, chl.generation),
            recorder=bot,
        ),
    )
    match = mgr.get_active_match_for_player("101")
    assert match is not None
    ui_state = coordinator._match_ui[match.match_id]

    # 4. Play all 14 turns through callbacks
    upd_id = 10
    while match.status is MatchLifecycleStatus.DRAFTING:
        active_id = match.draft_snapshot.active_player_id
        active_user = alex if active_id == "101" else kai
        other_user = kai if active_id == "101" else alex

        # Spectator blocked
        upd_id += 1
        await dp.feed_update(
            bot,
            _make_callback_update(
                upd_id,
                chat_id=-1001,
                chat_type="supergroup",
                message_id=ui_state.card_message_id,
                user=spectator,
                data=encode_cb("sh", match.match_id, match.generation),
                recorder=bot,
            ),
        )
        assert "not a participant" in bot.callback_answers[-1]["text"]

        # Wrong player blocked
        upd_id += 1
        await dp.feed_update(
            bot,
            _make_callback_update(
                upd_id,
                chat_id=-1001,
                chat_type="supergroup",
                message_id=ui_state.card_message_id,
                user=other_user,
                data=encode_cb("sh", match.match_id, match.generation),
                recorder=bot,
            ),
        )
        assert "not your turn" in bot.callback_answers[-1]["text"]

        # Active player shuffles
        prev_gen = match.generation
        upd_id += 1
        await dp.feed_update(
            bot,
            _make_callback_update(
                upd_id,
                chat_id=-1001,
                chat_type="supergroup",
                message_id=ui_state.card_message_id,
                user=active_user,
                data=encode_cb("sh", match.match_id, prev_gen),
                recorder=bot,
            ),
        )
        match = mgr.get_match(match.match_id)
        assert match is not None

        # Stale shuffle callback rejected
        upd_id += 1
        await dp.feed_update(
            bot,
            _make_callback_update(
                upd_id,
                chat_id=-1001,
                chat_type="supergroup",
                message_id=ui_state.card_message_id,
                user=active_user,
                data=encode_cb("sh", match.match_id, prev_gen),
                recorder=bot,
            ),
        )
        assert "expired" in bot.callback_answers[-1]["text"].lower()

        # Verify revealed card has NO hidden ratings
        last_caption = bot.edited_media[-1]["media"].caption if bot.edited_media else ""
        assert "Power" not in last_caption
        assert "Fit" not in last_caption

        # Choose first available role
        roster = match.public_view.teams[active_id]
        open_roles = [r for r in ROLES if roster.get(r) is None]
        role_idx = ROLES.index(open_roles[0])

        # Verify dynamic role keyboard layout (2 per row + odd last)
        rk = build_character_revealed_keyboard(match)
        role_btns = [b for row in rk.inline_keyboard[:-1] for b in row]
        assert len(role_btns) == len(open_roles)
        assert all(b.model_dump(exclude_none=True)["style"] == "success" for b in role_btns)

        upd_id += 1
        await dp.feed_update(
            bot,
            _make_callback_update(
                upd_id,
                chat_id=-1001,
                chat_type="supergroup",
                message_id=ui_state.card_message_id,
                user=active_user,
                data=encode_cb("as", match.match_id, match.generation, role_idx),
                recorder=bot,
            ),
        )
        match = mgr.get_match(match.match_id)
        assert match is not None

    assert match.status is MatchLifecycleStatus.COMPLETED
    assert match.outcome is not None
    assert match.outcome.resolution is not None

    # 5. Viewer-specific Detailed Results
    upd_id += 1
    await dp.feed_update(
        bot,
        _make_callback_update(
            upd_id,
            chat_id=-1001,
            chat_type="supergroup",
            message_id=ui_state.board_message_id,
            user=alex,
            data=encode_cb("dr", match.match_id, 0),
            recorder=bot,
        ),
    )
    detail_text = bot.sent_messages[-1]["text"]
    assert "Matchup Details" in detail_text
    assert "Captain Fit:" in detail_text
    assert "Healer Fit:" not in detail_text  # Other 6 fits must NOT be revealed!

    await coordinator.shutdown()
    db.close()


@pytest.mark.asyncio
async def test_media_failure_does_not_invalidate_shuffle_and_safe_api_handles_errors() -> None:
    db = CharacterDatabase(":memory:")
    _seed_naruto_db(db)
    mgr = MatchManager(db, dataset_kind=DatasetKind.PRODUCTION)
    bot = MockBotRecorder()
    bot.fail_photos = True  # Force all photo sends/edits to fail!
    cfg = BotConfig(bot_token="fake:token", bot_username="KayiArenaBot")
    dp, coordinator = create_dispatcher(bot=bot, config=cfg, db=db, manager=mgr)

    alex = _make_user(101, "Alex")
    kai = _make_user(202, "Kai")

    _, res = await mgr.handle_draft_command(
        player_id="101", chat_id="-1001", universe_arg="naruto", game_mode="ranked"
    )
    assert res and res.challenge
    acc = await mgr.accept_challenge(challenge_id=res.challenge.challenge_id, player_id="202")
    assert acc.match
    match = acc.match
    coordinator._player_names["101"] = "Alex"
    coordinator._player_names["202"] = "Kai"

    state = await coordinator.start_match_ui(match, chat_id="-1001")
    assert state is not None
    assert state.card_is_photo is False  # Clean text fallback!

    active_user = alex if match.draft_snapshot.active_player_id == "101" else kai
    await dp.feed_update(
        bot,
        _make_callback_update(
            1,
            chat_id=-1001,
            chat_type="supergroup",
            message_id=state.card_message_id,
            user=active_user,
            data=encode_cb("sh", match.match_id, match.generation),
            recorder=bot,
        ),
    )
    updated = mgr.get_match(match.match_id)
    assert updated is not None and updated.draft_snapshot.held_character is not None

    # Safe API: message not modified returns True
    fake_bot = MagicMock()
    fake_bot.edit_message_text = AsyncMock(
        side_effect=TelegramBadRequest(method=MagicMock(), message="Bad Request: message is not modified")
    )
    assert await edit_message_text_safe(fake_bot, chat_id=1, message_id=1, text="same") is True

    # Safe API: retry after succeeds on retry
    retry_bot = MagicMock()
    retry_bot.send_photo = AsyncMock(
        side_effect=[
            TelegramRetryAfter(method=MagicMock(), message="Too Many Requests", retry_after=0),
            MagicMock(),
        ]
    )
    msg, is_photo = await send_photo_or_text_safe(
        retry_bot, chat_id=1, photo="https://example.com/a.jpg", caption="hi"
    )
    assert msg is not None and is_photo is True

    await coordinator.shutdown()
    db.close()


@pytest.mark.asyncio
async def test_game_recovery_forfeit_inactivity_and_catalogue() -> None:
    db = CharacterDatabase(":memory:")
    _seed_naruto_db(db)
    clock = FakeClock()
    mgr = MatchManager(db, dataset_kind=DatasetKind.PRODUCTION, clock=clock)
    bot = MockBotRecorder()
    cfg = BotConfig(bot_token="fake:token", bot_username="KayiArenaBot")
    dp, coordinator = create_dispatcher(bot=bot, config=cfg, db=db, manager=mgr)

    alex = _make_user(101, "Alex")
    kai = _make_user(202, "Kai")

    # Catalogue command & filtering
    await dp.feed_update(bot, _make_message_update(1, chat_id=101, chat_type="private", user=alex, text="/list"))
    list_msg_id = 100 + len(bot.sent_messages)
    await dp.feed_update(
        bot,
        _make_callback_update(
            2,
            chat_id=101,
            chat_type="private",
            message_id=list_msg_id,
            user=alex,
            data=encode_cb("ls", "naruto", "l", 0),
            recorder=bot,
        ),
    )
    cat_text = bot.edited_messages[-1]["text"]
    assert "Character Catalogue" in cat_text
    assert "Legendary" in cat_text
    assert "Power" not in cat_text

    # Create and accept match
    _, res = await mgr.handle_draft_command(
        player_id="101", chat_id="-1001", universe_arg="naruto", game_mode="ranked"
    )
    assert res and res.challenge
    acc = await mgr.accept_challenge(challenge_id=res.challenge.challenge_id, player_id="202")
    match = acc.match
    assert match is not None
    coordinator._player_names["101"] = "Alex"
    coordinator._player_names["202"] = "Kai"
    old_state = await coordinator.start_match_ui(match, chat_id="-1001")
    assert old_state is not None

    # /game -> Recover Game
    await dp.feed_update(bot, _make_message_update(3, chat_id=101, chat_type="private", user=alex, text="/game"))
    game_msg_id = 100 + len(bot.sent_messages)
    assert "Your Active Match" in bot.sent_messages[-1]["text"]

    await dp.feed_update(
        bot,
        _make_callback_update(
            4,
            chat_id=101,
            chat_type="private",
            message_id=game_msg_id,
            user=alex,
            data=encode_cb("gg", match.match_id),
            recorder=bot,
        ),
    )
    new_state = coordinator._match_ui[match.match_id]
    assert new_state.last_action_line == "Game recovered."
    recovered_match = mgr.get_match(match.match_id)
    assert recovered_match is not None and recovered_match.generation > match.generation

    # Forfeit confirmation -> Yes, Forfeit (use latest generation after recovery)
    latest_gen = recovered_match.generation
    await dp.feed_update(
        bot,
        _make_callback_update(
            5,
            chat_id=101,
            chat_type="private",
            message_id=game_msg_id,
            user=alex,
            data=encode_cb("gf", match.match_id, latest_gen),
            recorder=bot,
        ),
    )
    assert "Forfeit match?" in bot.edited_messages[-1]["text"]

    await dp.feed_update(
        bot,
        _make_callback_update(
            6,
            chat_id=101,
            chat_type="private",
            message_id=game_msg_id,
            user=alex,
            data=encode_cb("gfc", match.match_id, latest_gen),
            recorder=bot,
        ),
    )
    forfeited = mgr.get_match(match.match_id)
    assert forfeited is not None
    assert forfeited.status is MatchLifecycleStatus.FORFEITED
    # Forfeit result must NOT invent 7 matchups (board is edited before card)
    board_result = bot.edited_messages[-2]["text"]
    assert "WINS BY FORFEIT" in board_result
    assert "Combined Score" not in board_result

    await coordinator.shutdown()
    db.close()


@pytest.mark.asyncio
async def test_restart_notifier_follows_kayi_conventions(tmp_path: Path) -> None:
    bot = MockBotRecorder()
    reason_file = tmp_path / "restart_reason.txt"
    reason_file.write_text("Module 6 Telegram UI deployed", encoding="utf-8")
    state_file = tmp_path / "restart_state.json"

    notifier = RestartNotifier(
        bot,  # type: ignore[arg-type]
        owner_id=111,
        log_channel_id=-100222,
        state_path=state_file,
        reason_path=reason_file,
    )
    sent = await notifier.notify_once()
    assert sent is True
    assert len(bot.sent_messages) == 2
    text = bot.sent_messages[0]["text"]
    assert "Kayi Arena Online 🟢" in text
    assert "Module 6 Telegram UI deployed" in text
    assert "restored" not in text.lower()
    assert not reason_file.exists()
    # Second call in same process is suppressed
    assert await notifier.notify_once() is False


def test_text_escaping_and_length_limits() -> None:
    db = CharacterDatabase(":memory:")
    _seed_naruto_db(db)
    u = db.get_universe("naruto")
    dver = db.get_latest_published_version("naruto", kind=DatasetKind.PRODUCTION)
    assert dver is not None
    rec = db.get_character_entry("naruto_c00")

    from app.matches import ManagedMatch, TimeoutPolicy
    from app.engine import start_draft

    catalog, _, _ = db.export_draft_catalog(dver)
    start_res = start_draft(
        match_id="m1",
        players=("1", "2"),
        universe_id="naruto",
        mode="ranked",
        catalog=catalog,
        rarity_weights=u.rarity_weights,
        dataset_version=dver,
        forced_starter="1",
    )
    snap, pv = start_res.snapshot, start_res.public_view
    match = ManagedMatch(
        match_id="m1",
        challenge_id="c1",
        players=("1", "2"),
        universe_id="naruto",
        game_mode="ranked",
        dataset_version=dver,
        status=MatchLifecycleStatus.DRAFTING,
        draft_snapshot=snap,
        public_view=pv,
        generation=0,
        turn_started_at=0.0,
        turn_deadline_at=120.0,
        turn_number_at_start=0,
        extensions_remaining={"1": 1, "2": 1},
        timeout_policy=TimeoutPolicy(),
        created_at=0.0,
        updated_at=0.0,
    )
    evil_names = {"1": "<script>alert(1)</script> &", "2": "Bob > All"}
    board = render_draft_board(
        match,
        universe_name="Naruto <Test>",
        player_names=evil_names,
        char_lookup={},
        seconds_remaining=90.0,
    )
    assert "<script>" not in board
    assert "&lt;script&gt;alert(1)&lt;/script&gt; &amp;" in board
    assert len(board) <= MAX_MESSAGE_LENGTH

    cap = render_revealed_character_card(
        match,
        character=rec,
        universe_name="Naruto",
        player_names=evil_names,
    )
    assert len(cap) <= MAX_CAPTION_LENGTH
    db.close()


@pytest.mark.asyncio
async def test_help_navigation_and_all_pages() -> None:
    db = CharacterDatabase(":memory:")
    _seed_naruto_db(db)
    mgr = MatchManager(db, dataset_kind=DatasetKind.PRODUCTION)
    bot = MockBotRecorder()
    cfg = BotConfig(bot_token="fake:token", bot_username="KayiArenaBot")
    dp, coordinator = create_dispatcher(bot=bot, config=cfg, db=db, manager=mgr)

    user = _make_user(101, "Alex")
    await dp.feed_update(bot, _make_message_update(1, chat_id=101, chat_type="private", user=user, text="/help"))
    help_msg_id = 100 + len(bot.sent_messages)
    assert "How to Play" in bot.sent_messages[-1]["text"]
    assert "01. Challenge" in bot.sent_messages[-1]["text"]

    for idx, (topic, expected) in enumerate(
        [
            ("roles", "The Seven Roles"),
            ("rarity", "Character Rarity"),
            ("rules", "Battle Rules"),
            ("scoring", "Advanced Scoring"),
            ("cmds", "Commands"),
            ("menu", "How to Play"),
        ],
        start=10,
    ):
        await dp.feed_update(
            bot,
            _make_callback_update(
                idx,
                chat_id=101,
                chat_type="private",
                message_id=help_msg_id,
                user=user,
                data=encode_cb("hlp", topic),
                recorder=bot,
            ),
        )
        assert expected in bot.edited_messages[-1]["text"]

    await coordinator.shutdown()
    db.close()
