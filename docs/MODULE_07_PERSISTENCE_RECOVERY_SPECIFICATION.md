# Module 7 — Durable Persistence & Recovery Specification

## 1. Overview
Module 7 replaces ephemeral in-memory challenge and match storage with an atomic SQLite persistence layer (`app/persistence/store.py`, `SqliteMatchStore`), restart-safe wall-clock timestamps (`time.time`), startup recovery (`MatchManager.recover_from_store`, `ArenaTelegramCoordinator.recover_on_startup`), resilient `/game` message reconstruction, historical match storage, and persistent character media caching.

## 2. Database Schema & Migrations (`app/persistence/store.py`)
- **Schema Version:** `SCHEMA_VERSION = 1` tracked in `schema_migrations (version, applied_at)`.
- **SQLite Pragmas:** `WAL` journal mode (for file-backed DBs), `synchronous=NORMAL`, `busy_timeout=5000`, `foreign_keys=ON`.
- **Tables:**
  - `challenges`: `challenge_id`, `challenge_type`, `challenger_id`, `target_player_id`, `universe_id`, `game_mode`, `chat_id`, `message_id`, `status`, `created_at`, `expires_at`, `generation`, `accepted_by`, `match_id`.
  - `matches`: `match_id`, `challenge_id`, `player_1_id`, `player_2_id`, `universe_id`, `game_mode`, `dataset_version`, `status`, `generation`, `draft_revision`, `turn_started_at`, `turn_deadline_at`, `turn_number_at_start`, `inactivity_claim_offered_to`, `inactivity_claim_expires_at`, `created_at`, `updated_at`, `draft_snapshot_json`, `timeout_policy_json`, `extensions_remaining_json`, `message_refs_json`, `outcome_json`.
  - `active_player_locks`: `player_id PRIMARY KEY`, `match_id` — enforces global one-active-match-per-player at the database level across restarts.
  - `player_profiles`: `player_id`, `display_name`, `username`, `updated_at`.
  - `match_history`: Permanent terminal records (both normal Module 3 resolutions and early terminations without fabricated matchups) ready for Module 8.
  - `media_cache`: Persistent Telegram `file_id` cache keyed by `(character_id, checksum_or_ref)`.

## 3. Atomic Transactions & Crash Safety
- All state transitions commit inside `BEGIN IMMEDIATE` SQLite transactions **before** updating in-memory state or attempting Telegram message edits.
- Secret random seeds are never persisted or exposed; once a character is drawn and committed in `draft_snapshot_json`, restarts or retries cannot change it.

## 4. Startup Recovery Policy & Downtime Handling
On startup (`recover_on_startup`):
1. Open and migrate SQLite without erasing existing data.
2. **Challenges:** Expired open challenges (`now >= expires_at`) are marked `EXPIRED` and their obsolete Telegram controls are removed; still-valid challenges keep their original `expires_at` and reschedule expiry timers.
3. **Active Matches:**
   - Verify pinned `dataset_version` via `CharacterDatabase.load_manifest`. Missing/corrupt datasets fail safely and surface a non-sensitive warning in `StartupRecoveryReport` without crashing startup.
   - Restore `active_player_locks` and `MatchUIState` from `message_refs`.
   - **Original Deadlines Preserved:** Active turn timers are never reset to 120s on restart.
   - **Turn Expired During Downtime:** Transitions the match to the 60s inactivity claim prompt (`now + claim_window_seconds`) rather than fabricating an automatic victory because the bot was offline.
   - **Claim Window Expired During Downtime:** Transitions to `ABANDONED` (`MUTUAL_INACTIVITY_ABANDONMENT`, no winner, `affects_rating=False`).

## 5. Telegram `/game` Recovery & Media
- `recover_game_ui` is serialized per match (`_recovery_locks`), bumps `match.generation` atomically via `replace_message_references(..., bump_generation=True)` to invalidate stale keyboards, and reuses surviving board/card messages without duplicating boards.
- `CharacterMediaResolver` (`app/telegram/media.py`) resolves cached Telegram `file_id`s or HTTPS URLs without auto-promoting technically validated images to identity-verified.

## 6. Deployment, Free Render Web Service & Durable Storage Strategy
- **Render Hosting Mode:** Hosted as a free Render **Web Service** (`type: web`, `plan: free`, `region: frankfurt`, `startCommand: python -u -m app.main`, `healthCheckPath: /health`). `maxShutdownDelaySeconds` is omitted because Render does not support it on free instances.
- **HTTP Health Server (`app/telegram/web.py`):** Runs a lightweight `aiohttp.web` server bound to `0.0.0.0:$PORT` alongside Telegram polling, serving `/` and `/health` (`200 OK` JSON) and shutting down gracefully via `runner.cleanup()` alongside `dp.stop_polling()`.
- **Ephemeral Filesystem Limitation:** Render Free Web Services use an ephemeral filesystem — local SQLite files (`ARENA_DB_PATH`, `ARENA_STATE_DB_PATH`) and `RESTART_STATE_PATH` survive in-process restarts on the same container, but **are wiped on redeploy or container replacement**.
- **Durable Production Storage Strategy:** For production competitive gameplay across redeploys, either upgrade to a Render paid plan with a Persistent Disk mounted at `/var/data`, or add an external managed database backend (e.g., PostgreSQL) implementing the `SqliteMatchStore` persistence contract.
- `SqliteMatchStore.backup_to(dest_path)` uses SQLite's online backup API for safe live snapshots.
