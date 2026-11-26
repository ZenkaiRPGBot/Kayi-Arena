"""Character media resolution, 960x540 card standardization, and Telegram file_id caching.

Never auto-promotes technically validated images to identity-verified, and
never lets media resolution failures interrupt drafting gameplay.
"""

from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING

from PIL import Image, ImageOps

from app.database import CharacterEntry

if TYPE_CHECKING:
    from app.persistence.store import SqliteMatchStore

_RARITY_BORDER_RGB: dict[str, tuple[int, int, int]] = {
    "Common": (148, 163, 184),
    "Uncommon": (34, 197, 94),
    "Rare": (59, 130, 246),
    "Epic": (168, 85, 247),
    "Legendary": (234, 179, 8),
}


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


class CharacterMediaResolver:
    """Resolves character artwork via persistent Telegram file_id cache or URL."""

    def __init__(self, store: SqliteMatchStore | None = None) -> None:
        self._store = store

    def resolve_media_ref(self, entry: CharacterEntry | None) -> str | None:
        if entry is None:
            return None
        raw_ref = entry.image.url_or_ref.strip()
        if not raw_ref:
            return None
        if self._store is not None:
            cached = self._store.get_media_cache(self._cache_key(entry, raw_ref))
            if cached:
                return cached
        if raw_ref.startswith(("http://", "https://")) or ":" not in raw_ref:
            return raw_ref
        return None

    def record_telegram_file_id(
        self, entry: CharacterEntry | None, telegram_file_id: str | None
    ) -> None:
        if entry is None or not telegram_file_id or self._store is None:
            return
        raw_ref = entry.image.url_or_ref.strip()
        if not raw_ref:
            return
        self._store.save_media_cache(
            self._cache_key(entry, raw_ref),
            telegram_file_id,
            character_id=entry.character_id,
            source_ref=raw_ref,
        )

    @staticmethod
    def _cache_key(entry: CharacterEntry, raw_ref: str) -> str:
        checksum = entry.image.checksum.strip()
        return f"{entry.character_id}:{checksum or raw_ref}"
