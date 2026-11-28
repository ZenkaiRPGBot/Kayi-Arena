# Kayi Arena — Player Profile 2.0 Implementation Report

**Branch:** `main`  
**Scope:** Dynamic Player Card V2 (1900×800 PNG, 19:8), Player Statistics, Universe Selection, Match History, Historical Match Details, Historical Battle Breakdown, Session & Callback Security, SQLite/MongoDB Persistence, Regression Suite & CodeRabbit Review.

---

## 1. Repository Inspection Summary
- Inspected `AGENTS.md`, `app/persistence/`, `app/telegram/`, and `tests/`.
- Preserved all existing Arena UI 2.0, UI 2.1, Arena Logs 2.0, Naruto Batch 005 content, and unrelated workspace files.
- Verified existing `HistoricalMatchRecord`, `SqliteMatchStore`, `MongoMatchStore`, `MatchCoordinator`, and callback encoding (`encode_cb` / `decode_cb` with Telegram's 64-byte callback limit).

## 2. Prototype & Asset Integration
- Extracted `kayi_player_card_prototype_v2.zip` (superseding the original 1900×600 prototype) and installed the approved raster layers into `app/telegram/assets/profile/`:
  - `background.png`
  - `emblem.png`
  - `avatar_frame.png`
- Installed official SIL Open Font License 1.1 Inter Display fonts into `app/telegram/assets/fonts/`:
  - `InterDisplay-BlackItalic.otf`
  - `InterDisplay-BoldItalic.otf`
  - `OFL.txt`

## 3. Player Card Renderer Implementation
- Implemented `app/telegram/profile_card.py`:
  - `CARD_WIDTH = 1900`, `CARD_HEIGHT = 800` (19:8, `RENDERER_VERSION = "2.1.0"`, `RGBA` → `PNG`).
  - `render_player_card_png(*, name, wins, losses, draws, avatar_bytes=None) -> bytes`.
  - `render_player_card_async(...)` offloads CPU-bound Pillow compositing via `asyncio.to_thread`.
  - Static layer caching (`_STATIC_CACHE`) caches castle-biased cropped background (`centering=(0.70, 0.5)`), emblem (`160×160`), and avatar frame (`480×480`), with `82 px` `KAYI ARENA` branding typography.
  - Cross-platform font resolution (`resolve_font_paths`) preferring bundled `InterDisplay-BlackItalic.otf` / `InterDisplay-BoldItalic.otf` with Windows/Linux system font fallbacks.
  - Text normalization (`NFKC` for Unicode Mathematical Bold/Italic `U+1D400`–`U+1D7FF`), automatic font downscaling (`max_size` down to `min_size=22`), and clean `"…"` truncation for long names.
  - EXIF-transposed circular avatar cropping (`_prepare_avatar_layer`, `diameter=348`) with graceful silhouette fallback when `avatar_bytes` is missing or corrupt.
  - `fetch_telegram_avatar_bytes` fetches the target user's Telegram profile photo with a 3-second timeout and falls back cleanly on network/API failure.
  - Measured local render latency (`render_player_card_png` V2):
    - Cold render (`OBITO`, 32W/14L/2D): `6373.9 ms`, `1,897,490` bytes.
    - Warm render (`Kiyomi`, 75W/19L/4D): `3558.6 ms`, `1,899,132` bytes.
    - Bounded LRU `PlayerCardCache` avoids re-rendering on cache hits.

## 4. Card Caching Strategy
- Implemented `PlayerCardCache` (thread-safe bounded LRU) keyed by `(RENDERER_VERSION, player_id, name, wins, losses, draws, avatar_hash)`.
- Any change to display name, authoritative Ranked wins/losses/draws, or avatar bytes produces a distinct cache key and automatically invalidates stale entries.

## 5. Text Fallback Strategy
- Implemented `render_profile_text_fallback` in `app/telegram/texts.py`.
- Used automatically if PNG rendering or `send_photo` fails, ensuring `/profile` still delivers the Ranked summary and interactive navigation keyboard without crashing.

## 6. Statistics Calculation & Consistency
- Implemented `COUNTED_HISTORY_STATUSES`, `PlayerStatsSummary`, and `summarize_player_records` in `app/persistence/models.py`.
- Implemented matching `compute_player_statistics`, `query_player_history`, `list_player_history_universes`, `get_match_duration_seconds`, and `get_player_display_names` on both `SqliteMatchStore` (`app/persistence/store.py`) and `MongoMatchStore` (`app/persistence/mongo_store.py`).
- Excluded non-counted lifecycle outcomes (e.g., `abandoned`, `cancelled`, `administrative`) consistently from both Player Card totals, Player Statistics, and Match History.
- Ranked Player Card totals and Ranked `All Universes` statistics read from the exact same `compute_player_statistics(..., game_mode="ranked", universe_id=None)` path.

## 7. Player Statistics Interface
- Implemented `render_profile_statistics` in `app/telegram/texts.py` and `build_profile_stats_keyboard` in `app/telegram/keyboards.py`.
- Displays target player identity, Mode (`Ranked` / `Friendly`), Universe filter (`All Universes` or specific universe), Battles Played, Victories, Defeats, Draws, Win Rate, Highest Team Score (`/700`), and Average Team Score (`/700`).

## 8. Universe Selection Interface
- Implemented `render_profile_universe_selection` in `app/telegram/texts.py`, `build_profile_universe_keyboard` in `app/telegram/keyboards.py`, and `MatchCoordinator.profile_universes` in `app/telegram/service.py`.
- Supports `All Universes`, active eligible universes, and universes referenced in the player's historical records (including graceful fallback via `SimpleNamespace` if a universe is no longer in `db`).
- Paginated navigation (`up` callback) and 64-byte-safe universe selection callbacks (`us` with direct `universe_id` for short IDs and `#<index>` fallback for long IDs).

## 9. Match History Interface
- Implemented `render_profile_history` in `app/telegram/texts.py` and `build_profile_history_keyboard` in `app/telegram/keyboards.py`.
- Deterministic ordering: `completed_at DESC, match_id DESC` in both SQLite and MongoDB.
- Displays small-caps numbered entries (`₁`–`₅` via `to_small_caps_digits`), opponent name, outcome status, score/termination indicator (`f"{wins_p}-{wins_o}"`, `ꜰᴏʀꜰᴇɪᴛ`, `ᴛɪᴍᴇᴏᴜᴛ`), universe, and timestamp.
- Supports `/history` entry directly into Match History (and `/profile` entry into the Player Card).

## 10. Historical Match Details Interface
- Implemented `render_historical_match_details` in `app/telegram/texts.py` and `build_historical_match_keyboard` in `app/telegram/keyboards.py`.
- Preserves full HTML structure within Telegram's 4096-character limit by bounding character names before escaping/wrapping and trimming whole lines if needed.
- Conditionally displays `[ 📊 Battle Breakdown ]` only when `rec.outcome.resolution` is present (e.g., hidden for forfeits/inactivity without draft resolution).

## 11. Historical Battle Breakdown Interface
- Implemented `render_historical_battle_breakdown` in `app/telegram/texts.py` and `build_historical_breakdown_keyboard` in `app/telegram/keyboards.py`.
- Displays per-role Power / Role Fit / Score for both players, role winners, and team totals directly from the immutable `HistoricalMatchRecord` snapshot.

## 12. Immutability Verification
- Verified in `tests/test_player_profile_2_0.py`: after mutating character evaluations and publishing a new dataset (`naruto-v2`), previously recorded `HistoricalMatchRecord` details and battle breakdowns remain unchanged.

## 13. Keyboard & Colored Button Compliance
- All Profile 2.0 keyboards (`build_profile_card_keyboard`, `build_profile_stats_keyboard`, `build_profile_universe_keyboard`, `build_profile_history_keyboard`, `build_historical_match_keyboard`, `build_historical_breakdown_keyboard`) use the repository's `_btn(...)` helper with `STYLE_PRIMARY` / `STYLE_DANGER` / neutral button styles and `encode_cb(...)` within Telegram's 64-byte callback limit.

## 14. Interface Lifecycle & Navigation Security
- Implemented `ProfileSession`, `open_profile_session`, and `handle_profile_action` in `app/telegram/service.py`, plus `ka:pf:<sid>:<rev>:<subaction>[:<arg>]` routing in `app/telegram/handlers/callbacks.py`.
- Enforces:
  - Per-session `asyncio.Lock` (`_profile_lock`) with in-lock re-validation of `closed`, `chat_id`, `message_id`, and `expected_revision`.
  - Requester-only navigation (`user_id == session.requester_id`).
  - Controlled photo ↔ text transitions (e.g., Card photo → Stats text → Card photo) and clean message deletion/markup stripping on Close (`cl`).
  - Updated `/profile` and `/history` commands in `app/telegram/handlers/commands.py` (including reply-to targeting).

## 15. Database Schema & Query Changes
- `app/persistence/models.py`: added `COUNTED_HISTORY_STATUSES`, `PlayerStatsSummary`, `summarize_player_records`.
- `app/persistence/store.py`: added `query_player_history`, `compute_player_statistics`, `list_player_history_universes`, `get_match_duration_seconds`, `get_player_display_names` on `SqliteMatchStore`.
- `app/persistence/mongo_store.py`: added matching implementations and supporting indexes on `MongoMatchStore`.

## 16. Automated Test Results
- Executed full regression suite after final edits:
  - Command: `C:\Users\2024\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests -v --tb=short`
  - Result: **231 passed in 250.57s (0:04:10)**, 0 failed, 0 skipped.
  - Includes `tests/test_player_profile_2_0.py` (3/3 passed), `tests/test_telegram_ui.py` (14/14 passed), and `tests/test_mongo_and_migration.py` (6/6 passed).

## 17. CodeRabbit Review Results
- Executed `coderabbit review --agent --uncommitted` on `main`.
- Resolved all 4 minor findings reported by CodeRabbit:
  1. `app/telegram/service.py` & `app/telegram/handlers/callbacks.py`: re-validate `expected_revision`, `chat_id`, and `message_id` inside `_profile_lock`.
  2. `app/telegram/texts.py`: bound character display names prior to HTML wrapping and avoid splitting HTML tags on length clamping in `render_historical_match_details`.
  3. `app/telegram/service.py`: replace incomplete `Universe(...)` fallback in `profile_universes` with `SimpleNamespace(universe_id=uid, name=...)`.
  4. `app/telegram/keyboards.py` & `app/telegram/service.py`: add `#<index>` callback fallback in `build_profile_universe_keyboard` / `handle_profile_action` so long `universe_id` values stay within Telegram's 64-byte callback-data limit.

## 18. Deployment & Live Telegram Verification
- Live Render / Telegram bot deployment verification has **not** been executed in this session (local workspace & automated test suite only). Live `/profile` and `/history` checks should be run after pushing to `origin/main` and deploying.

## 19. Files Changed / Added
- Added:
  - `app/telegram/assets/profile/background.png`
  - `app/telegram/assets/profile/emblem.png`
  - `app/telegram/assets/profile/avatar_frame.png`
  - `app/telegram/assets/fonts/InterDisplay-BlackItalic.otf`
  - `app/telegram/assets/fonts/InterDisplay-BoldItalic.otf`
  - `app/telegram/assets/fonts/OFL.txt`
  - `app/telegram/profile_card.py`
  - `tests/test_player_profile_2_0.py`
  - `docs/PLAYER_PROFILE_2.0_REPORT.md`
- Modified:
  - `app/persistence/models.py`
  - `app/persistence/mongo_store.py`
  - `app/persistence/store.py`
  - `app/telegram/constants.py`
  - `app/telegram/handlers/callbacks.py`
  - `app/telegram/handlers/commands.py`
  - `app/telegram/keyboards.py`
  - `app/telegram/service.py`
  - `app/telegram/texts.py`
  - `tests/test_telegram_ui.py`

## 20. Remaining Risks or Edge Cases
- Warm uncached Pillow V2 rendering takes ~3.6 seconds per card on this machine; `PlayerCardCache` mitigates repeat renders, and `render_player_card_async` keeps the asyncio event loop responsive.
- Live Telegram Bot API `getUserProfilePhotos` / `send_photo` latency and Render container memory should be observed on first production rollout.

## 21. Deferred Features Confirmed Excluded
- Confirmed excluded per specification: currencies, XP/levels, rank badges/tiers, cosmetics, and achievements.

## 22. Final Readiness Assessment
- **Code & Automated Tests:** Ready (`231 passed`, `0 failed`, `0 skipped`, CodeRabbit findings resolved).
- **Production Rollout:** Pending `git push origin main` and Render deployment verification.
