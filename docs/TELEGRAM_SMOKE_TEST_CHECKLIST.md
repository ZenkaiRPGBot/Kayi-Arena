# Telegram Smoke Test Checklist (Isolated Synthetic Dev Mode)

## 1. Prepare Isolated Synthetic Environment
Use a dedicated test `BOT_TOKEN` and isolated SQLite files (never mix with production):

```powershell
$env:BOT_TOKEN="<your-test-bot-token>"
$env:OWNER_ID="<your-telegram-numeric-id>"
$env:ARENA_DATASET_KIND="synthetic"
$env:ARENA_DB_PATH="data/dev_synthetic.sqlite3"
$env:ARENA_STATE_DB_PATH="data/dev_synthetic_state.sqlite3"
$env:TRANSPORT_MODE="polling"

python -m scripts.seed_synthetic_dev
python -u -m app.main
```

## 2. End-to-End Verification Steps
1. **Startup & Health:**
   - Verify `http://127.0.0.1:10000/` and `http://127.0.0.1:10000/health` return `200 OK` JSON.
   - Verify owner receives `Kayi Arena Online 🟢` restart notification.
2. **Home & Links (`/start`):**
   - Run `/start` in private chat; verify `Developer` (`t.me/qouba`), `Updates` (`t.me/KayiBots`), `Support` (`t.me/KayiBots`), and `Add to Group` buttons.
   - Run `/start` in a test group; verify compact intro.
3. **Universe & Challenges (`/arena`):**
   - Run `/arena` (and `/arena random`) in the test group; toggle Ranked/Friendly.
   - Reply to Player 2 with `/arena` -> verify Direct Challenge; test Mode switch (expiry preserved) and Cancel; create a new Open Challenge and have Player 2 Accept.
4. **Drafting & Timers:**
   - Verify two messages (Draft Board + Character Card).
   - Test `Shuffle`, `Skip` (verify skips decrement and timer does NOT reset), and all `14` role assignments (verify hidden ratings never appear).
5. **Inactivity, Extension, Forfeit & Resolution:**
   - On a second test match, wait 120s for Turn Expired -> test `Grant 60 More Seconds` -> wait for Turn Expired again -> test `Claim Victory`.
   - On a third match, test `/game` -> `Recover Game` (verify old controls reject with `"This action has expired."`) and `Forfeit Match`.
   - On a completed 14-role match, verify Module 3 Match Results and viewer-specific `Detailed Results` (`1/7`–`7/7`).
6. **Restart Recovery:**
   - Mid-draft (with a held character), stop `python -m app.main` (`Ctrl+C`) and restart it; verify held character, rosters, and original deadline are preserved.
7. **Admin Dashboard (`/admin`):**
   - Run `/admin` in private chat as `OWNER_ID`; check `Bot Statistics`, `Diagnostics`, `Manage Universes`, `Manage Characters`, `Manage Datasets`, `Active Matches`, `Database Backup`, `Maintenance Mode`, and `Broadcast`.
   - Confirm `/admin` is rejected for non-admins and in group chats.
