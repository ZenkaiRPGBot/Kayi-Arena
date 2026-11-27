"""Automated tests for Module 9: Admin Operations, Security, Maintenance & Transport."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from aiogram.types import CallbackQuery, Chat, Message, Update, User

from app.database import (
    CharacterDatabase,
    EvaluationStatus,
    ImageMetadata,
    ImageValidationStatus,
    SpeciesKind,
)
from app.matches import MatchLifecycleStatus, MatchManager
from app.persistence import SqliteMatchStore
from app.scoring import DatasetKind, SCORING_ROLES
from app.telegram import BotConfig, create_dispatcher
from app.telegram.web import build_health_app


class MockAdminBot:
    def __init__(self) -> None:
        self.id = 999999
        self.next_msg_id = 300
        self.sent_messages: list[dict[str, Any]] = []
        self.edited_messages: list[dict[str, Any]] = []
        self.callback_answers: list[dict[str, Any]] = []

    def _msg(self, chat_id: int | str, text: str = "") -> MagicMock:
        self.next_msg_id += 1
        m = MagicMock(spec=Message)
        m.message_id = self.next_msg_id
        m.chat = MagicMock(spec=Chat)
        m.chat.id = int(chat_id)
        m.chat.type = "private" if int(chat_id) > 0 else "supergroup"
        m.text = text
        return m

    async def send_message(self, **kwargs: Any) -> MagicMock:
        self.sent_messages.append(kwargs)
        return self._msg(kwargs["chat_id"], kwargs.get("text", ""))

    async def edit_message_text(self, **kwargs: Any) -> MagicMock:
        self.edited_messages.append(kwargs)
        return self._msg(kwargs["chat_id"], kwargs.get("text", ""))

    async def send_photo(self, **kwargs: Any) -> MagicMock:
        return self._msg(kwargs["chat_id"], kwargs.get("caption", ""))

    async def __call__(self, method: Any, **kwargs: Any) -> Any:
        from aiogram.methods import AnswerCallbackQuery

        if isinstance(method, AnswerCallbackQuery):
            self.callback_answers.append({"text": method.text, "show_alert": bool(method.show_alert)})
        return True


def _user(uid: int, name: str) -> User:
    return User(id=uid, is_bot=False, first_name=name, username=name.lower())


def _msg_upd(upd_id: int, *, chat_id: int, chat_type: str, user: User, text: str) -> Update:
    return Update(
        update_id=upd_id,
        message=Message(
            message_id=100 + upd_id,
            date=datetime.datetime.now(datetime.timezone.utc),
            chat=Chat(id=chat_id, type=chat_type),
            from_user=user,
            text=text,
        ),
    )


def _cb_upd(
    upd_id: int, *, chat_id: int, chat_type: str, msg_id: int, user: User, data: str
) -> Update:
    return Update(
        update_id=upd_id,
        callback_query=CallbackQuery(
            id=f"cb_{upd_id}",
            from_user=user,
            chat_instance="ci_1",
            message=Message(
                message_id=msg_id,
                date=datetime.datetime.now(datetime.timezone.utc),
                chat=Chat(id=chat_id, type=chat_type),
                from_user=_user(999999, "KayiArenaBot"),
                text="panel",
            ),
            data=data,
        ),
    )


def _seed_review_universe(db: CharacterDatabase) -> None:
    db.create_universe("naruto", "Naruto", active=True)
    for i in range(16):
        cid = f"naruto_c{i:02d}"
        fits = {r: ((i + idx) % 5) + 1 for idx, r in enumerate(SCORING_ROLES)}
        db.add_character(
            character_id=cid,
            universe_id="naruto",
            name=f"Ninja {i:02d}",
            species=SpeciesKind.HUMAN,
            rarity="Common",
            power=(i % 5) + 1,
            fit=fits,
            canonical_version="v1",
            image=ImageMetadata(
                url_or_ref=f"https://example.com/{cid}.jpg",
                status=ImageValidationStatus.VERIFIED,
            ),
        )
        db.submit_for_review(cid)
        if i < 15:
            db.approve_character(cid)
    db.publish_dataset("naruto", "naruto-v1", kind=DatasetKind.PRODUCTION)


@pytest.mark.asyncio
async def test_admin_authorization_and_private_chat_restriction(tmp_path: Path) -> None:
    db = CharacterDatabase(tmp_path / "chars.sqlite3")
    _seed_review_universe(db)
    store = SqliteMatchStore(tmp_path / "state.sqlite3")
    mgr = MatchManager(db, store=store)
    bot = MockAdminBot()
    cfg = BotConfig(bot_token="secret_token_do_not_leak", owner_id=1000, admin_ids=(1001,))
    dp, coordinator = create_dispatcher(bot=bot, config=cfg, db=db, manager=mgr, store=store)

    outsider = _user(555, "Outsider")
    admin = _user(1000, "Owner")

    # Non-admin blocked from /admin and adm:* callbacks
    await dp.feed_update(bot, _msg_upd(1, chat_id=555, chat_type="private", user=outsider, text="/admin"))
    assert "Unauthorized" in bot.sent_messages[-1]["text"]
    assert "secret_token" not in bot.sent_messages[-1]["text"]

    await dp.feed_update(
        bot, _cb_upd(2, chat_id=555, chat_type="private", msg_id=301, user=outsider, data="adm:dash")
    )
    assert bot.callback_answers[-1]["show_alert"] is True
    assert "Unauthorized" in bot.callback_answers[-1]["text"]

    # Admin blocked from sensitive operations in group chat
    await dp.feed_update(bot, _msg_upd(3, chat_id=-1001, chat_type="supergroup", user=admin, text="/admin"))
    assert "private chats" in bot.sent_messages[-1]["text"]

    # Authorized admin in private chat gets real dashboard
    await dp.feed_update(bot, _msg_upd(4, chat_id=1000, chat_type="private", user=admin, text="/admin"))
    dash = bot.sent_messages[-1]["text"]
    assert "KAYI ARENA ADMIN" in dash
    assert "Database: <b>OK</b>" in dash
    assert "secret_token" not in dash

    await coordinator.shutdown()
    store.close()
    db.close()


@pytest.mark.asyncio
async def test_admin_workflows_universe_character_dataset_match_maintenance_broadcast_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    db = CharacterDatabase(tmp_path / "chars.sqlite3")
    _seed_review_universe(db)
    store = SqliteMatchStore(tmp_path / "state.sqlite3")
    mgr = MatchManager(db, store=store)
    bot = MockAdminBot()
    cfg = BotConfig(bot_token="secret_tok", owner_id=1000)
    dp, coordinator = create_dispatcher(bot=bot, config=cfg, db=db, manager=mgr, store=store)

    admin = _user(1000, "Owner")
    p1 = _user(201, "Alice")
    p2 = _user(202, "Bob")

    # Seed known chats and an active match
    await dp.feed_update(bot, _msg_upd(1, chat_id=201, chat_type="private", user=p1, text="/ping"))
    chl = (await mgr.create_challenge(challenger_id="201", chat_id="-1001", universe_id="naruto")).challenge
    match = (await mgr.accept_challenge(challenge_id=chl.challenge_id, player_id="202")).match
    assert match is not None

    # Open /admin
    await dp.feed_update(bot, _msg_upd(2, chat_id=1000, chat_type="private", user=admin, text="/admin"))
    panel_id = 300 + len(bot.sent_messages)

    # Stats & Diagnostics
    await dp.feed_update(bot, _cb_upd(3, chat_id=1000, chat_type="private", msg_id=panel_id, user=admin, data="adm:stats"))
    assert "Active matches: <b>1</b>" in bot.edited_messages[-1]["text"]
    await dp.feed_update(bot, _cb_upd(4, chat_id=1000, chat_type="private", msg_id=panel_id, user=admin, data="adm:diag"))
    assert "Database integrity: <b>OK</b>" in bot.edited_messages[-1]["text"]

    # Approve REVIEW character naruto_c15
    await dp.feed_update(
        bot, _cb_upd(5, chat_id=1000, chat_type="private", msg_id=panel_id, user=admin, data="adm:chconf:naruto_c15")
    )
    assert db.get_character_entry("naruto_c15").status is EvaluationStatus.APPROVED

    # Publish new immutable dataset (existing match stays pinned to naruto-v1!)
    await dp.feed_update(
        bot, _cb_upd(6, chat_id=1000, chat_type="private", msg_id=panel_id, user=admin, data="adm:dpubc:naruto")
    )
    assert "Published immutable <b>production</b> dataset" in bot.edited_messages[-1]["text"]

    # Even when bot config is DatasetKind.TEST, adm:dpubc explicitly publishes PRODUCTION
    coordinator.config = BotConfig(bot_token="secret_tok", owner_id=1000, dataset_kind=DatasetKind.TEST)
    await dp.feed_update(
        bot, _cb_upd(60, chat_id=1000, chat_type="private", msg_id=panel_id, user=admin, data="adm:dpubc:naruto")
    )
    assert "Published immutable <b>production</b> dataset" in bot.edited_messages[-1]["text"]
    latest_prod = db.get_latest_published_version("naruto", kind=DatasetKind.PRODUCTION)
    assert latest_prod is not None
    assert db.load_manifest(latest_prod).kind is DatasetKind.PRODUCTION

    # Multiple testing publications within the same second must also succeed without VERSION_EXISTS
    await dp.feed_update(
        bot, _cb_upd(61, chat_id=1000, chat_type="private", msg_id=panel_id, user=admin, data="adm:dpubt:naruto")
    )
    assert "Published preliminary testing dataset" in bot.edited_messages[-1]["text"]
    await dp.feed_update(
        bot, _cb_upd(62, chat_id=1000, chat_type="private", msg_id=panel_id, user=admin, data="adm:dpubt:naruto")
    )
    assert "Published preliminary testing dataset" in bot.edited_messages[-1]["text"]
    coordinator.config = cfg
    assert mgr.get_match(match.match_id).dataset_version == "naruto-v1"

    # Toggle universe inactive with confirmation
    await dp.feed_update(
        bot, _cb_upd(7, chat_id=1000, chat_type="private", msg_id=panel_id, user=admin, data="adm:uconf:naruto")
    )
    assert db.get_universe("naruto").active is False

    # Administratively terminate active match (no fabricated victory)
    await dp.feed_update(
        bot, _cb_upd(8, chat_id=1000, chat_type="private", msg_id=panel_id, user=admin, data=f"adm:mtermc:{match.match_id}")
    )
    term_m = mgr.get_match(match.match_id)
    assert term_m is not None and term_m.status is MatchLifecycleStatus.TERMINATED_ADMIN
    assert term_m.outcome is not None and term_m.outcome.winner_id is None

    # Enable maintenance mode -> non-admin /arena blocked, admin /admin allowed
    await dp.feed_update(
        bot, _cb_upd(9, chat_id=1000, chat_type="private", msg_id=panel_id, user=admin, data="adm:mconf")
    )
    assert coordinator.is_maintenance_mode() is True
    await dp.feed_update(bot, _msg_upd(10, chat_id=201, chat_type="private", user=p1, text="/arena"))
    assert "Maintenance Mode" in bot.sent_messages[-1]["text"]

    # Broadcast preview & send
    await dp.feed_update(
        bot, _cb_upd(11, chat_id=1000, chat_type="private", msg_id=panel_id, user=admin, data="adm:bcast")
    )
    await dp.feed_update(
        bot, _msg_upd(12, chat_id=1000, chat_type="private", user=admin, text="Scheduled update tonight!")
    )
    assert "Broadcast Preview" in bot.sent_messages[-1]["text"]
    await dp.feed_update(
        bot, _cb_upd(13, chat_id=1000, chat_type="private", msg_id=panel_id, user=admin, data="adm:bsend")
    )
    assert "Broadcast Complete" in bot.edited_messages[-1]["text"]

    # Database backup
    await dp.feed_update(
        bot, _cb_upd(14, chat_id=1000, chat_type="private", msg_id=panel_id, user=admin, data="adm:backup")
    )
    assert "Database Backup Complete" in bot.edited_messages[-1]["text"]
    assert list((tmp_path / "backups").glob("*.sqlite3"))

    # Audit log recorded all actions
    audit = store.list_admin_audit_log(limit=20)
    actions = {entry["action"] for entry in audit}
    assert {
        "approve_character",
        "publish_dataset",
        "toggle_universe_active",
        "terminate_match",
        "set_maintenance_mode",
        "send_broadcast",
        "database_backup",
    }.issubset(actions)

    await coordinator.shutdown()
    store.close()
    db.close()


def test_transport_mode_configuration_and_webhook_app(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRANSPORT_MODE", "webhook")
    monkeypatch.setenv("WEBHOOK_BASE_URL", "https://kayi-arena.onrender.com")
    monkeypatch.setenv("ADMIN_IDS", "111, 222")
    monkeypatch.setenv("OWNER_ID", "999")
    cfg = BotConfig.from_env()
    assert cfg.transport_mode == "webhook"
    assert cfg.webhook_url == "https://kayi-arena.onrender.com/telegram/webhook"
    assert cfg.is_admin(999) and cfg.is_admin(111) and cfg.is_admin(222)
    assert not cfg.is_admin(333)

    # Without WEBHOOK_BASE_URL, safely falls back to polling
    monkeypatch.delenv("WEBHOOK_BASE_URL", raising=False)
    monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)
    cfg2 = BotConfig.from_env()
    assert cfg2.transport_mode == "polling"

    app = build_health_app(extra_status={"transport_mode": "polling"})
    routes = {r.resource.canonical for r in app.router.routes() if r.resource is not None}
    assert "/" in routes and "/ping" in routes and "/health" in routes


@pytest.mark.asyncio
async def test_health_endpoints_liveness_readiness_and_self_ping_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio
    from aiohttp.test_utils import TestClient, TestServer
    from app.telegram.web import run_self_ping_loop

    # Local dev defaults: self-ping disabled when RENDER_EXTERNAL_URL is unset
    monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)
    monkeypatch.delenv("ENABLE_SELF_PING", raising=False)
    monkeypatch.delenv("PING_URL", raising=False)
    monkeypatch.delenv("SELF_PING_INITIAL_DELAY", raising=False)
    monkeypatch.delenv("SELF_PING_INTERVAL", raising=False)
    monkeypatch.delenv("SELF_PING_TIMEOUT", raising=False)
    local_cfg = BotConfig.from_env()
    assert local_cfg.enable_self_ping is False
    assert local_cfg.ping_url == ""

    # Render environment: auto-enables self-ping with /ping fallback
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://kayi-arena.onrender.com")
    render_cfg = BotConfig.from_env()
    assert render_cfg.enable_self_ping is True
    assert render_cfg.ping_url == "https://kayi-arena.onrender.com/ping"
    assert render_cfg.self_ping_interval == 600.0

    # /ping must NOT call readiness_check (no unnecessary DB ops)
    db_calls = 0
    db_ok = True

    def _readiness() -> tuple[bool, str]:
        nonlocal db_calls
        db_calls += 1
        return (True, "mongodb-ok") if db_ok else (False, "mongodb-unreachable")

    app = build_health_app(readiness_check=_readiness, extra_status={"transport_mode": "webhook"})
    async with TestClient(TestServer(app)) as client:
        r_root = await client.get("/")
        assert r_root.status == 200
        assert (await r_root.json())["status"] == "ok"
        assert db_calls == 0

        r_ping = await client.get("/ping")
        assert r_ping.status == 200
        ping_body = await r_ping.json()
        assert ping_body["status"] == "ok"
        assert "uptime" in ping_body
        assert db_calls == 0

        r_health_ok = await client.get("/health")
        assert r_health_ok.status == 200
        assert (await r_health_ok.json())["database"] == "mongodb-ok"
        assert db_calls == 1

        db_ok = False
        r_health_bad = await client.get("/health")
        assert r_health_bad.status == 503
        assert (await r_health_bad.json())["status"] == "degraded"

    # Self-ping loop reuses one session, survives failures, and stops on stop_event
    sessions_created = 0
    get_calls = 0
    stop_event = asyncio.Event()

    class _FakeResp:
        status = 200
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return False

    class _FakeSession:
        async def __aenter__(self):
            nonlocal sessions_created
            sessions_created += 1
            return self
        async def __aexit__(self, *args):
            return False
        def get(self, url: str):
            nonlocal get_calls
            get_calls += 1
            if get_calls == 1:
                raise RuntimeError("transient network error")
            if get_calls >= 2:
                stop_event.set()
            return _FakeResp()

    await run_self_ping_loop(
        ping_url="https://kayi-arena.onrender.com/ping",
        stop_event=stop_event,
        initial_delay=0.0,
        interval=0.01,
        session_factory=_FakeSession,
    )
    assert sessions_created == 1
    assert get_calls == 2
