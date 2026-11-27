# Kayi Arena — UI 2.0 Implementation Batch 01 Report

**Branch:** `main`  
**Baseline commit:** `b959453`  
**Scope:** Pre-implementation crash-consistency fix, Module 01 (`/start` & Support), Module 02 (`/help` — The Arena Handbook), Module 03 (Command Menu & Navigation).

---

## 1. Pre-Implementation & Final Crash-Consistency Fix

- **Commits `e5f5e62`, `4fa80da`, and final verification fix in `app/persistence/mongo_store.py`:**
  - `accept_challenge_and_create_match()` writes `"pending_commit": True` and numeric epoch `"pending_since"` on the match document before inserting `active_player_locks` and saving the `accepted` challenge, clearing `pending_commit` to `False` only after all steps succeed.
  - If an error occurs after `save_challenge()` may have run, the handler checks whether `pending_commit=False` already persisted (preserving the committed match on uncertain write timeouts); otherwise it attempts an ownership-filtered challenge rollback and, if rollback fails, marks `pending_since = 0.0` while preserving `pending_commit=True` for recovery.
  - `load_active_matches()` excludes `pending_commit: True` matches.
  - `reconcile_orphan_locks(*, min_age_seconds: float = 0.0)` guards each recovery step on `"pending_commit": True`, reopens the matching `accepted` challenge and cleans up partial locks first, and deletes the pending match last. Live lock-conflict reconciliation uses `min_age_seconds=30.0` so an in-progress match creation in another process is never mistaken for an abandoned operation.
  - Verified in `tests/test_mongo_and_migration.py::test_mongo_shared_client_without_uri_and_orphan_lock_recovery` and `test_pending_commit_live_conflict_uncertain_writes_and_same_second_publish`.

## 1A. Dataset Version Collision Fix

- **`app/database/models.py`, `app/database/__init__.py`, `app/database/mongo_repository.py`, `app/telegram/handlers/admin.py`:**
  - Added `generate_dataset_version(universe_id, kind)` using nanosecond-derived millisecond timestamps + 6-hex `uuid4` suffix (`{universe_id}-{prod|test}-{ts_ms}-{suffix}`), eliminating `VERSION_EXISTS` collisions for multiple publications within the same second.
  - Updated `MongoCharacterDatabase.publish_dataset()` to assign strictly monotonic `seq` values (`max(time.time(), max_seq + 1e-6)`) and projected `seq` / `dataset_version` queries.
  - Verified in `tests/test_admin_operations.py` and `tests/test_mongo_and_migration.py`.

---

## 2. Module 01 — `/start` & Support (`aed1b18`)

- **`app/telegram/texts.py`:**
  - Updated `render_home_private()` to the approved welcome message with clickable `/arena` and `/help` commands and exact bold/italic formatting.
  - Added `render_support_home()`.
- **`app/telegram/keyboards.py`:**
  - Updated `build_home_keyboard(config)` to the exact 3-row layout:
    - Row 1: `[➕ Add to Group]` (`success`)
    - Row 2: `[📢 Updates]` (`primary`), `[💬 Support]` (`primary`, internal callback `ka:sup:menu`)
    - Row 3: `[👨💻 Developer]` (`danger`)
  - Added `build_support_keyboard()`:
    - Row 1: `[🐞 Report a Bug]` (`danger`), `[💡 Suggest an Idea]` (`success`)
    - Row 2: `[« Back]` (default)
- **`app/telegram/handlers/commands.py` & `app/telegram/handlers/callbacks.py`:**
  - `cmd_start` sends the configured native welcome video (preserving audio) with the welcome caption and keyboard, falling back cleanly to plain text when unconfigured or on delivery failure.
  - `sup` callback opens the Support menu (replacing video/media messages cleanly via send-then-delete to avoid duplicates), returns truthful `"not available yet"` alerts on bug/idea buttons, and `home` (`« Back`) returns to the `/start` video or text without duplicates.
  - Verified in `tests/test_telegram_ui.py::test_home_keyboard_and_button_styles` and `test_start_welcome_video_and_support_flow`.

---

## 3. Module 02 — `/help` (The Arena Handbook) (`26e1e93`)

- **`app/telegram/texts.py`:**
  - Replaced legacy help topics with the 6-chapter Arena Handbook (`menu` Contents + chapters `1`–`6`):
    - `01/06` Getting Started
    - `02/06` Building Your Team
    - `03/06` Understanding Roles
    - `04/06` Character Rarity (reads percentages dynamically from `app.database.models.DEFAULT_RARITY_WEIGHTS`: 30% / 30% / 22% / 13% / 5%)
    - `05/06` Winning the Battle (mobile-friendly role-by-role SCORE-1.0 example battle: `4 — 2`, 4 wins · 2 losses · 1 draw)
    - `06/06` Match Rules
- **`app/telegram/keyboards.py`:**
  - Contents keyboard: `[1][2][3]` / `[4][5][6]` (all `primary`).
  - Chapter navigation: `[← Previous]` (default, omitted on Ch 1), `[☰]` (`success`), `[Next →]` (`primary`, omitted on Ch 6).
- **`app/telegram/service.py`, `commands.py`, `callbacks.py`:**
  - Added optional support for 7 admin-configured Telegram `file_id` illustrations (`handbook_cover_file_id`, `handbook_ch1_file_id`..`handbook_ch6_file_id`) in `bot_settings`, falling back to full text when unconfigured or if text exceeds `MAX_CAPTION_LENGTH` (1024).
  - Enforced group-chat owner isolation (`register_handbook_message` / `get_handbook_owner`) and safe media↔text message transitions.
  - Verified in `tests/test_telegram_ui.py::test_help_navigation_and_all_pages`.

---

## 4. Module 03 — Command Menu & Navigation (`addb336`)

- **`app/telegram/bot.py` & `app/main.py`:**
  - Updated `PUBLIC_BOT_COMMANDS` to the exact 8 private commands (`/start`, `/arena`, `/game`, `/profile`, `/leaderboard`, `/list`, `/help`, `/ping`).
  - Added `GROUP_BOT_COMMANDS` (7 commands, excluding `/start`) and `ADMIN_BOT_COMMANDS` (`/admin` at top + 8 private commands).
  - Updated `register_bot_commands(bot, config, previous_admin_ids=...)` to register `BotCommandScopeDefault`, `BotCommandScopeAllPrivateChats`, `BotCommandScopeAllGroupChats`, per-admin `BotCommandScopeChat`, and delete `BotCommandScopeAllChatAdministrators` and revoked admin scopes.
- **`app/telegram/keyboards.py`, `commands.py`, `callbacks.py`:**
  - Removed `/history` from advertised command menus while preserving `cmd_history` for backward compatibility.
  - Added default-styled `📜 Match History` button to `/profile` (`build_profile_keyboard`) and paginated `build_history_keyboard` + `hs` callback with `« Back to Profile`.
  - Verified in `tests/test_telegram_ui.py::test_public_commands_use_arena_not_draft` and `test_register_bot_commands_scopes_and_profile_history`.

---

## 5. CodeRabbit CLI Audit & Test Summary

- **CodeRabbit CLI (`coderabbit review --agent --base-commit b959453`):**
  - 4 findings reported:
    1. *Major* (`app/persistence/mongo_store.py`): Preserve `pending_commit=True` match/locks when challenge rollback fails — **Fixed**.
    2. *Minor* (`app/persistence/mongo_store.py`): Guard recovery steps on `pending_commit=True` — **Fixed**.
    3. *Minor* (`app/persistence/mongo_store.py`): Delete pending match only after challenge reopen — **Fixed**.
    4. *Minor* (`app/telegram/keyboards.py:54`): Keep `config.support_url` in Support menu — **Skipped intentionally** per owner-approved Module 01 specification (no support chat exists yet; Support menu uses `Report a Bug`, `Suggest an Idea`, and `« Back`).
- **CodeRabbit CLI (`coderabbit review --agent --uncommitted` on final fixes):**
  - 4 findings reported and all 4 fixed:
    1. *Major* (`app/persistence/mongo_store.py`): Use numeric epoch timestamps for `pending_since` age checks (with ISO string fallback) — **Fixed**.
    2. *Major* (`tests/test_mongo_and_migration.py`): Import `DatasetKind` in test scope — **Fixed**.
    3. *Major* (`tests/test_mongo_and_migration.py`): Fix `PersistenceConflictError` import path — **Fixed**.
    4. *Trivial* (`app/database/mongo_repository.py`): Project `seq` / `dataset_version` fields in `publish_dataset` and `get_latest_published_version` — **Fixed**.
- **Final Regression Suite (`pytest tests -v`):**
  - **150 passed, 0 failed** (including all UI 2.0, MongoDB, SQLite, admin, scoring, draft, and 100k simulation tests).
