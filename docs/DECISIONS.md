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
