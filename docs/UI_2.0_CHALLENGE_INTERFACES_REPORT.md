# Kayi Arena — UI 2.0 Modules 05, 06 & 08 Report

**Modules:**
- Module 05 — Direct Challenge
- Module 06 — Open Challenge
- Module 08 — Challenge Lifecycle & Player Mentions

**Status:** Implemented, verified, and pushed to `main`

---

## 1. Final Direct Challenge Interface (`render_challenge_card`, `build_challenge_keyboard`)

- **Standard Direct Challenge:**
  ```html
  <b>⚔️ Battle Challenge</b>

  <a href="tg://user?id=123456789">Obito</a> has challenged <a href="tg://user?id=987654321">Kakashi</a> to a battle.

  <b>Universe:</b> 🍥 Naruto

  <b>Mode:</b> 🏆 Ranked

  <i>⏳ Expires in 5 minutes.</i>
  ```
- **Random Universe Variation:**
  - Displays `<b>Universe:</b> 🎲 Random`, actual selected mode (`🏆 Ranked` or `🤝 Friendly`), and `<i>The universe will be revealed upon acceptance.</i>` before the expiration line.
  - Random universe remains unresolved until successful acceptance.
- **Keyboard:**
  - Row 1: `[ ⚔️ Accept ]` (`success` / green) | `[ Decline ]` (default)
  - Row 2: `[ ✕ Cancel ]` (`danger` / red)
- **Permissions:**
  - `Accept` (`ca`): targeted opponent only (enforces eligibility & active-match locks).
  - `Decline` (`cd`): targeted opponent only.
  - `Cancel` (`cx`): original challenger only.

---

## 2. Final Open Challenge Interface

- **Standard Open Challenge:**
  ```html
  <b>⚔️ Open Challenge</b>

  <a href="tg://user?id=123456789">Obito</a> is looking for an opponent.

  <b>Universe:</b> 🍥 Naruto

  <b>Mode:</b> 🏆 Ranked

  <i>⏳ Expires in 5 minutes.</i>
  ```
- **Random Universe Variation:**
  - Displays `<b>Universe:</b> 🎲 Random` and `<i>The universe will be revealed upon acceptance.</i>`.
- **Keyboard:**
  - Single row: `[ ⚔️ Accept ]` (`success` / green) | `[ ✕ Cancel ]` (`danger` / red)
  - No `Decline` button.
- **Permissions:**
  - `Accept` (`ca`): any eligible opponent except the challenger (`You cannot accept your own challenge.`).
  - `Cancel` (`cx`): original challenger only.

---

## 3. Player Mention Convention (`format_user_mention`, `ArenaTelegramCoordinator.first_name`)
- Uses `<a href="tg://user?id={user_id}">{escaped_first_name}</a>`.
- Records `user.first_name` in `register_user()`, falls back safely to `"Player"` if unavailable (never displaying raw numeric IDs as visible text), escapes HTML-sensitive characters (`&`, `<`, `>`), and preserves Unicode and emojis.

---

## 4. Challenge Lifecycle, Persistence & Recovery
- **Accepted (`ChallengeStatus.ACCEPTED`):** Cancels challenge expiry timer, removes obsolete challenge keyboard, resolves deferred `random` universe atomically under `self._global_lock`, pins dataset version, and transitions to gameplay. Post-commit Telegram UI errors are caught/logged without rolling back committed matches or reporting failed acceptance.
- **Declined (`ChallengeStatus.DECLINED`):** Implemented `MatchManager.decline_challenge()`. Edits invitation to `<b>Challenge Declined</b>\n\n{opponent_mention} declined the challenge.`, removes all buttons, and records no match/loss.
- **Cancelled (`ChallengeStatus.CANCELLED`):** Edits invitation to `<b>❌ Challenge Cancelled</b>\n\n{challenger_mention} cancelled the challenge.`, removes all buttons, and records no match/loss.
- **Expired (`ChallengeStatus.EXPIRED`):** Edits invitation to `<b>⌛ Challenge Expired</b>\n\nThe challenge was not accepted in time.`, removes all buttons, and preserves the 5-minute (`300.0`s) expiration & restart recovery.
- **Obsolete `cm` mode-switch callbacks:** Do not modify existing challenges; return `"Match mode cannot be changed after sending a challenge."`.

---

## 5. CodeRabbit CLI & Regression Results
- **CodeRabbit CLI (`coderabbit review --agent --uncommitted`):** Reported 6 findings (1 major, 3 minor, 2 trivial) — all 6 fixed:
  1. *Major* (`callbacks.py`): Separated `render_challenge_message` from `start_match_ui` and kept turn timer active + `/game` fallback notice if `start_match_ui` fails or returns `None`.
  2. *Minor* (`matches/service.py`): Allowed authorized `CANCELLED` / `DECLINED` replay to retry Telegram card updates without mutating state or generation.
  3. *Minor* (`texts.py`): Formatted `seconds_remaining` for expiration text.
  4. *Trivial* (`tests/test_telegram_ui.py`): Used emitted Decline button payload and an independent player (`404`) for expiration test.
- **Regression Suite:** Full suite `pytest tests -v` passed **153 / 153**, followed by post-fix `pytest tests/test_telegram_ui.py tests/test_match_management.py -v` (**19 / 19 passed**).
