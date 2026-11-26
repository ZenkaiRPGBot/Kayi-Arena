"""Comprehensive Module 7 tests: SQLite persistence, restarts, and recovery."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from aiogram.exceptions import TelegramBadRequest

from app.database import (
    CharacterDatabase,
    ImageMetadata,
    ImageValidationStatus,
    SpeciesKind,
)
from app.engine import DraftPhase
from app.matches import (
    ChallengeStatus,
    MatchLifecycleStatus,
    MatchManager,
    MatchManagementErrorCode,
    MatchOutcomeReason,
    MessageReference,
)
from app.persistence import CorruptStateError, PersistenceError, SqliteMatchStore
from app.scoring import DatasetKind, SCORING_ROLES
from app.telegram import BotConfig, RestartNotifier, create_dispatcher
from app.telegram.media import CharacterMediaResolver


class FakeClock:
    def __init__(self, start: float = 1_700_000_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class MockBot:
    def __init__(self) -> None:
        self.id = 999999
        self.next_msg_id = 500
        self.sent_messages: list[dict[str, Any]] = []
        self.edited_messages: list[dict[str, Any]] = []
        self.deleted_ids: set[int] = set()

    def _msg(self, chat_id: int | str, text: str = "") -> MagicMock:
        self.next_msg_id += 1
        m = MagicMock()
        m.message_id = self.next_msg_id
        m.chat = MagicMock()
        m.chat.id = int(chat_id)
        m.text = text
        return m

    async def send_message(self, **kwargs: Any) -> MagicMock:
        self.sent_messages.append(kwargs)
        return self._msg(kwargs["chat_id"], kwargs.get("text", ""))

    async def edit_message_text(self, **kwargs: Any) -> MagicMock:
        if int(kwargs["message_id"]) in self.deleted_ids:
            raise TelegramBadRequest(method=MagicMock(), message="Bad Request: message to edit not found")
        self.edited_messages.append(kwargs)
        return self._msg(kwargs["chat_id"], kwargs.get("text", ""))

    async def send_photo(self, **kwargs: Any) -> MagicMock:
        return self._msg(kwargs["chat_id"], kwargs.get("caption", ""))

    async def edit_message_media(self, **kwargs: Any) -> MagicMock:
        if int(kwargs["message_id"]) in self.deleted_ids:
            raise TelegramBadRequest(method=MagicMock(), message="Bad Request: message to edit not found")
        return self._msg(kwargs["chat_id"])

    async def edit_message_caption(self, **kwargs: Any) -> MagicMock:
        if int(kwargs["message_id"]) in self.deleted_ids:
            raise TelegramBadRequest(method=MagicMock(), message="Bad Request: message to edit not found")
        return self._msg(kwargs["chat_id"])


def _seed_db(db_path: Path, *, version: str = "naruto-v1", prefix: str = "c") -> CharacterDatabase:
    db = CharacterDatabase(db_path)
    try:
        db.get_universe("naruto")
    except Exception:
        db.create_universe(universe_id="naruto", name="Naruto", active=True)
    rarities = ["Common", "Uncommon", "Rare", "Epic", "Legendary"]
    for i in range(18):
        cid = f"naruto_{prefix}{i:02d}"
        fits = {r: ((i + idx) % 5) + 1 for idx, r in enumerate(SCORING_ROLES)}
        db.add_character(
            character_id=cid,
            universe_id="naruto",
            name=f"Ninja {prefix}{i:02d}",
            species=SpeciesKind.HUMAN,
            rarity=rarities[i % len(rarities)],
            power=(i % 5) + 1,
            fit=fits,
            canonical_version=version,
            image=ImageMetadata(
                url_or_ref=f"https://example.com/{cid}.jpg",
                status=ImageValidationStatus.VERIFIED,
            ),
        )
        db.submit_for_review(cid)
        db.approve_character(cid)
    db.publish_dataset(universe_id="naruto", dataset_version=version, kind=DatasetKind.PRODUCTION)
    return db


@pytest.mark.asyncio
async def test_restart_during_pending_and_expired_challenges(tmp_path: Path) -> None:
    char_db_path = tmp_path / "chars.sqlite3"
    state_db_path = tmp_path / "state.sqlite3"
    _seed_db(char_db_path).close()

    clock = FakeClock()
    db1 = CharacterDatabase(char_db_path)
    store1 = SqliteMatchStore(state_db_path)
    mgr1 = MatchManager(db1, store=store1, clock=clock)

    c_pending = (await mgr1.create_challenge(challenger_id="p1", chat_id="-1001", universe_id="naruto")).challenge
    c_expired = (await mgr1.create_challenge(challenger_id="p2", chat_id="-1001", universe_id="naruto")).challenge
    assert c_pending and c_expired
    store1.set_challenge_message(c_pending.challenge_id, "-1001", "10")
    store1.set_challenge_message(c_expired.challenge_id, "-1001", "11")
    # Make c_expired expire 100s later while c_pending still has 200s
    clock.advance(100.0)
    c_pending2 = (await mgr1.create_challenge(challenger_id="p3", chat_id="-1001", universe_id="naruto")).challenge
    assert c_pending2
    store1.set_challenge_message(c_pending2.challenge_id, "-1001", "12")
    store1.close()
    db1.close()

    # Advance past c_pending & c_expired (300s), before c_pending2 (400s)
    clock.advance(210.0)
    db2 = CharacterDatabase(char_db_path)
    store2 = SqliteMatchStore(state_db_path)
    mgr2 = MatchManager(db2, store=store2, clock=clock)
    bot2 = MockBot()
    _, coord2 = create_dispatcher(
        bot=bot2, config=BotConfig(bot_token="t"), db=db2, manager=mgr2, store=store2
    )
    report = await coord2.recover_on_startup()
    assert report.expired_challenges == 2
    assert report.pending_challenges == 1

    # Expired challenge cannot be accepted after restart
    acc_exp = await mgr2.accept_challenge(challenge_id=c_expired.challenge_id, player_id="p4")
    assert not acc_exp.accepted and acc_exp.error_code is MatchManagementErrorCode.CHALLENGE_NOT_OPEN

    # Pending challenge is still valid and preserves original expires_at
    restored_chl = mgr2.get_challenge(c_pending2.challenge_id)
    assert restored_chl is not None and restored_chl.expires_at == c_pending2.expires_at
    acc_ok = await mgr2.accept_challenge(challenge_id=c_pending2.challenge_id, player_id="p4")
    assert acc_ok.accepted

    await coord2.shutdown()
    store2.close()
    db2.close()


@pytest.mark.asyncio
async def test_restart_across_shuffle_skip_assign_extension_and_global_lock(tmp_path: Path) -> None:
    char_db_path = tmp_path / "chars.sqlite3"
    state_db_path = tmp_path / "state.sqlite3"
    _seed_db(char_db_path).close()
    clock = FakeClock()

    # Boot 1: accept -> shuffle -> restart with held character
    db1 = CharacterDatabase(char_db_path)
    store1 = SqliteMatchStore(state_db_path)
    mgr1 = MatchManager(db1, store=store1, clock=clock)
    chl = (await mgr1.create_challenge(challenger_id="p1", chat_id="-1001", universe_id="naruto")).challenge
    match = (await mgr1.accept_challenge(challenge_id=chl.challenge_id, player_id="p2")).match
    assert match is not None
    orig_deadline = match.turn_deadline_at
    active = match.draft_snapshot.active_player_id
    other = "p2" if active == "p1" else "p1"

    clock.advance(20.0)
    sh = await mgr1.shuffle_match(
        match_id=match.match_id,
        player_id=active,
        expected_revision=match.draft_snapshot.revision,
        expected_generation=match.generation,
    )
    assert sh.accepted and sh.match
    held_char = sh.match.draft_snapshot.held_character
    assert held_char is not None
    store1.close()
    db1.close()

    # Boot 2: fresh instances — held character & original deadline preserved (NOT reset to 120s!)
    clock.advance(15.0)
    db2 = CharacterDatabase(char_db_path)
    store2 = SqliteMatchStore(state_db_path)
    mgr2 = MatchManager(db2, store=store2, clock=clock)
    report2, _, _, restored2, _, _ = await mgr2.recover_from_store()
    assert report2.restored_matches == 1
    m2 = restored2[0]
    assert m2.draft_snapshot.phase is DraftPhase.AWAITING_DECISION
    assert m2.draft_snapshot.held_character == held_char
    assert m2.turn_deadline_at == orig_deadline

    # Global active-match lock survived restart!
    blocked = await mgr2.create_challenge(challenger_id="p1", chat_id="-1001", universe_id="naruto")
    assert not blocked.accepted and blocked.error_code is MatchManagementErrorCode.PLAYER_ALREADY_IN_MATCH

    # Skip -> restart -> verify skips_remaining, last_skipped_id, and preserved deadline
    sk = await mgr2.skip_match_character(
        match_id=m2.match_id,
        player_id=active,
        expected_revision=m2.draft_snapshot.revision,
        expected_generation=m2.generation,
    )
    assert sk.accepted and sk.match
    store2.close()
    db2.close()

    # Boot 3: fresh instances -> shuffle again (cannot redraw held_char) -> assign -> extend -> restart
    clock.advance(10.0)
    db3 = CharacterDatabase(char_db_path)
    store3 = SqliteMatchStore(state_db_path)
    mgr3 = MatchManager(db3, store=store3, clock=clock)
    await mgr3.recover_from_store()
    m3 = mgr3.get_match(m2.match_id)
    assert m3 is not None
    assert m3.draft_snapshot.skips_remaining[active] == 1
    assert m3.draft_snapshot.last_skipped_id == held_char.character_id
    assert m3.turn_deadline_at == orig_deadline

    sh2 = await mgr3.shuffle_match(
        match_id=m3.match_id,
        player_id=active,
        expected_revision=m3.draft_snapshot.revision,
        expected_generation=m3.generation,
    )
    assert sh2.accepted and sh2.match
    assert sh2.match.draft_snapshot.held_character != held_char

    as1 = await mgr3.assign_match_role(
        match_id=m3.match_id,
        player_id=active,
        role="Captain",
        expected_revision=sh2.match.draft_snapshot.revision,
        expected_generation=sh2.match.generation,
    )
    assert as1.accepted and as1.match
    ext = await mgr3.grant_turn_extension(
        match_id=m3.match_id,
        granting_player_id=active,
        expected_generation=as1.match.generation,
    )
    assert ext.accepted and ext.match
    extended_deadline = ext.match.turn_deadline_at
    store3.close()
    db3.close()

    # Boot 4: verify extended deadline and 0 remaining extensions for `other`
    db4 = CharacterDatabase(char_db_path)
    store4 = SqliteMatchStore(state_db_path)
    mgr4 = MatchManager(db4, store=store4, clock=clock)
    await mgr4.recover_from_store()
    m4 = mgr4.get_match(m2.match_id)
    assert m4 is not None
    assert m4.turn_deadline_at == extended_deadline
    assert m4.extensions_remaining[other] == 0
    assert m4.draft_snapshot.teams[active]["Captain"] is not None
    store4.close()
    db4.close()


@pytest.mark.asyncio
async def test_downtime_inactivity_no_fabricated_victory_and_abandonment(tmp_path: Path) -> None:
    char_db_path = tmp_path / "chars.sqlite3"
    state_db_path = tmp_path / "state.sqlite3"
    _seed_db(char_db_path).close()
    clock = FakeClock()

    db1 = CharacterDatabase(char_db_path)
    store1 = SqliteMatchStore(state_db_path)
    mgr1 = MatchManager(db1, store=store1, clock=clock)
    c1 = (await mgr1.create_challenge(challenger_id="p1", chat_id="-1001", universe_id="naruto")).challenge
    m1 = (await mgr1.accept_challenge(challenge_id=c1.challenge_id, player_id="p2")).match
    c2 = (await mgr1.create_challenge(challenger_id="p3", chat_id="-1001", universe_id="naruto")).challenge
    m2 = (await mgr1.accept_challenge(challenge_id=c2.challenge_id, player_id="p4")).match
    assert m1 and m2

    # m2 enters inactivity claim window before shutdown
    clock.advance(125.0)
    to2 = await mgr1.handle_turn_timeout(
        match_id=m2.match_id,
        expected_revision=m2.draft_snapshot.revision,
        expected_turn_number=m2.turn_number_at_start,
    )
    assert to2.accepted
    store1.close()
    db1.close()

    # 100s downtime passes: m2's 60s claim window expired -> ABANDONED (no winner!)
    # m1's turn expired during downtime -> offered claim window (NOT auto-victory!)
    clock.advance(100.0)
    db2 = CharacterDatabase(char_db_path)
    store2 = SqliteMatchStore(state_db_path)
    mgr2 = MatchManager(db2, store=store2, clock=clock)
    report, _, _, restored, prompted, abandoned = await mgr2.recover_from_store()

    assert report.abandoned_matches == 1
    assert report.inactivity_prompted_matches == 1
    assert abandoned[0].match_id == m2.match_id
    assert abandoned[0].status is MatchLifecycleStatus.ABANDONED
    assert abandoned[0].outcome is not None
    assert abandoned[0].outcome.winner_id is None
    assert abandoned[0].outcome.reason is MatchOutcomeReason.MUTUAL_INACTIVITY_ABANDONMENT

    assert prompted[0].match_id == m1.match_id
    assert prompted[0].status is MatchLifecycleStatus.DRAFTING
    assert prompted[0].inactivity_claim_offered_to is not None

    # Historical record persisted for abandoned match without fabricated matchups
    hist = store2.get_historical_match(m2.match_id)
    assert hist is not None and hist.wins_player_1 is None
    store2.close()
    db2.close()


@pytest.mark.asyncio
async def test_deleted_message_recovery_generation_invalidation_and_dataset_pinning(tmp_path: Path) -> None:
    char_db_path = tmp_path / "chars.sqlite3"
    state_db_path = tmp_path / "state.sqlite3"
    db1 = _seed_db(char_db_path, version="naruto-v1", prefix="v1_")
    clock = FakeClock()
    store1 = SqliteMatchStore(state_db_path)
    mgr1 = MatchManager(db1, store=store1, clock=clock)
    bot1 = MockBot()
    _, coord1 = create_dispatcher(
        bot=bot1, config=BotConfig(bot_token="t"), db=db1, manager=mgr1, store=store1
    )

    chl = (await mgr1.create_challenge(challenger_id="p1", chat_id="-1001", universe_id="naruto")).challenge
    match = (await mgr1.accept_challenge(challenge_id=chl.challenge_id, player_id="p2")).match
    assert match is not None
    old_gen = match.generation
    ui_state = await coord1.start_match_ui(match, chat_id="-1001")
    assert ui_state is not None

    # Publish naruto-v2 while match is active -> match stays pinned to naruto-v1
    _seed_db(char_db_path, version="naruto-v2", prefix="v2_").close()

    # Delete ONLY the card message in Telegram, keep board intact
    bot1.deleted_ids.add(ui_state.card_message_id)
    sent_before = len(bot1.sent_messages)
    recovered_ui = await coord1.recover_game_ui(match)
    assert recovered_ui is not None
    # Board was edited in-place (not duplicated!), only card was re-sent
    assert recovered_ui.board_message_id == ui_state.board_message_id
    assert recovered_ui.card_message_id != ui_state.card_message_id
    assert len(bot1.sent_messages) == sent_before + 1

    # Obsolete generation is rejected
    stale = await mgr1.shuffle_match(
        match_id=match.match_id,
        player_id=match.draft_snapshot.active_player_id,
        expected_revision=match.draft_snapshot.revision,
        expected_generation=old_gen,
    )
    assert not stale.accepted and stale.error_code is MatchManagementErrorCode.STALE_CONTROL_GENERATION

    # Pinned dataset version remains naruto-v1 after restart
    store1.close()
    db1.close()
    db2 = CharacterDatabase(char_db_path)
    store2 = SqliteMatchStore(state_db_path)
    mgr2 = MatchManager(db2, store=store2, clock=clock)
    await mgr2.recover_from_store()
    m2 = mgr2.get_match(match.match_id)
    assert m2 is not None and m2.dataset_version == "naruto-v1"

    await coord1.shutdown()
    store2.close()
    db2.close()


def test_schema_migration_backup_rollback_corrupt_state_and_media_cache(tmp_path: Path) -> None:
    db_path = tmp_path / "state.sqlite3"
    store = SqliteMatchStore(db_path)
    assert store.current_schema_version() == 2

    # Online SQLite backup
    backup_path = tmp_path / "backup.sqlite3"
    store.backup_to(backup_path)
    assert backup_path.exists()

    # Media cache & never auto-verifying pending images
    char_db = CharacterDatabase(tmp_path / "chars_media.sqlite3")
    char_db.create_universe("naruto", "Naruto")
    char_db.add_character(
        character_id="naruto_c00",
        universe_id="naruto",
        name="Naruto",
        species=SpeciesKind.HUMAN,
        rarity="Common",
        power=3,
        fit={r: 3 for r in SCORING_ROLES},
        canonical_version="v1",
        image=ImageMetadata(url_or_ref="https://example.com/n.jpg", status=ImageValidationStatus.PENDING),
    )
    pending_entry = char_db.get_character_entry("naruto_c00")
    char_db.close()
    resolver = CharacterMediaResolver(store)
    resolver.record_telegram_file_id(pending_entry, "AgACAgIAAxkBAAI")
    assert resolver.resolve_media_ref(pending_entry) == "AgACAgIAAxkBAAI"
    assert pending_entry.image.status is ImageValidationStatus.PENDING

    # Corrupt JSON state raises CorruptStateError
    store._conn.execute(
        """
        INSERT INTO challenges (
            challenge_id, challenge_type, challenger_id, target_player_id,
            universe_id, game_mode, chat_id, message_id, status,
            created_at, expires_at, generation, accepted_by, match_id
        ) VALUES ('bad1', 'invalid_type', 'p1', NULL, 'naruto', 'ranked', 'c1', NULL, 'open', 0, 1, 0, NULL, NULL)
        """
    )
    with pytest.raises(CorruptStateError):
        store.load_open_challenges()
    store.close()


@pytest.mark.asyncio
async def test_crash_after_persistence_and_missing_dataset_fails_safely(tmp_path: Path) -> None:
    char_db_path = tmp_path / "chars.sqlite3"
    state_db_path = tmp_path / "state.sqlite3"
    db1 = _seed_db(char_db_path, version="naruto-v1")
    clock = FakeClock()
    store1 = SqliteMatchStore(state_db_path)
    mgr1 = MatchManager(db1, store=store1, clock=clock)

    chl = (await mgr1.create_challenge(challenger_id="p1", chat_id="-1001", universe_id="naruto")).challenge
    match = (await mgr1.accept_challenge(challenge_id=chl.challenge_id, player_id="p2")).match
    assert match is not None

    # Complete a shuffle persisted to SQLite, simulate crash before Telegram rendering
    active = match.draft_snapshot.active_player_id
    sh = await mgr1.shuffle_match(
        match_id=match.match_id,
        player_id=active,
        expected_revision=match.draft_snapshot.revision,
        expected_generation=match.generation,
    )
    assert sh.accepted and sh.match
    store1.close()
    db1.close()

    # Reopen with an empty char_db (missing pinned dataset) -> fails safely with recovery_error!
    empty_db = CharacterDatabase(tmp_path / "empty_chars.sqlite3")
    store2 = SqliteMatchStore(state_db_path)
    mgr2 = MatchManager(empty_db, store=store2, clock=clock)
    report, _, _, restored, _, _ = await mgr2.recover_from_store()
    assert report.restored_matches == 0
    assert len(report.recovery_errors) == 1

    # RestartNotifier includes accurate counts without leaking player IDs
    bot = MockBot()
    notifier = RestartNotifier(bot, owner_id=1, state_path=tmp_path / "rs.json")  # type: ignore[arg-type]
    await notifier.notify_once(recovery_report=report)
    msg_text = bot.sent_messages[-1]["text"]
    assert "Recovery warnings: 1" in msg_text
    assert "p1" not in msg_text and "p2" not in msg_text

    store2.close()
    empty_db.close()


@pytest.mark.asyncio
async def test_http_health_server_endpoints_and_graceful_shutdown() -> None:
    import aiohttp
    from app.telegram.web import build_health_app, start_http_server

    app = build_health_app(extra_status={"restored_matches": 1})
    runner, site = await start_http_server(app, host="127.0.0.1", port=0)
    try:
        port = site._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://127.0.0.1:{port}/") as resp:
                assert resp.status == 200
                data = await resp.json()
                assert data["service"] == "kayi-arena"
                assert data["status"] == "ok"

            async with session.get(f"http://127.0.0.1:{port}/health") as resp:
                assert resp.status == 200
                data = await resp.json()
                assert data["status"] == "ok"
                assert data["restored_matches"] == 1
    finally:
        await runner.cleanup()
