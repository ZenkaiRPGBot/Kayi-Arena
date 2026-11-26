# Module 6 — Telegram UI & UX Specification

## 1. Overview & Framework Choice
- **Framework:** `aiogram` (`>=3.13,<4.0`) with `ParseMode.HTML`, `MemoryStorage`, and native Telegram Bot API `InlineKeyboardButton(..., style=...)` (`"primary"`, `"success"`, `"danger"`, default `None`).
- **Kayi Bots Ecosystem Conventions:**
  - Developer URL: `https://t.me/qouba` (`DEVELOPER_URL`)
  - Updates URL: `https://t.me/KayiBots` (`UPDATES_URL`)
  - Support URL: `https://t.me/KayiBots` (`SUPPORT_URL`)
  - Restart Notification: `RestartNotifier` (`app/telegram/restart_notify.py`) matching the Kayi Bots standard (`Kayi Arena Online 🟢`, `Status: Running smoothly`, optional `Note:` from `restart_reason.txt`, IST timestamp, per-commit dedup, `OWNER_ID` / `LOG_CHANNEL_ID`).
  - Deployment: `render.yaml` (`worker`, Frankfurt region, `python -m app.main`) and `.env.example`.

## 2. Public Commands
- `/start` — Home menu in private chat; compact intro in groups.
- `/arena` — Universe selection menu (preserves reply-to-player target across mode switching and pagination).
- `/arena <universe>` — Open challenge (or direct challenge when replying to an eligible player).
- `/arena random` — Challenge in a random active eligible universe.
- `/game` — Active match status, Go to Game link, Recover Game, and Forfeit Match confirmation.
- `/list` — Public character catalogue with universe selection, rarity filtering, and pagination (no hidden ratings).
- `/profile` — Player profile (uses `ProfileStatsProvider`; shows graceful unavailable state until Module 8).
- `/leaderboard` — Global & This Group leaderboard UI (Module 8 integration port).
- `/history` — Match history UI (Module 7/8 integration port).
- `/help` — Paginated gameplay guide covering all approved rules.
- `/ping` — Bot responsiveness check.

## 3. Presentation Standards
- **Rarity Icons:** Common `⚪`, Uncommon `🟢`, Rare `🔵`, Epic `🟣`, Legendary `🟡`.
- **Canonical Role Icons & Order:**
  1. `👑 Captain`
  2. `🧠 Strategist`
  3. `⚔️ Attacker`
  4. `🛡️ Tank`
  5. `🗡️ Assassin`
  6. `✨ Support`
  7. `💚 Healer`
- **Button Styling:**
  - `primary` (blue): Shuffle, Enter Arena, active filter/mode toggles, Grant 60 More Seconds, Go to Game.
  - `success` (green): Accept Challenge, role assignment buttons, Rematch, Claim Victory.
  - `danger` (red): Cancel Challenge, Forfeit Match, Yes, Forfeit.
  - Default (`None`): Skip, pagination, navigation, secondary actions.
- **Safety & Limits:**
  - All user-controlled text escaped via `html.escape(..., quote=True)`.
  - Messages clamped to `4096` chars; photo captions clamped to `1024` chars.
  - Compact `ka:<action>:<args...>` callback payloads strictly validated `<= 64` UTF-8 bytes.

## 4. Two-Message Match Architecture & Lifecycle
1. **Permanent Draft Board:** Displays universe, mode, match ID, draft progress (`x/14`), both complete rosters with rarity icons, skips remaining, active turn, pinned turn deadline countdown, and compact last action line.
2. **Interactive Character Card:**
   - **Awaiting Shuffle:** Card-back artwork (or text fallback) with `[🎲 Shuffle]`.
   - **Character Revealed:** Character artwork (or fallback without invalidating Shuffle), character name, rarity badge, universe, turn prompt, skips available, dynamically generated available-role buttons (2 per row + full-width final odd role), and `[⏭ Skip (x/2)]` when available. Never reveals Power, Role Fits, scores, or RP.
   - **Turn Expired:** `[🏆 Claim Victory]` and (if opponent still has 1 extension left) `[⏳ Grant 60 More Seconds]`.
   - **Completed / Terminal:** Board updates to authoritative Module 3 results (or early-termination reason without fabricated 7 matchups) with `[🔁 Rematch]`, `[📊 Detailed Results]` (viewer-specific pagination `1/7..7/7` revealing only Power and assigned-role Fit), and player profile buttons. Card retires gameplay controls.

## 5. Authorization, Concurrency & Reliability
- Every callback routes through `MatchManager` with `expected_generation` and `expected_revision` checks.
- Authoritative gameplay transitions commit before Telegram rendering.
- `app/telegram/safe_api.py` handles `TelegramRetryAfter`, "message is not modified", deleted/uneditable messages, invalid media fallback, `TelegramForbiddenError`, and transient `TelegramNetworkError`.
- `UpdateDedupMiddleware` drops duplicate `update_id`s.

## 6. Rarity Points v0.2 (`app/scoring/rarity_v02.py`)
- Separate balance-testing utility (`RARITY-0.2`) computing `RP = highest_role_score + combat_bonus + specialist_bonus + versatility_bonus` with thresholds `>=100` Legendary, `>=90` Epic, `>=80` Rare, `>=60` Uncommon, `<60` Common, plus optional provisional Naruto Healer floors (`Healer Fit 4 -> min Rare`, `Healer Fit 5 -> min Epic`).

## 7. Integration Interfaces & Remaining Modules
- **Module 7 (Persistence):** Durable match/challenge/message-ref storage so `/game` recovery and restart notifications can restore in-progress matches across process restarts.
- **Module 8 (Competitive Progression):** `ProfileStatsProvider` (`app/telegram/ports.py`) connects `/profile`, `/leaderboard`, and `/history` once rating formulas and progression are finalized.
- **Module 9 (Production Content & Artwork):** Populates verified character datasets and `ImageMetadata` in `CharacterDatabase`.
