# Kayi Arena — Initial Naruto Character Integration Report

## 1. Validation & Dataset Summary
- **Total Records:** 60 (`53` `Draft`, `7` `Held`)
- **Held Characters Preserved:** `Rock Lee`, `Hagoromo Otsutsuki`, `Hamura Otsutsuki`, `Indra Otsutsuki`, `Ashura Otsutsuki`, `Sakumo Hatake`, `Izuna Uchiha`
- **Scoring & Rarity Verification:** Validated all 60 records against `SCORE-1.0` and `RARITY-0.2` (with provisional Naruto Healer floors) — **0 mismatches**.
- **Rarity Distribution in Pool (60):** `8` Legendary, `2` Epic, `28` Rare, `22` Uncommon, `0` Common.
- **Full 60-Character Review Table:** See [NARUTO_60_CONSOLIDATED_REVIEW_REPORT.md](file:///D:/KayiBots/Kayi%20Arena/docs/NARUTO_60_CONSOLIDATED_REVIEW_REPORT.md).

## 2. Image Audit & Standardization
- **Replacement Images Verified (Narutopedia API):**
  - **Kurama** (`dattebayo:711`): `https://static.wikia.nocookie.net/naruto/images/7/7b/Kurama2.png/revision/latest?cb=20140818171718` (`1891x1080`)
  - **Jiraiya** (`dattebayo:515`): `https://static.wikia.nocookie.net/naruto/images/d/d7/Jiraiya_Posing.png/revision/latest?cb=20191209054336` (`1916x1076`)
  - **Chiyo** (`dattebayo:148`): `https://static.wikia.nocookie.net/naruto/images/7/73/Chiyo.png/revision/latest?cb=20160113171702` (`1440x1080`)
- **Result:** All **60/60** characters have valid HTTPS image URLs accessible from Render without relying on local gitignored image directories.
- **Standardization:** Added `standardize_card_image()` in [media.py](file:///D:/KayiBots/Kayi%20Arena/app/telegram/media.py) to pad/frame artwork onto a `960x540` landscape canvas with rarity borders and zero stretching.

## 3. 10,000-Match Balance Simulation (`scripts/simulate_naruto_balance.py`)
Simulated **10,000** full 14-role drafts using approved `DEFAULT_RARITY_WEIGHTS` (`30/30/22/13/5`) and `RES-1.0` resolution:
- **Drawn Rarity Distribution:** Uncommon `46.17%`, Rare `34.12%`, Epic `12.12%`, Legendary `7.58%`, Common `0.0%` (no Common characters in initial 60).
- **Role Average Scores:** Attacker `69.17`, Tank `60.05`, Captain `55.13`, Strategist `53.51`, Support `48.81`, Assassin `46.19`, Healer `14.76`.
- **Healer Availability:** `5.42%` of teams drafted a Healer with Fit >= 3; `3.35%` drafted a Healer with Fit >= 4 (random role assignment; actual player drafting will be higher when prioritizing Healers).
- **First-Player Balance:** Starter win rate `50.38%`, second-player win rate `49.42%`, match draws `0.2%`.
- **Matchup Draw Rate:** `17.63%`.
- **Resolution Breakdown:** `84.43%` decided by matchup count, `15.37%` by combined score, `0.2%` exact draws.

## 4. Testing Dataset & Ephemeral Bootstrap
- **Isolated Testing Dataset:** Set `ARENA_DATASET_KIND=test` and `AUTHORIZED_TESTER_IDS=<id1>,<id2>` on a test service to auto-publish `naruto-prelim-test-v1` (the 53 non-held preliminary records) for authorized testers only.
- **Production Ephemeral Bootstrap:** On startup, `bootstrap_naruto_database()` in [naruto_loader.py](file:///D:/KayiBots/Kayi%20Arena/app/database/naruto_loader.py) loads the 60 preliminary records into `Draft`/`Held` status (never auto-approving them for production) and restores owner-approved records only if `ARENA_BOOTSTRAP_SNAPSHOT_PATH` (`data/approved_naruto_snapshot.json`) exists.

## 5. Simple Owner Procedure to Approve & Publish Naruto in Telegram
1. Open your private chat with the bot and run `/admin`.
2. Tap **📚 Manage Characters** -> **Naruto**.
3. Tap **📤 Submit Non-Held Drafts** (submits the 53 non-held characters to Review while preserving all 7 Held characters).
4. Tap **✅ Batch Approve Review** -> **Confirm Approve (53)**.
5. Tap **📦 Go to Datasets** -> **Publish Naruto** -> **Confirm Publish**.
6. Naruto is now live for `/arena` in production! *(To persist your approval across Render Free redeploys, export `data/approved_naruto_snapshot.json` via `export_approved_snapshot()` or upgrade to persistent storage.)*
