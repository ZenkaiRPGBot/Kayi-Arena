"""Character media resolution and Telegram file_id caching (Module 7).

Never auto-promotes technically validated images to identity-verified, and
never lets media resolution failures interrupt drafting gameplay.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.database import CharacterEntry

if TYPE_CHECKING:
    from app.persistence.store import SqliteMatchStore


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
