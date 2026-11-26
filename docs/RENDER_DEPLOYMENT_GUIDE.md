# Render Deployment Guide (Free Web Service)

## 1. Free Render Web Service Settings
Create a **Web Service** manually in the Render Dashboard connected to `ZenkaiRPGBot/Kayi-Arena` (`main` branch):
- **Runtime:** Python 3 (`3.12`)
- **Plan:** Free
- **Region:** Frankfurt (or preferred)
- **Build Command:** `pip install --no-cache-dir -r requirements.txt`
- **Start Command:** `python -u -m app.main`
- **Health Check Path:** `/health`
- **Note:** Do **not** set `maxShutdownDelaySeconds` (unsupported on Render Free instances).

## 2. Environment Variables
| Variable | Required | Default / Example | Notes |
| --- | --- | --- | --- |
| `BOT_TOKEN` | Yes | — | Telegram Bot API token (secret) |
| `OWNER_ID` | Yes | `986380678` | Numeric Telegram owner ID |
| `ADMIN_IDS` | Optional | `""` | Comma-separated additional numeric admin IDs |
| `LOG_CHANNEL_ID` | Optional | `""` | Channel/group ID for restart notifications |
| `PORT` | Auto (Render) | `10000` | Bound on `0.0.0.0` by `aiohttp` |
| `TRANSPORT_MODE` | Optional | `polling` | `polling` or `webhook` (only one runs at a time) |
| `WEBHOOK_BASE_URL` | If webhook | `https://<app>.onrender.com` | Falls back to `RENDER_EXTERNAL_URL` |
| `WEBHOOK_PATH` | Optional | `/telegram/webhook` | Webhook endpoint path |
| `WEBHOOK_SECRET` | Optional | `""` | Secret token header validation for webhook |
| `ARENA_DB_PATH` | Optional | `data/kayi_arena.sqlite3` | Character SQLite DB path |
| `ARENA_STATE_DB_PATH` | Optional | `data/kayi_arena_state.sqlite3` | Match/challenge/audit SQLite DB path |
| `ARENA_DATASET_KIND` | Optional | `production` | `production` or `synthetic` |
| `PYTHONUNBUFFERED` | Recommended | `1` | Unbuffered stdout logs |
| `PYTHONPATH` | Recommended | `.` | Module import root |

## 3. Polling vs. Webhook on Free Render Web Services
- **Render Sleep Behavior:** Free Web Services sleep after ~15 minutes without inbound HTTP traffic.
- **Polling Mode (`TRANSPORT_MODE=polling`):** On startup, `app/main.py` calls `bot.delete_webhook(drop_pending_updates=False)` to prevent `409 Conflict` errors from stale webhooks, then runs `dp.start_polling(...)` alongside the `aiohttp` `/health` server. When Render sleeps the container, polling stops until an inbound HTTP request wakes it.
- **Webhook Mode (`TRANSPORT_MODE=webhook` + `WEBHOOK_BASE_URL`):** Recommended when a public HTTPS URL is available. `app/main.py` registers `set_webhook(...)` on `/telegram/webhook` and serves updates through `aiohttp` without running polling. Telegram's incoming webhook POST automatically wakes a sleeping Render Free Web Service, avoiding long-polling disconnections and 409 conflicts.
- **Never run two bot instances with the same `BOT_TOKEN` in polling mode simultaneously** (causes Telegram `409 Conflict`).

## 4. Storage Durability & Limitations
- **Across in-container restarts:** Local SQLite (`WAL` mode) survives process restarts while the container filesystem remains intact.
- **Across redeployments or container replacement:** Render Free Web Services use an **ephemeral filesystem** — local SQLite files and `restart_state.json` are wiped on redeploy/spin-down replacement.
- **Recommended Production Storage Strategy:**
  - *Option A (Low cost):* Render Paid Starter (`$7/mo`) + Persistent Disk mounted at `/var/data` (`ARENA_DB_PATH=/var/data/kayi_arena.sqlite3`, `ARENA_STATE_DB_PATH=/var/data/kayi_arena_state.sqlite3`).
  - *Option B (Free-tier durable DB):* External managed PostgreSQL free tier (e.g. Neon / Supabase / Render Postgres free tier with 90-day expiry) by implementing a PostgreSQL adapter behind the `SqliteMatchStore` persistence interface in a future storage upgrade.

## 5. Downtime Recovery Policy (Owner Review)
- When a **turn deadline** expires while the bot is offline, startup recovery opens a fresh **60-second inactivity claim window** (`now + 60s`) rather than fabricating an automatic victory.
- When an already-open **60-second inactivity claim window** expires during downtime, startup recovery abandons the match (`MUTUAL_INACTIVITY_ABANDONMENT`, no winner, no rating change).
