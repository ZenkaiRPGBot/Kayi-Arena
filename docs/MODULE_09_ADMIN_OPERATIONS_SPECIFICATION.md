# Module 9 — Admin Operations & Deployment Readiness Specification

## 1. Overview
Module 9 provides an owner- and admin-authorized `/admin` Telegram operations dashboard (`app/telegram/handlers/admin.py`), persistent maintenance mode (`MaintenanceMiddleware`), SQLite Schema v2 audit logging & chat tracking (`app/persistence/store.py`), and dual-mode Telegram transport (`polling` or `webhook`) for reliable hosting on a free Render Web Service.

## 2. Administrative Authorization & Security
- **Authorized IDs:** Configured via `OWNER_ID` and comma-separated `ADMIN_IDS` (`BotConfig.is_admin`).
- **Independent Verification:** Every `/admin` command, private-chat broadcast draft input, and `adm:*` callback independently verifies `config.is_admin(user.id)` AND `chat.type == "private"`. Button visibility is never treated as a security boundary.
- **Audit Logging:** All mutating admin actions (`toggle_universe_active`, `approve_character`, `reopen_character_draft`, `publish_dataset`, `terminate_match`, `send_broadcast`, `database_backup`, `set_maintenance_mode`) are persisted in `admin_audit_log`.
- **Secret Protection:** Never exposes `BOT_TOKEN`, `WEBHOOK_SECRET`, database credentials, private player info, or unpublished character ratings to ordinary users.

## 3. Admin Workflows (`/admin`)
- **Dashboard (`adm:dash`):** Real-time uptime, SQLite `PRAGMA integrity_check`, maintenance state, registered users, active matches, open challenges, and eligible universes.
- **Statistics & Diagnostics (`adm:stats`, `adm:diag`):** Real SQLite counts, Python/OS runtime, transport mode, and dataset kind.
- **Universe Management (`adm:univ`):** Activate/deactivate universes with explicit confirmation.
- **Character Review (`adm:chars`):** Browse `Draft`, `Review`, and `Approved` records, inspect `ImageValidationStatus`, approve `Review` characters, or reopen `Approved` records to `Draft` with confirmation.
- **Dataset Management (`adm:dsets`):** Validate and publish new immutable dataset versions with confirmation; existing active and completed matches remain pinned to their original dataset versions.
- **Active Matches (`adm:matches`):** Inspect active matches and perform narrowly scoped administrative termination (`TerminationReason.ADMINISTRATIVE`) with confirmation and audit reason (no fabricated victory).
- **Broadcast (`adm:bcast`):** Compose -> preview with target chat count -> explicit confirmation -> rate-limited delivery (`0.05s` pacing) -> delivery report.
- **Database Backup (`adm:backup`):** Runs `PRAGMA integrity_check` and creates timestamped SQLite snapshots via `SqliteMatchStore.backup_to()`.
- **Maintenance Mode (`adm:maint`):** Persisted in `bot_settings`; blocks non-admin gameplay commands & callbacks while allowing admins to manage the bot.

## 4. Competitive Progression Boundary
Module 8 (ratings, rank thresholds, rewards, seasonal rankings, XP/currency) remains explicitly deferred. Existing `ProfileStatsProvider` integration ports remain intact.
