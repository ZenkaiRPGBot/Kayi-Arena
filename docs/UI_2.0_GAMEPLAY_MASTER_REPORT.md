# KAYI ARENA — UI 2.0 Gameplay Master Implementation Report (Modules 09–17)

## 1. Implementation Summary
Implemented the complete Kayi Arena UI 2.0 Gameplay Lifecycle (Modules 09–17, Screens 01–16) on top of the latest `main` branch (`2cfd9bb`), preserving all existing gameplay rules, SCORE-1.0 scoring, rarity weights, `/start`, `/help`, `/arena` configuration, and challenge interfaces.

Key deliverables:
- **Approved Unicode typography & symbol system** (`app/telegram/constants.py`, `app/telegram/texts.py`): Bold Serif uppercase headings (`𝐊𝐀𝐘𝐈 𝐀𝐑𝐄𝐍𝐀`, `𝐂𝐇𝐀𝐑𝐀𝐂𝐓𝐄𝐑 𝐃𝐑𝐀𝐅𝐓`, `𝐀𝐑𝐄𝐍𝐀 𝐑𝐄𝐒𝐔𝐋𝐓`, `𝐁𝐀𝐓𝐓𝐋𝐄 𝐁𝐑𝐄𝐀𝐊𝐃𝐎𝐖𝐍`, character names `✦ 𝐈𝐓𝐀𝐂𝐇𝐈 𝐔𝐂𝐇𝐈𝐇𝐀`), Bold Sans-Serif button labels, small-caps status indicators (`ᴄᴜʀʀᴇɴᴛ ᴛᴜʀɴ`, `sᴋɪᴘᴘᴇᴅ`, `ᴠɪᴄᴛᴏʀʏ`, `ᴅᴇꜰᴇᴀᴛ`, `ᴛɪᴍᴇᴏᴜᴛ`, `ɴᴏ ʀᴇsᴘᴏɴsᴇ`, `ᴅʀᴀᴡ`), section separator (`──────── ✦ ────────`), and escaped native `tg://user?id=...` first-name mentions.
- **Two-message gameplay architecture & challenge handoff** (`app/telegram/service.py`, `app/telegram/handlers/callbacks.py`): Challenge acceptance reuses the challenge message as the Draft Board (or replaces it cleanly) and sends a text-only Initial Shuffle Action Card.
- **Persistent character artwork lifecycle** (`MatchDisplayState` in `app/matches/models.py`, `app/persistence/models.py`, `app/persistence/store.py`, `app/persistence/mongo_store.py`): Retains the most recently obtained character's artwork across role assignments, next-player Shuffle, Skip, Turn Expired, Extra Time, Recovery, and process restarts.
- **Full-match recovery & stale-interface protection** (`recover_game_ui`, `/game` confirmation flow `gr` / `grb` / `grc`): Atomically bumps `match.generation`, removes/disables old messages and temporary confirmations, sends fresh Draft Board + Action Card in the original group, persists both new message IDs, and re-arms turn/claim timers.
- **Terminal message cleanup**: Edits the Draft Board into the final result, deletes the Action Card (or strips its keyboard if deletion fails), deletes temporary forfeit confirmations, and cleans up obsolete recovery messages.
- **Dedicated Kayi Arena Gameplay Logs** (`app/telegram/gameplay_logs.py`): Non-blocking, deduplicated logger targeting `ARENA_LOG_CHANNEL_ID` (`#MATCH_STARTED`, `#COMPLETED`, `#FORFEITED`, `#INACTIVITY`, `#ABANDONED`, `#RECOVERED`, `#RECOVERY_FAILED`, `#ERROR`), keeping `LOG_CHANNEL_ID` dedicated to restart/infrastructure alerts.

## 2. Commit Hash
- **Implementation & Tests Commit:** `8fa03f2` (`main`)
- **Base Commit:** `2cfd9bb`

## 3. Exact Implemented Screen Inventory
| Screen | Name | Renderer / Builder |
|---|---|---|
| Screen 01 | Draft Board (Initial & In-Progress) | `render_draft_board` / `build_draft_board_keyboard` |
| Screen 02 | Initial Shuffle (Text-only) | `render_awaiting_shuffle_card` / `build_awaiting_shuffle_keyboard` |
| Screen 03 | Character Obtained | `render_revealed_character_card` / `build_character_revealed_keyboard` |
| Screen 04 | Character Assigned & Next Turn | `render_awaiting_shuffle_card` (assigned state) / `build_awaiting_shuffle_keyboard` |
| Screen 05 | Character Skipped | `render_awaiting_shuffle_card` (skipped state) / `build_awaiting_shuffle_keyboard` |
| Screen 06 | Turn Expired (With & Without Extension) | `render_turn_expired_card` / `build_inactivity_keyboard` |
| Screen 07 | Extra Time Granted (Variations A, B, C) | `render_awaiting_shuffle_card` & `render_revealed_character_card` |
| Screen 08 | Victory by Inactivity | `render_match_results` (`INACTIVITY_VICTORY`) |
| Screen 09 | Match Abandoned | `render_match_results` (`MUTUAL_INACTIVITY_ABANDONMENT`) |
| Screen 10 | Completed Battle Result (No Emojis) | `render_match_results` (normal resolution) / `build_match_results_keyboard` |
| Screen 11 | Battle Breakdown (No Emojis, Single Message) | `render_detailed_result_page` / `build_detailed_results_keyboard` |
| Screen 12 | Tiebreaker & Draw | `render_match_results` (`COMBINED_SCORE` & `DRAW`) |
| Screen 13 | Forfeit Confirmation | `render_forfeit_confirmation` / `build_forfeit_confirm_keyboard` |
| Screen 14 | Forfeit Result | `render_match_results` (`VOLUNTARY_FORFEITURE`) |
| Screen 15 | Active Match (`/game`), Recovery Confirm, Success & Failure | `render_active_game`, `render_recover_confirmation`, `render_recover_success`, `render_recover_failed` |
| Screen 16 | No Active Match (`/game`) | `render_no_active_game` / `build_no_active_game_keyboard` (`None`) |

## 4. Final Message Templates (Rendered Previews)
- **Screen 01 (Draft Board):** `⚔️ 𝐊𝐀𝐘𝐈 𝐀𝐑𝐄𝐍𝐀`, `◆ Universe`, `◆ Mode`, `──────── ✦ ────────`, `🔵 {mention} 〔0/7〕 ✦ ᴄᴜʀʀᴇɴᴛ ᴛᴜʀɴ`, assigned roles in canonical `ROLE_ORDER` (`✦ {icon} {Role} — {Char} {rarity}`), `▪ Available:` unassigned role emojis (or `None`), `▪ Skips left: X/2`.
- **Screen 02 (Initial Shuffle):** `🎲 𝐂𝐇𝐀𝐑𝐀𝐂𝐓𝐄𝐑 𝐃𝐑𝐀𝐅𝐓`, `{mention}, Shuffle to reveal your first character.`, `▪ Time limit: 2 minutes` (or actual remaining time on restore).
- **Screen 03 (Character Obtained):** Character artwork + `✦ {BOLD_SERIF_NAME}`, `{rarity_icon} {Rarity}`, `──────── ✦ ────────`, `{mention}, choose a role for your character.`, `▪ Skips left: X/2`, `▪ Time remaining: Xm YYs`.
- **Screen 04 (Assigned & Next Turn):** Retained artwork + `✅ Assigned as {Role} by {mention}.` + `{next_mention}, Shuffle to reveal your next character.`
- **Screen 05 (Skipped):** Retained artwork + `{rarity_icon} {Rarity} · ⏭ sᴋɪᴘᴘᴇᴅ` + `{mention}, Shuffle to reveal another character.` + remaining skips & timer.
- **Screen 06 (Turn Expired):** `⌛ 𝐓𝐈𝐌𝐄'𝐒 𝐔𝐏`, `{inactive} failed to complete their turn.`, `{opponent}, claim victory or grant extra time.` (or `you may now claim victory.` + `No further extensions are available.`).
- **Screen 07 (Extra Time Granted):** Variation A (`⏳ 𝐓𝐔𝐑𝐍 𝐄𝐗𝐓𝐄𝐍𝐃𝐄𝐃`), Variation B (held character + `⏳ {opp} granted an extra minute.` + `This is your final extension.`), Variation C (skipped character + extension note).
- **Screen 08 / 09 / 14 (Inactivity / Abandoned / Forfeit):** `⚔️ 𝐀𝐑𝐄𝐍𝐀 𝐑𝐄𝐒𝐔𝐋𝐓` with small-caps status badges (`ᴠɪᴄᴛᴏʀʏ`, `ᴅᴇꜰᴇᴀᴛ`, `ᴛɪᴍᴇᴏᴜᴛ`, `ɴᴏ ʀᴇsᴘᴏɴsᴇ`) and no fabricated role scores.
- **Screen 10 & 12 (Completed Result / Tiebreaker / Draw):** Zero emojis, `𝐀𝐑𝐄𝐍𝐀 𝐑𝐄𝐒𝐔𝐋𝐓`, `{p1} 〔𝟒 — 𝟐〕 {p2}`, `✦ {winner} — ᴠɪᴄᴛᴏʀʏ` or `✦ 𝐁𝐀𝐓𝐓𝐋𝐄 𝐃𝐑𝐀𝐖`, 7 canonical role comparisons with `〔Winner · Score〕`, `𝐓𝐄𝐀𝐌 𝐒𝐂𝐎𝐑𝐄𝐒`, and exact decision explanation.
- **Screen 11 (Battle Breakdown):** Zero emojis, `𝐁𝐀𝐓𝐓𝐋𝐄 𝐁𝐑𝐄𝐀𝐊𝐃𝐎𝐖𝐍`, `Power / Role Fit / Score` for all 7 roles in one message, `Total Score — X : Y`.
- **Screen 13 (Forfeit Confirmation):** `𝐂𝐎𝐍𝐅𝐈𝐑𝐌 𝐒𝐔𝐑𝐑𝐄𝐍𝐃𝐄𝐑`, `{req}, are you sure you want to forfeit against {opp}?`.
- **Screen 15 & 16 (`/game`):** `⚔️ 𝐀𝐂𝐓𝐈𝐕𝐄 𝐌𝐀𝐓𝐂𝐇`, `🔄 𝐑𝐄𝐂𝐎𝐕𝐄𝐑 𝐌𝐀𝐓𝐂𝐇`, `✅ 𝐌𝐀𝐓𝐂𝐇 𝐑𝐄𝐂𝐎𝐕𝐄𝐑𝐄𝐃`, `⚠️ 𝐑𝐄𝐂𝐎𝐕𝐄𝐑𝐘 𝐈𝐍𝐂𝐎𝐌𝐏𝐋𝐄𝐓𝐄`, `⚔️ 𝐍𝐎 𝐀𝐂𝐓𝐈𝐕𝐄 𝐌𝐀𝐓𝐂𝐇`.

## 5. Final Keyboard Arrangements
- **Draft Board:** `[[ ⚑ 𝗙𝗼𝗿𝗳𝗲𝗶𝘁 ]]`
- **Shuffle / Assigned / Skipped / Extended A & C:** `[[ 🎲 𝗦𝗵𝘂𝗳𝗳𝗹𝗲 ]]`
- **Character Obtained / Extended B:** Available roles in canonical order (2 per row, odd last role full width) + `[[ ⏭ 𝗦𝗞𝗜𝗣 ]]` on final row when `skips_left > 0 and skip_eligible`.
- **Turn Expired:** `[[ 🏆 𝗖𝗹𝗮𝗶𝗺 𝗩𝗶𝗰𝘁𝗼𝗿𝘆, ⏳ 𝗪𝗮𝗶𝘁 𝟭𝗺 ]]` (or `[[ 🏆 𝗖𝗹𝗮𝗶𝗺 𝗩𝗶𝗰𝘁𝗼𝗿𝘆 ]]` when extension exhausted).
- **Completed Result:** `[[ 𝗕𝗮𝘁𝘁𝗹𝗲 𝗕𝗿𝗲𝗮𝗸𝗱𝗼𝘄𝗻 ]]`
- **Battle Breakdown:** `[[ « 𝗕𝗮𝗰𝗸 𝘁𝗼 𝗥𝗲𝘀𝘂𝗹𝘁 ]]`
- **Forfeit Confirmation:** `[[ 𝗙𝗢𝗥𝗙𝗘𝗜𝗧, ✕ 𝗖𝗮𝗻𝗰𝗲𝗹 ]]`
- **`/game` Active Match:** Row 1 (omitted if no valid supergroup message link): `[[ ↗ 𝗚𝗼 𝘁𝗼 𝗠𝗮𝘁𝗰𝗵 ]]`; Row 2: `[[ 🔄 𝗥𝗲𝗰𝗼𝘃𝗲𝗿, ⚑ 𝗙𝗼𝗿𝗳𝗲𝗶𝘁 ]]`.
- **Recovery Confirmation:** `[[ 𝗥𝗲𝗰𝗼𝘃𝗲𝗿, « 𝗕𝗮𝗰𝗸 ]]`
- **Recovery Success:** `[[ ↗ 𝗚𝗼 𝘁𝗼 𝗠𝗮𝘁𝗰𝗵 ]]` (omitted if no valid link).
- **No Active Match / Inactivity / Abandoned / Forfeit Result:** `None` (no keyboard).

## 6. Native Button Styles
- **Primary (`"primary"`):** `🎲 𝗦𝗵𝘂𝗳𝗳𝗹𝗲`, `⏳ 𝗪𝗮𝗶𝘁 𝟭𝗺`, `𝗕𝗮𝘁𝘁𝗹𝗲 𝗕𝗿𝗲𝗮𝗸𝗱𝗼𝘄𝗻`, `↗ 𝗚𝗼 𝘁𝗼 𝗠𝗮𝘁𝗰𝗵`, `𝗥𝗲𝗰𝗼𝘃𝗲𝗿` (confirm).
- **Success (`"success"`):** `🏆 𝗖𝗹𝗮𝗶𝗺 𝗩𝗶𝗰𝘁𝗼𝗿𝘆`.
- **Danger (`"danger"`):** `⏭ 𝗦𝗞𝗜𝗣`, `⚑ 𝗙𝗼𝗿𝗳𝗲𝗶𝘁`, `𝗙𝗢𝗥𝗙𝗘𝗜𝗧`.
- **Default (omitted `style`):** All 7 role buttons, `« 𝗕𝗮𝗰𝗸 𝘁𝗼 𝗥𝗲𝘀𝘂𝗹𝘁`, `🔄 𝗥𝗲𝗰𝗼𝘃𝗲𝗿`, `« 𝗕𝗮𝗰𝗸`, `✕ 𝗖𝗮𝗻𝗰𝗲𝗹`.

## 7. Artwork Lifecycle Implementation
Implemented via `MatchDisplayState` and `_resolve_retained_photo` in `app/telegram/service.py`:
- Initial Shuffle sends a text-only message (`card_is_photo=False`).
- On first successful Shuffle, `replace_text_with_photo_card_safe` upgrades the card to a photo message and persists `media_ref` + `card_is_photo=True` via `MatchManager.update_display_state`.
- On Assign (`last_action="assigned"`), Skip (`last_action="skipped"`), Turn Expired, Extra Time (`extension_granted_note=True`), and Recovery, `_resolve_retained_photo` resolves `display_state.media_ref` (or falls back to `display_state.last_character_id` / `draft_snapshot.last_skipped_id`) so the artwork stays attached without making assigned/skipped characters assignable again.

## 8. Persistent Display-State Changes
Added `MatchDisplayState` (`last_character_id`, `last_character_name`, `last_character_rarity`, `last_action`, `assigned_role`, `assigned_by_player_id`, `media_ref`, `card_is_photo`, `extension_granted_note`) to `ManagedMatch`:
- **SQLite:** Schema migration `4` (`ALTER TABLE matches ADD COLUMN display_state_json TEXT NOT NULL DEFAULT '{}'`).
- **MongoDB:** Backward-compatible `"display_state"` subdocument (`doc.get("display_state")` defaults to empty `MatchDisplayState()` for pre-existing matches).

## 9. Callback Authorization & Generation Protection
- Every gameplay callback (`sh`, `sk`, `as`, `cv`, `ex`, `gf`, `gfc`, `gfk`, `grc`) validates participant membership, `DRAFTING` status, `expected_generation == match.generation`, and `expected_revision` (where applicable).
- Group gameplay callbacks (`sh`, `sk`, `as`, `cv`, `ex`, `gf`) reject cross-chat replays (`chat_id != match_chat_id`) and stale card message IDs (`msg_id != current_ui.card_message_id`).
- Stale callbacks return `"This gameplay interface is outdated.\nUse /game to access the latest match messages."` as a callback alert without mutating state.
- Forfeit confirmations (`gf`, `gfc`, `gfk`) are serialized per `(match_id, user_id)` with `asyncio.Lock`, bound to `(chat_id, msg_id, user_id, generation)`, and consumed before awaiting confirm/cancel.
- Battle Breakdown (`dr`, `mr`) restricts shared result toggling to match participants (`user_id in match.players`).

## 10. Full-Match Recovery Behavior
Confirmed recovery (`gr` -> `grc`) runs under `_recovery_lock(match_id)`:
1. Re-fetches latest match and verifies `DRAFTING` status and valid group `chat_id`.
2. Bumps `match.generation` FIRST so all old callbacks are immediately rejected.
3. Deletes/strips old Draft Board, Action Card, and temporary forfeit confirmations; clears stale message references while keeping `kind="chat"` for retry safety.
4. Sends a brand-new Draft Board and a brand-new Action Card (restoring exact state, retained artwork, and real remaining deadline).
5. Persists both new `MessageReference`s (`board` and `card`), reconciles if a concurrent timeout occurred during Telegram I/O, and re-arms the turn or claim timer with the new generation.
6. Logs `#RECOVERED` and updates `/game` to `𝐌𝐀𝐓𝐂𝐇 𝐑𝐄𝐂𝐎𝐕𝐄𝐑𝐄𝐃` with a `Go to Match` link to the new Action Card.

## 11. Partial Recovery Handling
- If sending the replacement Draft Board fails, sending the Action Card fails, or persisting the new `MessageReference`s raises/fails, any partially created replacement message is deleted/stripped, `#RECOVERY_FAILED` is logged, and `/game` displays `⚠️ 𝐑𝐄𝐂𝐎𝐕𝐄𝐑𝐘 𝐈𝐍𝐂𝐎𝐌𝐏𝐋𝐄𝐓𝐄` with a retry prompt. Success is never reported unless both messages and persistence succeed.

## 12. Timer & Extension Behavior
- Preserves 120s normal turn, 60s opponent claim window, 60s extension, and 1 extension per player.
- Shuffle and Skip preserve the active turn deadline; Assignment starts the opponent's 120s turn.
- Recovered Action Cards and Turn Expired cards display actual remaining time from persisted deadlines.
- On 2nd timeout after extension, `Wait 1m` is omitted; on claim-window expiry, `MUTUAL_INACTIVITY_ABANDONMENT` records `inactive_player_id` and ends the match with no winner or rating impact.

## 13. Terminal Message Cleanup
- `sync_match_ui` cancels timers, cleans up locks and temporary forfeit confirmations (`fc:*`), edits the Draft Board into the final result (sending at most one replacement if missing, marked in `_terminal_rendered_matches` only upon publish success), deletes the Action Card (or strips its keyboard if deletion fails), and cleans up any leftover obsolete board/card references.

## 14. Dedicated Gameplay Logging Implementation
- Implemented `GameplayLogger` in `app/telegram/gameplay_logs.py` using `ARENA_LOG_CHANNEL_ID`.
- Supports `#MATCH_STARTED`, `#COMPLETED`, `#FORFEITED`, `#INACTIVITY`, `#ABANDONED`, `#RECOVERED`, `#RECOVERY_FAILED`, and `#ERROR`.
- Non-blocking with bounded retries (`max_attempts=3`), deduplication cache, HTML escaping, copyable `<code>` IDs, clickable mentions, and no secrets.

## 15. Environment Configuration Requirements
Add to Render / `.env`:
- **`ARENA_LOG_CHANNEL_ID`**: Numeric Telegram channel ID (e.g. `-100...`) for the private **Kayi Arena Logs** channel.
  - Setup steps:
    1. Create a private Telegram channel named **Kayi Arena Logs**.
    2. Add the Kayi Arena bot as an **Administrator** with **Post Messages** permission.
    3. Obtain the channel's `-100...` ID and set `ARENA_LOG_CHANNEL_ID` in Render Environment Variables.
    4. Leave `LOG_CHANNEL_ID` unchanged for restart/uptime notifications.
  - Note: Until `ARENA_LOG_CHANNEL_ID` is configured in production and bot permissions are granted, gameplay continues normally with gameplay channel logging disabled.

## 16. Database Compatibility & Migration Notes
- **SQLite:** Automatic migration `4` adds `display_state_json TEXT NOT NULL DEFAULT '{}'`. Existing databases upgrade seamlessly on startup.
- **MongoDB:** `display_state` is optional on read (`doc.get("display_state")`); existing active or historical matches load with default `MatchDisplayState()` without requiring manual migration.

## 17. Restart-Recovery Verification
- Verified via `tests/test_persistence_recovery.py` and `tests/test_ui_2_gameplay_master.py`:
  - `display_state` (`last_character_id`, `last_character_name`, `last_character_rarity`, `last_action`, `assigned_role`, `assigned_by_player_id`, `media_ref`, `card_is_photo`, `extension_granted_note`) survives SQLite close/reopen.
  - `_restore_match_ui_from_refs` restores `card_is_photo` from persisted `display_state` instead of resetting to `False`.
  - Obsolete generations remain rejected after restart.

## 18. CodeRabbit CLI Findings & Fixes
Ran `coderabbit review --agent --uncommitted` (19 findings reported across 15 reviewed files). Confirmed and fixed:
- Kept Draft Board `Forfeit` generation in sync on Shuffle (`update_board=True` in `sh` handler).
- Re-armed claim/turn timer after recovery bumps generation and reconciled concurrent timeout races during recovery.
- Handled persistence exceptions in `recover_game_ui` with partial-message cleanup and `#RECOVERY_FAILED` logging.
- Invalidated retired board/card refs before recovery sends so failed recovery does not leave `/game` linking to a deleted card.
- Persisted group `chat` ref if initial `start_match_ui` card send fails.
- Serialized `gf` / `gfc` / `gfk` under per-`(match_id, user_id)` `asyncio.Lock` and consumed confirmation registration before awaiting cancel/confirm.
- Marked `_terminal_rendered_matches` only after actual result publish success.
- Added `draft_snapshot.last_skipped_id` fallback in `_resolve_retained_photo`, remaining claim countdown in `render_turn_expired_card`, `inactive_player_id` recording on abandonment, and character name capping in Battle Breakdown.
- Updated `tests/test_telegram_ui.py` recovery test to exercise `gr` -> `grc` and exact confirmation message IDs.

## 19. Complete Final Regression Results
Command: `python -m pytest tests -v --tb=short` (run after all final CodeRabbit fixes)
- **Collected:** 169
- **Passed:** 169
- **Failed:** 0
- **Skipped:** 0
- **Runtime:** 280.99s (0:04:40)
- **Limitations:** Telegram Bot API calls (`MockBotRecorder`) and MongoDB Atlas live concurrency were not executed against live external servers in this local test run; SQLite persistence, aiogram dispatcher routing, callback validation, and rendering were exercised end-to-end locally.

## 20. Live Deployment Status
- Pushed to GitHub `main` (`8fa03f2` + this report commit). Render auto-deploy and live Telegram group testing remain to be verified by the owner once Render finishes deploying and `ARENA_LOG_CHANNEL_ID` is configured.

## 21. Known Limitations
- `ARENA_LOG_CHANNEL_ID` is not yet configured in this workspace/production environment, so live channel delivery could not be tested against Telegram servers.
- Live MongoDB Atlas multi-process contention was not exercised locally (covered by mocked/unit store tests).

## 22. Decisions Requiring Owner Review
- Configure `ARENA_LOG_CHANNEL_ID` in Render to activate `#MATCH_STARTED` / `#COMPLETED` / `#RECOVERED` logging in **Kayi Arena Logs**.
