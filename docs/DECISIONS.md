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
