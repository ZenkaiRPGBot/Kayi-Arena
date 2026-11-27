"""Tests for Phase 7 & 8: Dataset caching, /ping latency, /health readiness, webhook secret, dedup, and races."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from aiohttp.test_utils import TestClient, TestServer

from app.database import CharacterDatabase, ImageMetadata, ImageValidationStatus
from app.matches import MatchManager
from app.persistence import SqliteMatchStore
from app.scoring import SCORING_ROLES
from app.telegram.bot import create_dispatcher
from app.telegram.config import BotConfig
from app.telegram.web import build_health_app


class _FakePingBot:
    def __init__(self) -> None:
        self.id = 999999
        self.messages: list[str] = []

        async def _close() -> None:
            return None

        self.session = SimpleNamespace(close=_close)

    async def get_me(self) -> Any:
        return SimpleNamespace(id=999999, username="KayiArenaBot")

    async def send_message(self, chat_id: int | str, text: str, **kwargs: Any) -> Any:
        self.messages.append(text)
        return SimpleNamespace(message_id=101, chat=SimpleNamespace(id=chat_id), text=text)


def test_dataset_manifest_caching_hits_memory(tmp_path: Path) -> None:
    db = CharacterDatabase(tmp_path / "chars.sqlite3")
    db.create_universe("naruto", "Naruto", active=True)
    for idx in range(1, 15):
        c = db.add_character(
            character_id=f"char_{idx}",
            universe_id="naruto",
            name=f"Ninja {idx}",
            canonical_version="Shippuden",
            rarity="Common",
            power=3,
            fit={r: 3 for r in SCORING_ROLES},
            image=ImageMetadata(
                url_or_ref=f"https://cdn.example.org/{idx}.png",
                status=ImageValidationStatus.VERIFIED,
            ),
        )
        db.submit_for_review(c.character_id)
        db.approve_character(c.character_id)
    db.publish_dataset("naruto", "1.0.0")

    m1 = db.load_manifest("1.0.0")
    m2 = db.load_manifest("1.0.0")
    assert m1 is m2
    rec = db.get_character("1.0.0", "char_1")
    assert rec.character_id == "char_1"


@pytest.mark.asyncio
async def test_ping_reports_real_latencies_and_dedup_drops_duplicate_updates(tmp_path: Path) -> None:
    db = CharacterDatabase(tmp_path / "chars.sqlite3")
    store = SqliteMatchStore(tmp_path / "state.sqlite3")
    bot = _FakePingBot()
    config = BotConfig(bot_token="123:ABC", owner_id=1, admin_ids=(1,))
    dp, coordinator = create_dispatcher(bot=bot, config=config, db=db, store=store)
    now = int(datetime.now(timezone.utc).timestamp())

    for uid in (5001, 5002, 5003):
        await dp.feed_raw_update(
            bot,
            {
                "update_id": uid,
                "message": {
                    "message_id": uid,
                    "date": now,
                    "chat": {"id": 42, "type": "private"},
                    "from": {"id": 42, "is_bot": False, "first_name": "Tester"},
                    "text": "/ping",
                },
            },
        )
    # Duplicate update_id=5003 must be dropped
    await dp.feed_raw_update(
        bot,
        {
            "update_id": 5003,
            "message": {
                "message_id": 5099,
                "date": now,
                "chat": {"id": 42, "type": "private"},
                "from": {"id": 42, "is_bot": False, "first_name": "Tester"},
                "text": "/ping",
            },
        },
    )
    assert len(bot.messages) == 3
    assert "App processing:" in bot.messages[2]
    assert "Database (OK):" in bot.messages[2]
    assert "Telegram API (getMe):" in bot.messages[2]
    assert "Rolling (2 reqs):" in bot.messages[2]


@pytest.mark.asyncio
async def test_health_readiness_and_webhook_secret_enforcement(tmp_path: Path) -> None:
    app_ok = build_health_app(readiness_check=lambda: (True, "sqlite ok"))
    async with TestClient(TestServer(app_ok)) as client:
        resp = await client.get("/health")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "ok"
        assert data["database"] == "sqlite ok"

    app_bad = build_health_app(readiness_check=lambda: (False, "db error"))
    async with TestClient(TestServer(app_bad)) as client:
        resp = await client.get("/health")
        assert resp.status == 503
        data = await resp.json()
        assert data["status"] == "degraded"

    # Webhook secret enforcement
    db = CharacterDatabase(tmp_path / "chars.sqlite3")
    bot = _FakePingBot()
    dp, _ = create_dispatcher(bot=bot, config=BotConfig(bot_token="123:ABC"), db=db)
    app_wh = build_health_app(
        bot=bot,
        dp=dp,
        webhook_path="/telegram/webhook",
        webhook_secret="super-secret-token",
    )
    async with TestClient(TestServer(app_wh)) as client:
        bad_resp = await client.post(
            "/telegram/webhook",
            json={"update_id": 1},
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"},
        )
        assert bad_resp.status in (401, 403)


@pytest.mark.asyncio
async def test_concurrent_challenge_acceptance_race(tmp_path: Path) -> None:
    db = CharacterDatabase(tmp_path / "chars.sqlite3")
    db.create_universe("naruto", "Naruto", active=True)
    for idx in range(1, 15):
        c = db.add_character(
            character_id=f"char_{idx}",
            universe_id="naruto",
            name=f"Ninja {idx}",
            canonical_version="Shippuden",
            rarity="Common",
            power=3,
            fit={r: 3 for r in SCORING_ROLES},
            image=ImageMetadata(
                url_or_ref=f"https://cdn.example.org/{idx}.png",
                status=ImageValidationStatus.VERIFIED,
            ),
        )
        db.submit_for_review(c.character_id)
        db.approve_character(c.character_id)
    db.publish_dataset("naruto", "1.0.0")

    store = SqliteMatchStore(tmp_path / "state.sqlite3")
    mgr = MatchManager(db, store=store)
    _, created = await mgr.handle_draft_command(
        player_id="100", chat_id="-1001", universe_arg="naruto"
    )
    assert created and created.challenge is not None
    cid = created.challenge.challenge_id

    r1, r2 = await asyncio.gather(
        mgr.accept_challenge(challenge_id=cid, player_id="200"),
        mgr.accept_challenge(challenge_id=cid, player_id="300"),
    )
    accepted_count = int(r1.accepted) + int(r2.accepted)
    assert accepted_count == 1
