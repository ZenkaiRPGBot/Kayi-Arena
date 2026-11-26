# Module 6 — Telegram UI & UX Implementation Report

## 1. Summary
Module 6 connects Kayi Arena's core drafting engine (Module 1), scoring engine (Module 2), match resolution (Module 3), character database (Module 4A), and match lifecycle manager (Module 5) to a modular, native Telegram Bot API interface built on `aiogram` (`>=3.13,<4.0`) and aligned with the Kayi Bots ecosystem conventions.

## 2. Implemented Components

### Telegram UI & Bot Architecture (`app/telegram/`)
- `app/telegram/config.py`: `BotConfig` environment configuration (`BOT_TOKEN`, `BOT_USERNAME`, `OWNER_ID`, `LOG_CHANNEL_ID`, `DEVELOPER_URL`, `UPDATES_URL`, `SUPPORT_URL`, `ARENA_DB_PATH`, `ARENA_DATASET_KIND`, `HOME_BANNER_REF`, `CARD_BACK_REF`, `DROP_PENDING_UPDATES`, `LOG_LEVEL`).
- `app/telegram/constants.py`: Permanent rarity icons (`⚪`, `🟢`, `🔵`, `🟣`, `🟡`), canonical role icons & order (`👑 Captain` through `💚 Healer`), native Bot API button `style` constants (`primary`, `success`, `danger`), and Telegram length limits (`4096` / `1024` / `64`).
- `app/telegram/callbacks.py`: Compact `ka:<action>:<args...>` callback codec strictly bounded to `<= 64` UTF-8 bytes.
- `app/telegram/ports.py`: `ProfileStatsProvider` protocol and `UnavailableStatsProvider` stub for deferred Module 8 features (`/profile`, `/leaderboard`, `/history`).
- `app/telegram/texts.py`: HTML-escaped formatters for private/group `/start`, `/arena` universe selection, open/direct challenge cards, 2-message Draft Board & Shuffle/Revealed cards (with zero hidden rating leaks), Turn Expired card, Module 3 Match Results & early-termination results, viewer-specific paginated Detailed Results (`1/7`–`7/7`), `/game` & forfeit confirmation, `/list` character catalogue, `/help` paginated guide, and `/profile` / `/leaderboard` / `/history`.
- `app/telegram/keyboards.py`: Native styled `InlineKeyboardMarkup` builders (`style="primary"|"success"|"danger"`), dynamic available-role grid (2 per row + full-width final odd role), and conditional Skip/Extension controls.
- `app/telegram/safe_api.py`: Resilient Telegram API wrappers handling `TelegramRetryAfter`, "message is not modified", deleted/uneditable messages, invalid media fallback (retaining controls without invalidating Shuffle), `TelegramForbiddenError`, and transient `TelegramNetworkError`.
- `app/telegram/service.py`: `ArenaTelegramCoordinator` projecting authoritative `MatchManager` state onto the two primary match messages, managing challenge/turn/claim-window timers, viewer-specific Detailed Results, `/game` recovery, and `UpdateDedupMiddleware` support.
- `app/telegram/handlers/`: Modular routers (`commands.py`, `callbacks.py`, `errors.py`) with factory builders (`build_commands_router`, `build_callbacks_router`, `build_errors_router`).
- `app/telegram/restart_notify.py`: Kayi Bots `RestartNotifier` (`Kayi Arena Online 🟢`, `Status: Running smoothly`, optional `restart_reason.txt`, IST timestamp, per-commit dedup, `OWNER_ID` / `LOG_CHANNEL_ID`).
- `app/telegram/bot.py` & `app/main.py`: Bot/Dispatcher factory, public command registration (`/arena`, `/start`, `/game`, `/list`, `/profile`, `/leaderboard`, `/history`, `/help`, `/ping`), and polling entrypoint.

### Application-Layer & Scoring Additions
- `app/matches/service.py`: Added atomic `switch_challenge_mode(...)` (challenger-only, preserves `expires_at`, increments `generation`).
- `app/scoring/rarity_v02.py`: Added `classify_rarity_v02` (`RARITY-0.2`) with optional provisional Naruto Healer rarity floors.

### Deployment & Configuration
- `.env.example`, `render.yaml`, `requirements.txt`, `pyproject.toml`.

## 3. Deviations & Deferred Scope
- No deviations from approved gameplay rules or presentation standards.
- `/profile`, `/leaderboard`, and `/history` display clean unavailable states via `UnavailableStatsProvider` until Module 8 is implemented.
- Durable cross-restart match persistence remains deferred to Module 7; `RestartNotifier` never claims in-memory matches were restored.

## 4. Verification Results
- **Full Regression Suite:** `C:\Users\2024\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests -v`
- **Result:** **`91 passed in 215.96s (0:03:35)`** (0 failed, 0 skipped), including:
  - `tests/test_rarity_v02.py` (3 tests)
  - `tests/test_telegram_ui.py` (8 tests, including mocked end-to-end `/arena` -> challenge -> accept -> 14 assignments -> resolution -> detailed results, media failure fallback, `/game` recovery & forfeit, catalogue filtering, restart notifier, escaping & length limits)
  - All existing Module 1–5 tests (80 tests, including the 100,000-draft simulation).

## 5. Bot Startup Instructions
```powershell
copy .env.example .env
# Set BOT_TOKEN (and optionally OWNER_ID, LOG_CHANNEL_ID) in .env
python -m app.main
```
