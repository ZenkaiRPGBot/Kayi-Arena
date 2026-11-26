# Kayi Arena — Technical Decisions

## Module 1: Core Drafting Engine

1. **Zero-dependency pure engine core (`app/engine/`)**
   - Uses only Python 3.12 standard library (`dataclasses`, `enum`, `json`, `secrets`, `random`, `asyncio`, `hashlib`).
   - Keeps Module 1 completely decoupled from Telegram (`aiogram`), databases, character datasets, ratings, and clocks.

2. **Immutable state & pure transition functions**
   - `DraftSnapshot`, `CatalogEntry`, `DraftConfigSnapshot`, `TerminalRecord`, `PublicDraftView`, and `ActionResult` are frozen dataclasses.
   - Rejected actions return the original snapshot untouched, never mutate skips or revisions, and emit zero events.

3. **Separate `PublicDraftView` vs `DraftSnapshot`**
   - `project_public_view(snapshot)` exposes only the fields permitted by Spec Section 5.5 (`PublicTerminalSummary` exposes only `reason` and `subject_player_id`).
   - `available_pool`, `catalog`, `rarity_weights`, `dataset_version`, `last_skipped_id`, `timestamps`, `caller_reference`, and `source_label` never appear on `PublicDraftView`.

4. **Rarity-first drawing with injected `DrawSource`**
   - Production uses `SystemDrawSource` (`secrets.SystemRandom`); snapshots never store seeds or RNG state.
   - Tests use `SeededDrawSource` and `ScriptedDrawSource` to verify exact draw-source call counts (1 starter call + 1 per Shuffle) and deterministic `state_hash()` outputs.

5. **CAS & commit-before-reveal harness (`app/engine/adapter.py`)**
   - `SerializedDraftService` serializes per-match actions with `asyncio.Lock` and persists via `DraftStore.compare_and_set(expected_revision, snapshot)` before returning `ActionResult` to callers.
   - This serves as the exact contract for Module 7 Persistence & Recovery.

6. **External termination & outdated timeout protection**
   - Per Spec Section 4.3, `terminate_draft` performs no revision check and always acts on the latest state when invoked by an authorized caller (Module 5 / Module 9).
   - Preventing stale inactivity timers from terminating an active turn belongs to Module 5 (which compares the timer's captured `(revision, turn_number)` before calling `terminate_draft`).

## Module 2: Character Evaluation & Scoring

1. **R1–R4 adopted verbatim from Final Scoring Specification v1.0**
   - **R1:** Strict integer typing (`type(v) is int`) rejecting floats (including `3.0`), booleans (`True`/`False`), strings, and `None` (`V02`).
   - **R2:** `scoring_version` is separate from `dataset_version`, with exactly one scoring version per dataset (`DV7`, `DV8`). `SCORE-1.0` cannot be paired with altered scoring constants (`V07`).
   - **R3:** Role scores are precomputed at dataset publication and verified by full recomputation (`DV4`).
   - **R4:** The scoring engine ignores evidence, confidence, and approval status; production-only `Approved` enforcement lives in the dataset layer (`DV1`).

2. **R5 revised per project direction**
   - Advisory diagnostics (`compute_diagnostics`) are calculated even for small datasets (`< 50` approved characters) wherever mathematically defined, rather than suppressed.
   - Samples with `< 50` approved characters are explicitly labeled `is_preliminary=True` (`sample_status="preliminary"`).
   - Single-universe datasets are analyzed directly without requiring multiple universes first.
   - Diagnostics remain strictly advisory (`advisory_only=True`) and never modify ratings/scores or block publication.
   - Undefined Pearson correlations (empty sets or zero-variance/constant series) safely return `None`.

3. **Canonical hashing & V08 invariant guard**
   - `DatasetManifest.compute_content_hash()` uses deterministic `json.dumps(..., sort_keys=True, separators=(",", ":"))` over sorted `DatasetRecord`s + SHA-256, verified on both publication and load (`DV3`).
   - `V08` (`verify_internal_score_range`) is an internal invariant guard tested directly without permitting invalid inputs through public scoring APIs.

## Module 3: Match Resolution (`RES-1.0`)

1. **Approved Decisions (D1–D6)**
   - **D1:** `RES-1.0` stored in every `MatchResolutionSuccess`.
   - **D2:** Each `RoleMatchup` retains `power`, assigned-role `fit`, and assigned-role `score`; full 7-role Fit vectors remain in the pinned dataset.
   - **D3 & D6 (Future Module 4):** Module 4 must generate advisory dataset health reports (never blocking publication or forcing rating changes) and repeat strategic balance simulations using actual character datasets.
   - **D4:** Fail-fast validation precedence Stages 1–9 (`MALFORMED_REQUEST` through `CHARACTER_RECORD_INVALID`), with Stages 1–4 performing zero dataset access.
   - **D5:** All 14 character records are reverified during resolution using Module 2's `score_record()` logic.

2. **Role Casing & Module 1 Adapter**
   - `resolve_match()` strictly enforces lowercase `SCORING_ROLES` (`"captain"`..`"healer"`) with no silent normalization.
   - `build_resolve_request_from_completed_draft()` explicitly translates Module 1's `CompletedDraftOutput` Title Case roles (`"Captain"`..`"Healer"`) into lowercase `SCORING_ROLES` while preserving player identities and slots without reordering.

3. **Canonical Serialization**
   - `canonical_json()` uses `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)` so UTF-8 Unicode characters serialize directly without `\uXXXX` escaping, floats/NaN/Infinity are forbidden, and optional empty `details` are omitted.

## Module 4A: Database Foundation

1. **Zero-dependency SQLite persistence (`app/database/`)**
   - Uses Python 3.12 stdlib `sqlite3` with `PRAGMA foreign_keys = ON` and transactional writes, supporting both `:memory:` and persistent file databases.
   - Implements Module 3's `DatasetReader` protocol directly (`load_manifest`, `get_character`) and exports Module 1-compatible `(catalog, rarity_weights, dataset_version)` via `export_draft_catalog()`.

2. **Five rarity tiers & configurable minimums**
   - Enforces exact 5 rarity tiers: `Common`, `Uncommon`, `Rare`, `Epic`, `Legendary` with configurable positive universe draw weights.
   - Enforces Module 1's hard floor of `14` characters while keeping each universe's `min_pool_size` configurable (`>= 14`).

3. **Publication safeguards & mandatory advisory health reports**
   - Production datasets require active universe, `EvaluationStatus.APPROVED` records only, verified `ImageValidationStatus.VERIFIED` metadata, valid 5-tier rarities, and Module 2 `validate_manifest_for_publication()` (`DV1`–`DV8`).
   - Generates mandatory `DatasetHealthReport` (rarity, Power, Fit, specialist, healer, concentration, tie frequencies, and Module 2 `compute_diagnostics()`) without imposing artificial caps, mandatory healer quotas, or pity systems.

4. **Parallel development contract (`KA-IMPORT-1.0`)**
   - Documented in `docs/IMPORT_FORMAT.md`; supports incomplete candidate imports (`draft` status) and AI evaluation batches independently of external providers/scrapers.

## Module 5: Challenge & Match Management

1. **Global & per-match concurrency isolation**
   - `_global_lock` serializes challenge creation, acceptance, cancellation, expiration, and global `_active_match_by_player` checks.
   - Per-match `asyncio.Lock` serializes all drafting, timeout, forfeit, and resolution transitions.

2. **Timer & stale-timeout protection**
   - `turn_started_at` is updated only when a draft starts or `assign_role` advances the turn; `skip_character` leaves `turn_started_at` unchanged.
   - `handle_turn_timeout` revalidates `(expected_revision, expected_turn_number)` atomically under the match lock before offering an inactivity claim.
   - `ProvisionalTimeoutPolicy` durations (`300s` challenge, `90s` turn, `60s` claim) are explicitly provisional pending owner confirmation.

3. **Dataset pinning & resolution boundary**
   - `accept_challenge` pins the universe's latest published `dataset_version` and rarity weights at match creation; later publications never affect active matches.
   - Prematurely terminated matches (`FORFEITED`, `INACTIVITY_WIN`, `ABANDONED`, `TERMINATED_*`) never enter Module 3 resolution (`TERMINATED_MATCH_CANNOT_RESOLVE`).
