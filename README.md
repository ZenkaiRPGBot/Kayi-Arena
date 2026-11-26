# Kayi Arena

Competitive Telegram-based anime character drafting game under the **Kayi Bots** ecosystem.

- **Bot name:** Kayi Arena (`@KayiArenaBot`)
- **Primary gameplay command:** `/arena`
- **Current status:** **Modules 1–7** (Core Drafting, Scoring `SCORE-1.0`, Match Resolution `RES-1.0`, Database Foundation, Character Content Tooling, Challenge & Match Management, Telegram UI & UX, Durable Persistence & Recovery) implemented and verified; Modules 8–9 are awaiting specification.

## Setup

Requires Python 3.12+. Runtime Module 1 code has zero third-party dependencies.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

## Running Tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests -v
```

This runs all unit tests, invariant checks, concurrency/CAS/commit-before-reveal tests, statistical distribution tests, and 100,000 randomized draft simulations.

## Running the Local CLI Demo

Observe and play a fictional 2-player draft locally without Telegram:

```powershell
python -m scripts.demo_draft
python -m scripts.demo_draft --seed 42
python -m scripts.demo_scoring
python -m scripts.demo_resolution
```

## Character Catalogue Tooling (Module 4 support)

Collect and validate candidate character/image data without modifying the production database:

```powershell
python -m scripts.collect_naruto_catalogue --output data/naruto_candidates.json
python -m scripts.validate_naruto_images --catalogue data/naruto_candidates.json --output-dir data/naruto_images --report data/naruto_image_report.json
python -m scripts.export_naruto_catalogue --catalogue data/naruto_candidates.json --output data/naruto_candidates_ka_import.json
```

Notes:
- The collector uses the Dattebayo API and records incomplete/unverified entries as `pending` drafts.
- Image validation checks HTTP status, file signature, dimensions, corruption markers, and exact duplicate hashes.
- Export targets `KA-IMPORT-1.0` (`batch_type = "catalogue"`); `rarity` is intentionally set to a provisional `Common` placeholder because Claude assigns final rarity.
- Network-dependent collection is separate from deterministic unit tests.

## Module Roadmap

| # | Module | Status |
| --- | --- | --- |
| 1 | Core Drafting Engine | Implemented & Tested (`v1.0`) |
| 2 | Character Evaluation & Scoring | Implemented & Tested (`SCORE-1.0`) |
| 3 | Match Resolution | Implemented & Tested (`RES-1.0`) |
| 4A | Universe & Character Database (Foundation) | Implemented & Tested (`SQLite` + `KA-IMPORT-1.0`) |
| 4B | Catalogue & Image Tooling | In Progress (Parallel Branch) |
| 5 | Challenge & Match Management | Implemented & Tested |
| 6 | Telegram UI & User Experience | Implemented & Tested (`aiogram` 3) |
| 7 | Persistence & Game Recovery | Implemented & Tested (`SQLite` + `WAL`) |
| 8 | Profiles & Competitive Progression | Awaiting Planning |
| 9 | Administration & Bot Operations | Awaiting Planning |

## Documentation

- [Module 1 Specification](docs/MODULE_01_CORE_DRAFTING_ENGINE.md)
- [Module 2 Final Scoring Specification](docs/Kayi%20Arena%20%E2%80%94%20Module%202%20Final%20Scoring%20Specification%20%26%20Implementation%20Handoff%20v1.0.md)
- [Module 3 Match Resolution Specification](docs/MODULE_03_MATCH_RESOLUTION_SPECIFICATION.md)
- [Module 5 Challenge & Match Management Specification](docs/MODULE_05_MATCH_MANAGEMENT_SPECIFICATION.md)
- [Module 6 Telegram UI & UX Specification](docs/MODULE_06_TELEGRAM_UI_SPECIFICATION.md)
- [Module 7 Persistence & Recovery Specification](docs/MODULE_07_PERSISTENCE_RECOVERY_SPECIFICATION.md)
- [Versioned JSON Import Format (`KA-IMPORT-1.0`)](docs/IMPORT_FORMAT.md)
- [Progress Tracker](docs/PROGRESS.md)
- [Architecture & Technical Decisions](docs/DECISIONS.md)
- [Module 1 Implementation Report](docs/MODULE_01_IMPLEMENTATION_REPORT.md)
- [Module 2 Implementation Report](docs/MODULE_02_IMPLEMENTATION_REPORT.md)
- [Module 3 Implementation Report](docs/MODULE_03_IMPLEMENTATION_REPORT.md)
- [Module 4A Implementation Report](docs/MODULE_04A_IMPLEMENTATION_REPORT.md)
- [Module 5 Implementation Report](docs/MODULE_05_IMPLEMENTATION_REPORT.md)
- [Module 6 Implementation Report](docs/MODULE_06_IMPLEMENTATION_REPORT.md)
- [Module 7 Implementation Report](docs/MODULE_07_IMPLEMENTATION_REPORT.md)

## Running the Telegram Bot

```powershell
copy .env.example .env
# Set BOT_TOKEN (and optionally OWNER_ID / LOG_CHANNEL_ID) in .env
python -m app.main
```
