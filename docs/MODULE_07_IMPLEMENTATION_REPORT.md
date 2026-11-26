# Module 7 — Durable Persistence & Recovery Implementation Report

## 1. Summary
Module 7 adds durable SQLite persistence, versioned schema migrations, atomic state transitions, restart-safe wall-clock deadlines, startup recovery, resilient `/game` message reconstruction, historical match records, and persistent character media caching.

## 2. Implemented Components
- **Persistence Layer (`app/persistence/`):**
  - [models.py](file:///D:/KayiBots/Kayi%20Arena/app/persistence/models.py): `HistoricalMatchRecord`, `StartupRecoveryReport`, `PersistenceError`, `CorruptStateError`, and JSON serializers for `TimeoutPolicy`, `MatchOutcomeSummary`, and `MatchResolutionSuccess`.
  - [store.py](file:///D:/KayiBots/Kayi%20Arena/app/persistence/store.py): `SqliteMatchStore` (`SCHEMA_VERSION = 1`, `schema_migrations`, `WAL`, `busy_timeout=5000`, `BEGIN IMMEDIATE`, `challenges`, `matches`, `active_player_locks`, `player_profiles`, `match_history`, `media_cache`, and `backup_to`).
- **Match Lifecycle & Startup Recovery (`app/matches/service.py`):**
  - Integrated `SqliteMatchStore` into all challenge & match mutations (committing to SQLite before updating in-memory state or Telegram UI).
  - Switched default `MatchManager` clock to `time.time` for restart-safe deadlines while keeping `clock` injection for deterministic tests.
  - Added `replace_message_references` and `recover_from_store`.
- **Telegram Recovery & Media (`app/telegram/`):**
  - [media.py](file:///D:/KayiBots/Kayi%20Arena/app/telegram/media.py): `CharacterMediaResolver` with persistent Telegram `file_id` cache.
  - [service.py](file:///D:/KayiBots/Kayi%20Arena/app/telegram/service.py): `recover_on_startup()` and serialized, non-duplicating `recover_game_ui()`.
  - [restart_notify.py](file:///D:/KayiBots/Kayi%20Arena/app/telegram/restart_notify.py): Accurate, non-sensitive `StartupRecoveryReport` summary in startup alerts.
  - [seed_synthetic_dev.py](file:///D:/KayiBots/Kayi%20Arena/scripts/seed_synthetic_dev.py): Isolated synthetic dataset seeder for local Telegram smoke testing.
- **Deployment & HTTP Health Server (`app/telegram/web.py`, `app/main.py`, `render.yaml`, `.env.example`):**
  - Added lightweight `aiohttp` HTTP server (`/` and `/health`) bound to `0.0.0.0:$PORT` alongside Telegram polling, with graceful shutdown (`runner.cleanup()`, `dp.stop_polling()`, `coordinator.shutdown()`, `store.close()`, `db.close()`).
  - Updated `render.yaml` to free Render Web Service (`type: web`, `plan: free`, `healthCheckPath: /health`, no `maxShutdownDelaySeconds`) and documented ephemeral filesystem limitations vs. durable production storage (paid persistent disk or external Postgres).

## 3. Downtime Policy Note (Owner Confirmation)
- When a turn expires while the bot is offline, startup recovery offers the opponent a fresh 60s inactivity claim window rather than fabricating an automatic victory.
- When an already-open 60s inactivity claim window expires during downtime, startup recovery abandons the match (`MUTUAL_INACTIVITY_ABANDONMENT`, no winner, `affects_rating=False`).

## 4. Verification Results
- **Combined Regression Suite:** `C:\Users\2024\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests -v`
- **Result:** **`110 passed in 321.92s (0:05:21)`** (0 failed, 0 skipped), covering:
  - Module 7 persistence & recovery ([test_persistence_recovery.py](file:///D:/KayiBots/Kayi%20Arena/tests/test_persistence_recovery.py): 6 tests)
  - Module 6 Telegram UI & Rarity v0.2 (11 tests)
  - OpenCode character content & image tooling (13 tests)
  - Modules 1–5 including the 100,000-draft simulation (80 tests)
