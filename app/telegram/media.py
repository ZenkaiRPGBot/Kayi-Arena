"""Character media resolution, SSRF-safe download, 960x540 standardization, and Telegram file_id caching.

Never auto-promotes technically validated images to identity-verified, and
never lets media resolution failures interrupt drafting gameplay.
"""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import logging
import socket
from collections.abc import Sequence
from dataclasses import dataclass, field
from io import BytesIO
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin, urlparse

import httpx
from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramNetworkError,
    TelegramRetryAfter,
)
from aiogram.types import BufferedInputFile
from PIL import Image, ImageOps, UnidentifiedImageError

from app.database import CharacterEntry

if TYPE_CHECKING:
    from app.persistence.store import SqliteMatchStore

logger = logging.getLogger(__name__)

_RARITY_BORDER_RGB: dict[str, tuple[int, int, int]] = {
    "Common": (148, 163, 184),
    "Uncommon": (34, 197, 94),
    "Rare": (59, 130, 246),
    "Epic": (168, 85, 247),
    "Legendary": (234, 179, 8),
}

_BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "ip6-localhost",
        "ip6-loopback",
        "metadata.google.internal",
        "metadata",
    }
)
_MAX_MEDIA_BYTES = 10 * 1024 * 1024
_MAX_REDIRECTS = 3
_DEFAULT_HEADERS = {
    "User-Agent": "KayiArenaMediaBot/1.0",
    "Accept": "*/*",
}
_FALLBACK_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class UnsafeMediaURLError(ValueError):
    """Raised when a media URL fails SSRF or scheme validation."""


class MediaDownloadError(RuntimeError):
    """Raised when downloading or decoding a remote character image fails."""


def _is_global_ip(ip_str: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return bool(
        addr.is_global
        and not addr.is_private
        and not addr.is_loopback
        and not addr.is_link_local
        and not addr.is_multicast
        and not addr.is_reserved
        and not addr.is_unspecified
    )


def validate_media_url(url: str, *, resolve_dns: bool = True) -> str:
    """Validate that a remote image URL is HTTP(S) and does not target private/local networks."""
    cleaned = url.strip()
    parsed = urlparse(cleaned)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise UnsafeMediaURLError(f"Unsupported URL scheme: {parsed.scheme!r}")
    if parsed.username or parsed.password:
        raise UnsafeMediaURLError("Credentials in media URLs are not allowed.")
    host = (parsed.hostname or "").strip().lower().rstrip(".")
    if not host:
        raise UnsafeMediaURLError("Media URL is missing a hostname.")
    if host in _BLOCKED_HOSTNAMES or host.endswith((".local", ".internal", ".localhost")):
        raise UnsafeMediaURLError(f"Blocked internal hostname: {host}")

    try:
        ipaddress.ip_address(host)
    except ValueError:
        is_literal_ip = False
    else:
        is_literal_ip = True

    if is_literal_ip:
        if not _is_global_ip(host):
            raise UnsafeMediaURLError(f"Blocked non-public IP address: {host}")
        return cleaned

    if resolve_dns:
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
        try:
            infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise MediaDownloadError(f"DNS resolution failed for {host}: {exc}") from exc
        resolved_ips = {str(info[4][0]) for info in infos if info[4]}
        if not resolved_ips or any(not _is_global_ip(ip) for ip in resolved_ips):
            raise UnsafeMediaURLError(f"Hostname {host} resolved to non-public IP address.")
    return cleaned


def standardize_card_image(
    raw_bytes: bytes,
    *,
    rarity: str = "Common",
    target_size: tuple[int, int] = (960, 540),
    border_px: int = 8,
) -> bytes:
    """Standardize character artwork onto a 960x540 landscape canvas without stretching."""
    with Image.open(BytesIO(raw_bytes)) as src:
        rgb = src.convert("RGB")
        inner_w = max(1, target_size[0] - 2 * border_px)
        inner_h = max(1, target_size[1] - 2 * border_px)
        padded = ImageOps.pad(
            rgb,
            (inner_w, inner_h),
            method=Image.Resampling.LANCZOS,
            color=(15, 23, 42),
        )
        border_color = _RARITY_BORDER_RGB.get(rarity, (148, 163, 184))
        canvas = Image.new("RGB", target_size, border_color)
        canvas.paste(padded, (border_px, border_px))
        out = BytesIO()
        canvas.save(out, format="JPEG", quality=90, optimize=True)
        return out.getvalue()


@dataclass(slots=True)
class MediaSyncResult:
    total: int = 0
    uploaded: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)
    error_counts: dict[str, int] = field(default_factory=dict)


class MediaPipeline:
    """SSRF-safe image downloader, 960x540 standardizer, and Telegram media channel uploader."""

    def __init__(self, store: SqliteMatchStore | Any | None = None) -> None:
        self._store = store

    async def download_and_prepare(
        self,
        url: str,
        *,
        rarity: str = "Common",
        max_bytes: int = _MAX_MEDIA_BYTES,
        client: httpx.AsyncClient | None = None,
        resolve_dns: bool = True,
    ) -> tuple[bytes, str]:
        current_url = validate_media_url(url, resolve_dns=resolve_dns)
        owns_client = client is None
        if client is None:
            client = httpx.AsyncClient(
                timeout=httpx.Timeout(15.0, connect=8.0),
                headers=_DEFAULT_HEADERS,
            )
        try:
            response: httpx.Response | None = None
            for _ in range(_MAX_REDIRECTS + 1):
                resp = await client.get(
                    current_url,
                    follow_redirects=False,
                    headers=_DEFAULT_HEADERS,
                )
                if resp.status_code == 403:
                    retry_headers = dict(_FALLBACK_HEADERS)
                    host = (urlparse(current_url).hostname or "").lower()
                    if "wikia.nocookie.net" in host or "fandom.com" in host:
                        retry_headers["Referer"] = "https://naruto.fandom.com/"
                    resp = await client.get(
                        current_url,
                        follow_redirects=False,
                        headers=retry_headers,
                    )
                if resp.status_code in {301, 302, 303, 307, 308}:
                    location = resp.headers.get("location", "").strip()
                    if not location:
                        raise MediaDownloadError("Redirect missing Location header.")
                    current_url = validate_media_url(
                        urljoin(current_url, location),
                        resolve_dns=resolve_dns,
                    )
                    continue
                response = resp
                break
            if response is None:
                raise MediaDownloadError("Too many redirects while downloading media.")
            if response.status_code >= 400:
                raise MediaDownloadError(f"HTTP {response.status_code} downloading media.")
            content_type = response.headers.get("content-type", "").lower()
            if content_type and not content_type.startswith("image/"):
                raise MediaDownloadError(f"Unexpected content-type: {content_type}")
            raw_bytes = response.content
            if not raw_bytes:
                raise MediaDownloadError("Downloaded empty media payload.")
            if len(raw_bytes) > max_bytes:
                raise MediaDownloadError(f"Media exceeds {max_bytes} bytes limit.")
        except httpx.HTTPError as exc:
            raise MediaDownloadError(f"HTTP download error ({type(exc).__name__}): {exc}") from exc
        finally:
            if owns_client:
                await client.aclose()

        try:
            with Image.open(BytesIO(raw_bytes)) as img:
                img.verify()
            standardized = standardize_card_image(raw_bytes, rarity=rarity)
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise MediaDownloadError(f"Invalid image payload: {exc}") from exc

        digest = hashlib.sha256(standardized).hexdigest()
        return standardized, digest

    async def upload_character_media_detailed(
        self,
        bot: Bot,
        entry: CharacterEntry,
        *,
        channel_id: int | str,
        bot_username: str = "",
        force: bool = False,
        client: httpx.AsyncClient | None = None,
        resolve_dns: bool = True,
    ) -> tuple[str | None, str | None]:
        raw_ref = entry.image.url_or_ref.strip()
        if not raw_ref:
            return None, "missing source URL"
        cache_key = CharacterMediaResolver._cache_key(entry, raw_ref)
        if not force and self._store is not None:
            existing = self._store.get_media_cache(cache_key)
            if existing:
                return existing, None

        if not raw_ref.startswith(("http://", "https://")) and ":" not in raw_ref:
            if self._store is not None:
                self._store.upsert_media_asset(
                    media_key=cache_key,
                    character_id=entry.character_id,
                    universe_id=entry.universe_id,
                    source_url=raw_ref,
                    telegram_file_id=raw_ref,
                    channel_id=str(channel_id),
                    bot_username=bot_username,
                    verification_status=entry.image.status.value,
                    upload_status="uploaded",
                    attribution=entry.image.source_ref,
                    last_error="",
                )
            return raw_ref, None

        caption = (
            f"Kayi Arena Media | {entry.name} ({entry.character_id})\n"
            f"Universe: {entry.universe_id} | Rarity: {entry.rarity}"
        )
        file_obj: Any = None
        digest = entry.image.checksum or ""
        try:
            jpg_bytes, digest = await self.download_and_prepare(
                raw_ref,
                rarity=entry.rarity,
                client=client,
                resolve_dns=resolve_dns,
            )
            file_obj = BufferedInputFile(jpg_bytes, filename=f"{entry.character_id}.jpg")
        except UnsafeMediaURLError as exc:
            err_msg = str(exc)
            logger.warning("Media URL rejected for %s: %s", entry.character_id, err_msg)
            if self._store is not None:
                self._store.upsert_media_asset(
                    media_key=cache_key,
                    character_id=entry.character_id,
                    universe_id=entry.universe_id,
                    source_url=raw_ref,
                    telegram_file_id="",
                    channel_id=str(channel_id),
                    bot_username=bot_username,
                    verification_status=entry.image.status.value,
                    upload_status="failed",
                    attribution=entry.image.source_ref,
                    last_error=err_msg,
                )
            return None, err_msg
        except MediaDownloadError as exc:
            err_msg = str(exc)
            if "HTTP 403" in err_msg:
                # Datacenter IP blocked by CDN: let Telegram fetch the SSRF-validated URL directly
                try:
                    file_obj = validate_media_url(raw_ref, resolve_dns=resolve_dns)
                    logger.info(
                        "HTTP 403 downloading %s locally; falling back to Telegram URL fetch",
                        entry.character_id,
                    )
                except (UnsafeMediaURLError, MediaDownloadError) as val_exc:
                    err_msg = str(val_exc)
                    logger.warning("Fallback URL validation failed for %s: %s", entry.character_id, err_msg)
            if file_obj is None:
                logger.warning("Media download failed for %s: %s", entry.character_id, err_msg)
                if self._store is not None:
                    self._store.upsert_media_asset(
                        media_key=cache_key,
                        character_id=entry.character_id,
                        universe_id=entry.universe_id,
                        source_url=raw_ref,
                        telegram_file_id="",
                        channel_id=str(channel_id),
                        bot_username=bot_username,
                        verification_status=entry.image.status.value,
                        upload_status="failed",
                        attribution=entry.image.source_ref,
                        last_error=err_msg,
                    )
                return None, err_msg

        msg = None
        last_err = "Telegram upload failed"
        for attempt in range(2):
            try:
                msg = await bot.send_photo(chat_id=channel_id, photo=file_obj, caption=caption)
                break
            except TelegramRetryAfter as exc:
                last_err = f"TelegramRetryAfter ({exc.retry_after}s)"
                if attempt == 0:
                    await asyncio.sleep(min(float(exc.retry_after) + 0.5, 30.0))
                    continue
                logger.warning("TelegramRetryAfter exhausted for %s", entry.character_id)
            except (TelegramAPIError, TelegramBadRequest, TelegramNetworkError, OSError) as exc:
                last_err = f"{type(exc).__name__}: {exc}"
                logger.warning("Media channel upload failed for %s: %s", entry.character_id, last_err)
                break

        if msg is None or not getattr(msg, "photo", None):
            if self._store is not None:
                self._store.upsert_media_asset(
                    media_key=cache_key,
                    character_id=entry.character_id,
                    universe_id=entry.universe_id,
                    source_url=raw_ref,
                    telegram_file_id="",
                    channel_id=str(channel_id),
                    bot_username=bot_username,
                    image_hash=digest,
                    verification_status=entry.image.status.value,
                    upload_status="failed",
                    attribution=entry.image.source_ref,
                    last_error=last_err,
                )
            return None, last_err

        best_photo = msg.photo[-1]
        file_id = str(best_photo.file_id)
        file_unique_id = str(getattr(best_photo, "file_unique_id", "") or "")
        if self._store is not None:
            self._store.upsert_media_asset(
                media_key=cache_key,
                character_id=entry.character_id,
                universe_id=entry.universe_id,
                source_url=raw_ref,
                telegram_file_id=file_id,
                telegram_file_unique_id=file_unique_id,
                channel_id=str(channel_id),
                channel_message_id=int(msg.message_id),
                bot_username=bot_username,
                image_hash=digest,
                verification_status=entry.image.status.value,
                upload_status="uploaded",
                attribution=entry.image.source_ref,
                last_error="",
            )
        return file_id, None

    async def upload_character_media(
        self,
        bot: Bot,
        entry: CharacterEntry,
        *,
        channel_id: int | str,
        bot_username: str = "",
        force: bool = False,
        client: httpx.AsyncClient | None = None,
        resolve_dns: bool = True,
    ) -> str | None:
        file_id, _ = await self.upload_character_media_detailed(
            bot,
            entry,
            channel_id=channel_id,
            bot_username=bot_username,
            force=force,
            client=client,
            resolve_dns=resolve_dns,
        )
        return file_id

    async def sync_universe_media(
        self,
        bot: Bot,
        entries: Sequence[CharacterEntry],
        *,
        channel_id: int | str,
        bot_username: str = "",
        force: bool = False,
        only_failed: bool = False,
        delay_seconds: float = 0.25,
        resolve_dns: bool = True,
    ) -> MediaSyncResult:
        result = MediaSyncResult(total=len(entries))

        # Preflight check on media channel accessibility
        if hasattr(bot, "get_chat"):
            try:
                await bot.get_chat(channel_id)
            except Exception as exc:
                reason = f"Media channel inaccessible ({type(exc).__name__}): {exc}"
                result.failed = len(entries)
                result.errors.append(reason)
                result.error_counts[reason[:80]] = len(entries)
                return result

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(15.0, connect=8.0),
            headers=_DEFAULT_HEADERS,
        ) as client:
            for entry in entries:
                raw_ref = entry.image.url_or_ref.strip()
                if not raw_ref:
                    result.failed += 1
                    reason = "missing source URL"
                    result.errors.append(f"{entry.character_id}: {reason}")
                    result.error_counts[reason] = result.error_counts.get(reason, 0) + 1
                    continue

                cache_key = CharacterMediaResolver._cache_key(entry, raw_ref)
                if not force and self._store is not None and self._store.get_media_cache(cache_key):
                    result.skipped += 1
                    continue

                if only_failed and self._store is not None:
                    asset = self._store.get_media_asset_by_character(entry.character_id)
                    if not asset or asset.get("upload_status") != "failed":
                        result.skipped += 1
                        continue

                file_id, err_reason = await self.upload_character_media_detailed(
                    bot,
                    entry,
                    channel_id=channel_id,
                    bot_username=bot_username,
                    force=force,
                    client=client,
                    resolve_dns=resolve_dns,
                )
                if file_id:
                    result.uploaded += 1
                else:
                    result.failed += 1
                    msg = err_reason or "upload failed"
                    result.errors.append(f"{entry.character_id}: {msg}")
                    bucket = msg.split("\n")[0][:70]
                    result.error_counts[bucket] = result.error_counts.get(bucket, 0) + 1
                if delay_seconds > 0:
                    await asyncio.sleep(delay_seconds)
        return result


class CharacterMediaResolver:
    """Resolves character artwork via persistent Telegram file_id cache, media channel, or SSRF-safe fallback."""

    def __init__(self, store: SqliteMatchStore | Any | None = None) -> None:
        self._store = store
        self._pipeline = MediaPipeline(store)
        self._memory_cache: dict[str, str] = {}

    def resolve_media_ref(self, entry: CharacterEntry | None) -> str | None:
        if entry is None:
            return None
        raw_ref = entry.image.url_or_ref.strip()
        if not raw_ref:
            return None
        cache_key = self._cache_key(entry, raw_ref)
        mem = self._memory_cache.get(cache_key)
        if mem:
            return mem
        if self._store is not None:
            cached = self._store.get_media_cache(cache_key)
            if cached:
                self._memory_cache[cache_key] = cached
                return cached
            asset = self._store.get_media_asset_by_character(entry.character_id)
            if asset and asset.get("upload_status") == "uploaded" and asset.get("telegram_file_id"):
                fid = str(asset["telegram_file_id"])
                self._memory_cache[cache_key] = fid
                return fid
        if raw_ref.startswith(("http://", "https://")):
            try:
                return validate_media_url(raw_ref, resolve_dns=False)
            except UnsafeMediaURLError:
                return None
        if ":" not in raw_ref:
            return raw_ref
        return None

    async def resolve_card_photo_async(
        self,
        bot: Bot,
        entry: CharacterEntry | None,
        *,
        channel_id: int | str = 0,
        bot_username: str = "",
        resolve_dns: bool = True,
    ) -> str | BufferedInputFile | None:
        """Resolve a character card photo with fallback order:
        1. Cached Telegram file_id
        2. Download + standardize + upload to MEDIA_CHANNEL_ID (if configured)
        3. Download + standardize to BufferedInputFile (direct upload fallback)
        4. SSRF-validated URL or None
        """
        if entry is None:
            return None
        raw_ref = entry.image.url_or_ref.strip()
        if not raw_ref:
            return None

        cache_key = self._cache_key(entry, raw_ref)
        mem = self._memory_cache.get(cache_key)
        if mem:
            return mem
        if self._store is not None:
            cached = self._store.get_media_cache(cache_key)
            if cached:
                self._memory_cache[cache_key] = cached
                return cached
            asset = self._store.get_media_asset_by_character(entry.character_id)
            if asset and asset.get("upload_status") == "uploaded" and asset.get("telegram_file_id"):
                fid = str(asset["telegram_file_id"])
                self._memory_cache[cache_key] = fid
                return fid

        if not raw_ref.startswith(("http://", "https://")):
            return raw_ref if ":" not in raw_ref else None

        if channel_id:
            uploaded_id = await self._pipeline.upload_character_media(
                bot,
                entry,
                channel_id=channel_id,
                bot_username=bot_username,
                resolve_dns=resolve_dns,
            )
            if uploaded_id:
                self._memory_cache[cache_key] = uploaded_id
                return uploaded_id

        try:
            jpg_bytes, _ = await self._pipeline.download_and_prepare(
                raw_ref,
                rarity=entry.rarity,
                resolve_dns=resolve_dns,
            )
            return BufferedInputFile(jpg_bytes, filename=f"{entry.character_id}.jpg")
        except (UnsafeMediaURLError, MediaDownloadError) as exc:
            logger.warning("On-the-fly image prep failed for %s: %s", entry.character_id, exc)
            try:
                return validate_media_url(raw_ref, resolve_dns=False)
            except UnsafeMediaURLError:
                return None

    def record_telegram_file_id(
        self, entry: CharacterEntry | None, telegram_file_id: str | None
    ) -> None:
        if entry is None or not telegram_file_id:
            return
        raw_ref = entry.image.url_or_ref.strip()
        if not raw_ref:
            return
        cache_key = self._cache_key(entry, raw_ref)
        self._memory_cache[cache_key] = telegram_file_id
        if self._store is None:
            return
        self._store.upsert_media_asset(
            media_key=cache_key,
            character_id=entry.character_id,
            universe_id=entry.universe_id,
            source_url=raw_ref,
            telegram_file_id=telegram_file_id,
            verification_status=entry.image.status.value,
            upload_status="uploaded",
            attribution=entry.image.source_ref,
            last_error="",
        )

    @staticmethod
    def _cache_key(entry: CharacterEntry, raw_ref: str) -> str:
        checksum = entry.image.checksum.strip()
        return f"{entry.character_id}:{checksum or raw_ref}"
