# Kayi Arena

Competitive Telegram-based anime character drafting game under the **Kayi Bots** ecosystem.

- **Bot name:** Kayi Arena (`@KayiArenaBot`)
- **Primary gameplay command:** `/draft`
- **Current status:** **Module 1 (Core Drafting Engine)** and **Module 2 (Character Evaluation & Scoring)** implemented and verified; Modules 3–9 are planned or awaiting specification.

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
```

## Module Roadmap

| # | Module | Status |
| --- | --- | --- |
| 1 | Core Drafting Engine | Implemented & Tested (`v1.0`) |
| 2 | Character Evaluation & Scoring | Implemented & Tested (`SCORE-1.0`) |
| 3 | Match Resolution | Awaiting Planning |
| 4 | Universe & Character Database | Awaiting Planning |
| 5 | Challenge & Match Management | Awaiting Planning |
| 6 | Telegram UI & User Experience | Awaiting Planning |
| 7 | Persistence & Game Recovery | Awaiting Planning |
| 8 | Profiles & Competitive Progression | Awaiting Planning |
| 9 | Administration & Bot Operations | Awaiting Planning |

## Documentation

- [Module 1 Specification](docs/MODULE_01_CORE_DRAFTING_ENGINE.md)
- [Module 2 Final Scoring Specification](docs/Kayi%20Arena%20%E2%80%94%20Module%202%20Final%20Scoring%20Specification%20%26%20Implementation%20Handoff%20v1.0.md)
- [Progress Tracker](docs/PROGRESS.md)
- [Architecture & Technical Decisions](docs/DECISIONS.md)
- [Module 1 Implementation Report](docs/MODULE_01_IMPLEMENTATION_REPORT.md)
- [Module 2 Implementation Report](docs/MODULE_02_IMPLEMENTATION_REPORT.md)
