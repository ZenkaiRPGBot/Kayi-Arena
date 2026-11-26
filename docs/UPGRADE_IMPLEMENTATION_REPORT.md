# Kayi Arena — Infrastructure, Performance & UX Upgrade Report

## 1. Completed Phases & Summary

1. **Phase 1 — Live Diagnostics & Character Image Root-Cause Fix (`1315ad9`):**
   - Diagnosed why character images were not displayed in live Telegram matches:
     1. When `CARD_BACK_REF` was unset, `start_match_ui` sent the Awaiting-Shuffle card as a text message (`card_is_photo=False`). On Shuffle, `edit_card_message_safe` stayed on `edit_message_text_safe` and ignored `photo`.
     2. External `static.wikia.nocookie.net` URLs frequently return `webp` or fail Telegram server-side URL fetches.
   - Added `replace_text_with_photo_card_safe` in `app/telegram/safe_api.py` and wired `sync_match_ui` in `app/telegram/service.py` to upgrade text cards into photo cards and persist the new `card` `MessageReference`.

2. **Phase 2 — Beginner-Friendly `/help` Redesign (`1315ad9`):**
   - Redesigned `_HELP_TOPICS` (`app/telegram/texts.py`) and `build_help_keyboard` (`app/telegram/keyboards.py`) into `How to Play`, `The Seven Roles`, `Character Rarity`, `Battle Rules`, `Advanced Scoring`, and `Commands` without altering gameplay layouts.

3. **Phase 3 — Automated Telegram Media Pipeline (`16f8a11`):**
   - Bumped `SqliteMatchStore` to `SCHEMA_VERSION = 3` (`app/persistence/store.py`) with the `media_assets` table.
   - Added `validate_media_url` (SSRF protection blocking localhost, private/loopback/link-local/reserved IPs, credentials, non-HTTP(S) schemes, and unsafe redirects), `MediaPipeline` (Pillow `960x540` JPEG standardization, SHA-256 hashing, `TelegramRetryAfter` handling, `MEDIA_CHANNEL_ID` upload + `file_id` caching), and `CharacterMediaResolver.resolve_card_photo_async` in `app/telegram/media.py`.

4. **Phase 4 & 5 — `/admin` Media Manager & Welcome Video (`16f8a11`):**
   - Added `/admin` Media Manager (`Sync Images`, `Upload Missing`, `Review Images`, `Replace Image` via Telegram photo or SSRF-checked URL, `Media Status`) and Welcome Video management (`adm:wvid`, `adm:wvidset`, `adm:wvidclr`) in `app/telegram/handlers/admin.py`.
   - Updated private `/start` in `app/telegram/handlers/commands.py` to send `bot.send_video` (preserving audio) via `send_video_or_text_safe` with automatic fallback to text on failure.

5. **Phase 6 — Optional MongoDB Atlas Backend & Migration (`592ff28`):**
   - Added `MongoMatchStore` (`app/persistence/mongo_store.py`), `create_match_store(config)` (`app/persistence/__init__.py`), and `migrate_sqlite_to_mongo(..., dry_run=True|False)` (`app/persistence/migrate.py`), keeping SQLite as the default (`DB_BACKEND=sqlite`).
   - Documented Atlas M0 (512 MB) capacity and zero-binary media storage in `docs/MONGODB_ATLAS_STORAGE_REPORT.md`.

6. **Phase 7 & 8 — Performance, `/ping`, Reliability & Security:**
   - Added immutable manifest & O(1) record caching (with SQLite `content_hash` verification preserved) in `CharacterDatabase` (`app/database/repository.py`).
   - Added rolling request latency tracking (`UpdateDedupMiddleware` -> `ArenaTelegramCoordinator`) and upgraded `/ping` (`app/telegram/handlers/commands.py`) to report measured app processing, DB round-trip, Telegram `get_me` latency, and rolling P50/P95/P99.
   - Added DB readiness verification (`readiness_check`) to `/health` (`app/telegram/web.py`, `app/main.py`) returning HTTP 503 `"degraded"` on DB failure while preserving `X-Telegram-Bot-Api-Secret-Token` webhook enforcement.

## 2. Verification Scope & Limitations

- All automated tests run against local SQLite (`:memory:` / `tmp_path`), mocked Telegram `Bot` recorders, `httpx.MockTransport`, `aiohttp` `TestClient`, and an in-memory fake MongoDB database.
- Live MongoDB Atlas M0 network connectivity, live Render deployment logs, and live Telegram `MEDIA_CHANNEL_ID` / `send_video` API calls were **not** executed in this offline/sandboxed environment and should be verified on Render once environment variables are configured.

## 3. Render Environment Variables Checklist

- `MEDIA_CHANNEL_ID`: Numeric ID of the private Telegram channel (bot must be an admin with post permissions).
- `WELCOME_VIDEO_FILE_ID`: Optional initial Telegram video `file_id` (or set live via `/admin` -> `Welcome Video`).
- `DB_BACKEND`: `sqlite` (default) or `mongodb`.
- `MONGODB_URI` / `MONGODB_DATABASE`: Set when `DB_BACKEND=mongodb`.
- `WEBHOOK_SECRET`: Recommended secret token for `/telegram/webhook`.
