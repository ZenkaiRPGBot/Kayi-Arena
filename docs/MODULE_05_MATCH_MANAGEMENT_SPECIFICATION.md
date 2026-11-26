# Kayi Arena — Module 5: Challenge & Match Management Specification

## 1. Public Interfaces (`app/matches/`)

- `MatchManager(db, *, dataset_kind=DatasetKind.PRODUCTION, timeout_policy=None, clock=None, draw_source=None, universe_rng=None, eligibility_checker=None)`
- **Challenge operations:** `handle_draft_command()`, `create_challenge()`, `accept_challenge()`, `cancel_challenge()`, `expire_challenge()`.
- **Draft & lifecycle operations:** `shuffle_match()`, `skip_match_character()`, `assign_match_role()`, `forfeit_match()`, `resolve_match_now()`.
- **Inactivity & external termination:** `handle_turn_timeout()`, `claim_inactivity_victory()`, `handle_claim_window_timeout()`, `terminate_match_externally()`.
- **Retrieval & `/game` support:** `get_challenge()`, `get_match()`, `get_active_match_for_player()`, `attach_message_reference()`.

## 2. State Transitions

- **Challenge states:** `open` → `accepted` | `cancelled` | `expired`.
- **Match lifecycle states:** `drafting` → `completed` | `forfeited` | `inactivity_win` | `abandoned` | `terminated_admin` | `terminated_technical`.
- Only `completed` drafts enter Module 3 (`resolve_completed_draft`). Prematurely terminated matches never enter normal resolution and never fabricate 7-role matchups or combined totals.

## 3. Authorization & Concurrency Rules

- Self-challenges are forbidden (`SELF_CHALLENGE_FORBIDDEN`).
- Direct challenges: only `target_player_id` may accept; only `challenger_id` may cancel.
- Open challenges: any eligible player != `challenger_id` may accept; first acceptance wins atomically under `_global_lock`.
- Both players are revalidated at acceptance time and locked globally in `_active_match_by_player` (at most 1 active match per player across all chats/universes).
- Per-match `asyncio.Lock` serializes all match transitions; `expected_revision` (Module 1) and `expected_generation` (Module 5) reject stale controls.

## 4. Provisional Timeout Settings (Owner Decisions Still Required)

`ProvisionalTimeoutPolicy` defaults are **provisional** and not finalized gameplay rules:
- `challenge_ttl_seconds = 300.0`
- `turn_timeout_seconds = 90.0`
- `claim_window_seconds = 60.0`
- `allow_inactivity_claim = True`

**Approved invariants:** `skip_character` never resets `turn_started_at`; stale timeout callbacks (`expected_revision` / `expected_turn_number` mismatch) are rejected (`STALE_TIMEOUT_EVENT`) without altering state; mutual inactivity abandons with `winner_id=None`.

## 5. Future Integration

- **Module 6 (Telegram UI):** Renders `/draft` and `/game` from `DraftCommandSelection`, `ManagedMatch.public_view`, `generation`, and `message_refs`.
- **Module 7 (Persistence & Recovery):** Persists `ChallengeRecord` and `ManagedMatch` snapshots across restarts.
- **Module 8 (Profiles & Rankings):** Reads `MatchOutcomeSummary` (`reason`, `winner_id`, `loser_id`, `affects_rating`, `resolution`).
