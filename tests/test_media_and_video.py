"""Tests for Phase 3-5: SSRF-safe media pipeline, 960x540 standardization, Media Manager, and Welcome Video."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendVideo
from aiogram.types import BufferedInputFile
from PIL import Image

from app.database import (
    CharacterDatabase,
    ImageMetadata,
    ImageValidationStatus,
)
from app.matches import MatchManager
from app.persistence import SqliteMatchStore
from app.scoring import DatasetKind, SCORING_ROLES
from app.telegram.bot import create_dispatcher
from app.telegram.config import BotConfig
from app.telegram.media import (
    CharacterMediaResolver,
    MediaPipeline,
    UnsafeMediaURLError,
    validate_media_url,
)
from app.telegram.service import ArenaTelegramCoordinator


def _make_png_bytes(width: int = 320, height: int = 480, color: tuple[int, int, int] = (220, 40, 40)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (width, height), color).save(buf, format="PNG")
    return buf.getvalue()


class FakeMediaBot:
    def __init__(self, *, fail_video: bool = False) -> None:
        self.id = 999999
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._msg_seq = 100
        self.fail_video = fail_video

    def _next_id(self) -> int:
        self._msg_seq += 1
        return self._msg_seq

    async def send_message(self, chat_id: int | str, text: str, **kwargs: Any) -> Any:
        mid = self._next_id()
        self.calls.append(("send_message", {"chat_id": chat_id, "text": text, **kwargs}))
        return SimpleNamespace(message_id=mid, chat=SimpleNamespace(id=chat_id), text=text)

    async def edit_message_text(self, **kwargs: Any) -> Any:
        self.calls.append(("edit_message_text", kwargs))
        return True

    async def answer_callback_query(self, **kwargs: Any) -> Any:
        self.calls.append(("answer_callback_query", kwargs))
        return True

    async def send_photo(self, chat_id: int | str, photo: Any, caption: str | None = None, **kwargs: Any) -> Any:
        mid = self._next_id()
        self.calls.append(("send_photo", {"chat_id": chat_id, "photo": photo, "caption": caption, **kwargs}))
        return SimpleNamespace(
            message_id=mid,
            chat=SimpleNamespace(id=chat_id),
            photo=[SimpleNamespace(file_id=f"tg_file_{mid}", file_unique_id=f"uniq_{mid}")],
        )

    async def send_video(self, chat_id: int | str, video: Any, caption: str | None = None, **kwargs: Any) -> Any:
        self.calls.append(("send_video", {"chat_id": chat_id, "video": video, "caption": caption, **kwargs}))
        if self.fail_video:
            raise TelegramBadRequest(method=SendVideo(chat_id=chat_id, video=str(video)), message="wrong file identifier")
        mid = self._next_id()
        return SimpleNamespace(
            message_id=mid,
            chat=SimpleNamespace(id=chat_id),
            video=SimpleNamespace(file_id=f"cached_vid_{mid}"),
        )

    async def delete_message(self, chat_id: int | str, message_id: int) -> bool:
        self.calls.append(("delete_message", {"chat_id": chat_id, "message_id": message_id}))
        return True


def _setup_env(tmp_path: Path, *, media_channel_id: int = -100999888, fail_video: bool = False):
    tmp_path.mkdir(parents=True, exist_ok=True)
    db = CharacterDatabase(tmp_path / "chars.sqlite3")
    db.create_universe("naruto", "Naruto", active=True)
    entry = db.add_character(
        character_id="naruto_uzumaki",
        universe_id="naruto",
        name="Naruto Uzumaki",
        canonical_version="Shippuden",
        rarity="Epic",
        power=4,
        fit={role: 4 for role in SCORING_ROLES},
        image=ImageMetadata(
            url_or_ref="https://cdn.example.org/naruto.png",
            status=ImageValidationStatus.PENDING,
        ),
    )
    entry = db.submit_for_review(entry.character_id)
    entry = db.approve_character(entry.character_id)

    store = SqliteMatchStore(tmp_path / "state.sqlite3")
    manager = MatchManager(db, store=store)
    bot = FakeMediaBot(fail_video=fail_video)
    config = BotConfig(
        bot_token="123456:FAKE_TOKEN",
        owner_id=1,
        admin_ids=(1,),
        media_channel_id=media_channel_id,
    )
    dp, coordinator = create_dispatcher(
        bot=bot, config=config, db=db, manager=manager, store=store
    )
    return db, store, coordinator, dp, bot, entry


@pytest.mark.parametrize(
    "bad_url",
    [
        "http://localhost/img.png",
        "http://127.0.0.1/img.png",
        "http://169.254.169.254/latest/meta-data",
        "https://10.0.0.5/secret.png",
        "https://192.168.1.10/a.jpg",
        "file:///etc/passwd",
        "ftp://example.com/a.png",
        "https://user:pass@example.com/a.png",
        "https://metadata.google.internal/computeMetadata/v1/",
    ],
)
def test_ssrf_blocks_unsafe_urls(bad_url: str) -> None:
    with pytest.raises(UnsafeMediaURLError):
        validate_media_url(bad_url, resolve_dns=False)


def test_ssrf_allows_public_https_url() -> None:
    url = "https://static.wikia.nocookie.net/naruto/images/d/d6/Naruto_Part_II.png"
    assert validate_media_url(url, resolve_dns=False) == url


@pytest.mark.asyncio
async def test_media_pipeline_standardizes_uploads_and_skips_cached(tmp_path: Path) -> None:
    _, store, _, _, bot, entry = _setup_env(tmp_path)
    png_bytes = _make_png_bytes(300, 500)

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=png_bytes, headers={"content-type": "image/png"})

    transport = httpx.MockTransport(_handler)
    pipeline = MediaPipeline(store)
    async with httpx.AsyncClient(transport=transport) as client:
        file_id = await pipeline.upload_character_media(
            bot,
            entry,
            channel_id=-100999888,
            bot_username="KayiArenaBot",
            client=client,
            resolve_dns=False,
        )

    assert file_id == "tg_file_101"
    photo_calls = [c for c in bot.calls if c[0] == "send_photo"]
    assert len(photo_calls) == 1
    uploaded_buf = photo_calls[0][1]["photo"]
    assert isinstance(uploaded_buf, BufferedInputFile)
    with Image.open(BytesIO(uploaded_buf.data)) as img:
        assert img.size == (960, 540)
        assert img.format == "JPEG"

    asset = store.get_media_asset_by_character(entry.character_id)
    assert asset is not None
    assert asset["telegram_file_id"] == "tg_file_101"
    assert asset["upload_status"] == "uploaded"

    # Resolver now hits persistent cache directly without HTTP
    resolver = CharacterMediaResolver(store)
    assert resolver.resolve_media_ref(entry) == "tg_file_101"
    cached_photo = await resolver.resolve_card_photo_async(bot, entry, channel_id=-100999888)
    assert cached_photo == "tg_file_101"
    assert len([c for c in bot.calls if c[0] == "send_photo"]) == 1


@pytest.mark.asyncio
async def test_media_pipeline_handles_403_with_browser_headers_and_telegram_url_fallback(
    tmp_path: Path,
) -> None:
    _, store, _, _, bot, entry = _setup_env(tmp_path)
    png_bytes = _make_png_bytes(300, 300)

    # Case 1: Default UA gets 403, browser fallback UA gets 200
    def _ua_handler(request: httpx.Request) -> httpx.Response:
        if "Mozilla/5.0" in request.headers.get("user-agent", ""):
            return httpx.Response(200, content=png_bytes, headers={"content-type": "image/png"})
        return httpx.Response(403, content=b"Forbidden")

    pipeline = MediaPipeline(store)
    async with httpx.AsyncClient(transport=httpx.MockTransport(_ua_handler)) as client:
        file_id = await pipeline.upload_character_media(
            bot,
            entry,
            channel_id=-100999888,
            bot_username="KayiArenaBot",
            client=client,
            resolve_dns=False,
        )
    assert file_id == "tg_file_101"

    # Case 2: Both HTTP attempts return 403 (datacenter IP block) -> falls back to Telegram URL fetch
    def _always_403(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, content=b"Forbidden")

    async with httpx.AsyncClient(transport=httpx.MockTransport(_always_403)) as client:
        file_id_2 = await pipeline.upload_character_media(
            bot,
            entry,
            channel_id=-100999888,
            bot_username="KayiArenaBot",
            force=True,
            client=client,
            resolve_dns=False,
        )
    assert file_id_2 == "tg_file_102"
    photo_calls = [c for c in bot.calls if c[0] == "send_photo"]
    assert photo_calls[-1][1]["photo"] == entry.image.url_or_ref


@pytest.mark.asyncio
async def test_media_sync_skips_existing_and_deletes_duplicate_channel_messages(
    tmp_path: Path,
) -> None:
    _, store, _, _, bot, entry = _setup_env(tmp_path)
    png_bytes = _make_png_bytes(300, 300)

    def _handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=png_bytes, headers={"content-type": "image/png"})

    pipeline = MediaPipeline(store)
    async with httpx.AsyncClient(transport=httpx.MockTransport(_handler)) as client:
        first_id = await pipeline.upload_character_media(
            bot,
            entry,
            channel_id=-100999888,
            bot_username="KayiArenaBot",
            client=client,
            resolve_dns=False,
        )
    assert first_id == "tg_file_101"

    # Re-sync without force (matching cache_key) -> skipped!
    res_skip = await pipeline.sync_universe_media(
        bot,
        [entry],
        channel_id=-100999888,
        bot_username="KayiArenaBot",
        force=False,
        delay_seconds=0.0,
        resolve_dns=False,
    )
    assert res_skip.skipped == 1
    assert res_skip.uploaded == 0

    # Changed checksum at unchanged URL -> triggers new upload (even with force=False) and deletes old channel message 101
    updated_entry = replace(entry, image=replace(entry.image, checksum="new_checksum_v2"))
    async with httpx.AsyncClient(transport=httpx.MockTransport(_handler)) as client:
        changed_id, changed_err = await pipeline.upload_character_media_detailed(
            bot,
            updated_entry,
            channel_id=-100999888,
            bot_username="KayiArenaBot",
            force=False,
            client=client,
            resolve_dns=False,
        )
    assert changed_err is None
    assert changed_id == "tg_file_102"
    del_calls = [c for c in bot.calls if c[0] == "delete_message"]
    assert len(del_calls) == 1
    assert del_calls[0][1]["message_id"] == 101

    # Force re-upload deletes previous channel message 102
    async with httpx.AsyncClient(transport=httpx.MockTransport(_handler)) as client:
        second_id, _ = await pipeline.upload_character_media_detailed(
            bot,
            updated_entry,
            channel_id=-100999888,
            bot_username="KayiArenaBot",
            force=True,
            client=client,
            resolve_dns=False,
        )
    assert second_id == "tg_file_103"
    del_calls = [c for c in bot.calls if c[0] == "delete_message"]
    assert len(del_calls) == 2
    assert del_calls[1][1]["message_id"] == 102


@pytest.mark.asyncio
async def test_welcome_video_send_and_fallback_and_admin_media_manager(tmp_path: Path) -> None:
    _, store, coordinator, dp, bot, entry = _setup_env(tmp_path)
    now = datetime.now(timezone.utc)

    # 1. Admin opens Media Manager -> Media Status
    upd_media = {
        "update_id": 1001,
        "callback_query": {
            "id": "cb_m1",
            "from": {"id": 1, "is_bot": False, "first_name": "Owner"},
            "chat_instance": "ci1",
            "data": "adm:media",
            "message": {
                "message_id": 10,
                "date": int(now.timestamp()),
                "chat": {"id": 1, "type": "private"},
                "text": "Admin",
            },
        },
    }
    await dp.feed_raw_update(bot, upd_media)
    edits = [c[1]["text"] for c in bot.calls if c[0] == "edit_message_text"]
    assert any("Media Manager" in t for t in edits)

    # 2. Admin sets welcome video via video message
    upd_wvidset = {
        "update_id": 1002,
        "callback_query": {
            "id": "cb_w1",
            "from": {"id": 1, "is_bot": False, "first_name": "Owner"},
            "chat_instance": "ci1",
            "data": "adm:wvidset",
            "message": {
                "message_id": 10,
                "date": int(now.timestamp()),
                "chat": {"id": 1, "type": "private"},
                "text": "Admin",
            },
        },
    }
    await dp.feed_raw_update(bot, upd_wvidset)

    upd_video_msg = {
        "update_id": 1003,
        "message": {
            "message_id": 11,
            "date": int(now.timestamp()),
            "chat": {"id": 1, "type": "private"},
            "from": {"id": 1, "is_bot": False, "first_name": "Owner"},
            "video": {
                "file_id": "BAACAgUAAxkBAA_WELCOME_VID",
                "file_unique_id": "uniq_vid",
                "width": 1280,
                "height": 720,
                "duration": 10,
            },
        },
    }
    await dp.feed_raw_update(bot, upd_video_msg)
    assert coordinator.get_welcome_video_file_id() == "BAACAgUAAxkBAA_WELCOME_VID"
    assert store.get_setting("welcome_video_file_id") == "BAACAgUAAxkBAA_WELCOME_VID"

    # 3. Private /start sends video (preserving audio via send_video)
    upd_start = {
        "update_id": 1004,
        "message": {
            "message_id": 12,
            "date": int(now.timestamp()),
            "chat": {"id": 42, "type": "private"},
            "from": {"id": 42, "is_bot": False, "first_name": "Player"},
            "text": "/start",
        },
    }
    await dp.feed_raw_update(bot, upd_start)
    vid_calls = [c for c in bot.calls if c[0] == "send_video"]
    assert len(vid_calls) == 1
    assert vid_calls[0][1]["video"] == "BAACAgUAAxkBAA_WELCOME_VID"

    # 4. If send_video fails, /start safely falls back to text
    _, _, _, dp2, bot2, _ = _setup_env(tmp_path / "fallback", fail_video=True)
    dp2["coordinator"].set_welcome_video_file_id("BAD_VIDEO_ID")
    await dp2.feed_raw_update(
        bot2,
        {
            "update_id": 1005,
            "message": {
                "message_id": 13,
                "date": int(now.timestamp()),
                "chat": {"id": 42, "type": "private"},
                "from": {"id": 42, "is_bot": False, "first_name": "Player"},
                "text": "/start",
            },
        },
    )
    assert any(c[0] == "send_video" for c in bot2.calls)
    assert any(c[0] == "send_message" and "Welcome to" in c[1]["text"] for c in bot2.calls)


@pytest.mark.asyncio
async def test_admin_manage_characters_filters_profile_and_retry_failed(tmp_path: Path) -> None:
    _, store, coordinator, dp, bot, entry = _setup_env(tmp_path)
    now = datetime.now(timezone.utc)

    # Record one failed media asset
    store.upsert_media_asset(
        media_key=f"{entry.character_id}:{entry.image.url_or_ref}",
        character_id=entry.character_id,
        universe_id=entry.universe_id,
        source_url=entry.image.url_or_ref,
        telegram_file_id="",
        upload_status="failed",
        last_error="HTTP 403",
    )

    # 1. Media Manager shows Retry Failed button
    await dp.feed_raw_update(
        bot,
        {
            "update_id": 2001,
            "callback_query": {
                "id": "cb_mm1",
                "from": {"id": 1, "is_bot": False, "first_name": "Owner"},
                "chat_instance": "ci1",
                "data": "adm:media",
                "message": {
                    "message_id": 20,
                    "date": int(now.timestamp()),
                    "chat": {"id": 1, "type": "private"},
                    "text": "Admin",
                },
            },
        },
    )
    media_edit = [c[1] for c in bot.calls if c[0] == "edit_message_text"][-1]
    assert "Total characters in DB: <b>1</b>" in media_edit["text"]
    flat_cbs = [
        btn.callback_data
        for row in media_edit["reply_markup"].inline_keyboard
        for btn in row
    ]
    assert "adm:mretry" in flat_cbs

    # 2. Manage Characters browser & filter cycling & profile view
    await dp.feed_raw_update(
        bot,
        {
            "update_id": 2002,
            "callback_query": {
                "id": "cb_mc1",
                "from": {"id": 1, "is_bot": False, "first_name": "Owner"},
                "chat_instance": "ci1",
                "data": "adm:chars:naruto:all:0",
                "message": {
                    "message_id": 20,
                    "date": int(now.timestamp()),
                    "chat": {"id": 1, "type": "private"},
                    "text": "Admin",
                },
            },
        },
    )
    chars_edit = [c[1] for c in bot.calls if c[0] == "edit_message_text"][-1]
    assert "Manage Characters — naruto" in chars_edit["text"]
    assert "Naruto Uzumaki" in chars_edit["text"]

    await dp.feed_raw_update(
        bot,
        {
            "update_id": 2003,
            "callback_query": {
                "id": "cb_mc2",
                "from": {"id": 1, "is_bot": False, "first_name": "Owner"},
                "chat_instance": "ci1",
                "data": f"adm:chview:{entry.character_id}",
                "message": {
                    "message_id": 20,
                    "date": int(now.timestamp()),
                    "chat": {"id": 1, "type": "private"},
                    "text": "Admin",
                },
            },
        },
    )
    profile_calls = [c[1] for c in bot.calls if c[0] in {"send_photo", "send_message"}]
    assert any("Role Fits:" in (c.get("caption") or c.get("text") or "") for c in profile_calls)
