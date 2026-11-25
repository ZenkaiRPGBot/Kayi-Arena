# Module 1 — Core Drafting Engine Specification (Final v1.0)

Kayi Bots · Anime Draft Bot · Planning document, no implementation code

**Labels used throughout:** **\[F\]** finalized and approved · **\[T\]** technical default adopted in this specification, no gameplay impact · **\[D\]** deferred to another module.

## 1. Executive summary

The Core Drafting Engine is a pure rules module. Given a valid match configuration and a character pool, it runs a 1v1 draft from the first shuffle to two complete seven-role teams, and nothing else. It knows nothing about Telegram, databases, ratings or winners.

Status: Final v1.0. All eight recommendations from Draft v1 are approved and seven technical inconsistencies found in review are resolved (see the change summary below). No gameplay rule changed, and no decision remains open for Module 1.

Key facts the spec guarantees:

- A draft always ends after exactly 14 assignments, taking at most 36 accepted drafting actions.
- A draft can never deadlock given a valid pool (at least 14 characters).
- Every rejected action leaves state untouched.
- Every accepted action advances a revision number, which makes stale, duplicate and simultaneous requests safe.
- Players only ever see a public view that excludes the pool, odds, ratings and randomness. The engine itself never holds Power or Role Fit ratings.

No decisions remain open for your approval. Matters deferred to other modules are listed in Section 13.

## Change summary: Draft v1 to Final v1.0

- **Approvals recorded \[F\]:** rarity-first drawing with renormalization, no player-order compensation for now, hard minimum of 14 characters, skip rejected when no alternative exists, persist-before-reveal, frozen catalog snapshots with revision-based validation and serialized per-match actions, exclusion of the last-skipped character from exactly the next draw, and the product-level minimum pool deferred to Module 4.
- **Randomness and restoration \[T\]:** production recovery preserves committed draws only, snapshots hold no random state, and tests own their draw source (Section 5.4). Acceptance criterion 4 was reworded to match.
- **Public versus internal state \[T\]:** a new Section 5.5 defines the internal snapshot and the public player-facing view. The earlier claim that the state holds no secrets was removed.
- **Termination invariant \[T\]:** Terminate releases any held character to the pool. The held-character invariant now applies to active matches, and terminal states hold no character.
- **Termination authorization \[T\]:** drafting actions and Terminate now have separate validation. The engine neither authorizes callers nor decides winners (Section 4.3).
- **Data version consistency \[T\]:** the engine stores an opaque dataset version and returns it to Match Resolution, so mid-match data updates cannot change a result.
- **Skip history \[T\]:** removed. Players see remaining skip counts only, and the engine keeps no action or skip history.
- **Strategic simulations \[D\]:** first and second-player evaluation, including strategic play, is deferred to Module 3.
- **Unchanged:** all gameplay rules, the seven roles, the state machine, drawing rules and module boundaries.

## 2. Review of existing gameplay decisions

### 2.1 What works

- Alternating turns with a skip that keeps the turn is simple and cannot desync.
- A shared pool with unique characters creates real interaction: what you take, the opponent cannot have.
- Public teams and rarity with hidden ratings reward anime knowledge rather than memorized numbers.
- Two skips is enough to matter without allowing rarity farming. A player sees at most 9 characters in total.
- Manual Shuffle costs the engine nothing and is easy to model.

### 2.2 Ambiguities and their resolutions

1. **"A turn normally ends when…"** The only way a turn ends is assignment. The only other exit is termination. \[T\]
2. **"Immediately following draw must not return the skipped character."** Since a skip keeps the turn, the next draw is always the same player's. The exclusion applies to exactly the next draw, then clears. A third draw can return the character. \[F\]
3. **"Draft can always be completed."** A valid pool has at least 14 unique characters, each in a positively weighted rarity (Section 6.5). \[F\]
4. **Draft end timing.** The starter takes turns 1, 3, … 13 and the other player takes 2, 4, … 14. The draft therefore ends on the non-starter's seventh assignment. No player ever finishes early or needs a skipped turn. This is an invariant, not a rule to add.
5. **"No timer reset on shuffle/skip"** means one turn can contain up to three draws plus an assignment inside one deadline. The engine does not own timers (Section 9). \[T\]
6. **Mid-match data edits.** The engine freezes the catalog snapshot (character id and rarity id) at match start \[F\] and stores an opaque dataset version that pins the Power and Role Fit data used later by Match Resolution \[T\].

### 2.3 Problems found and resolved

- **Deadlock edge case.** Suppose exactly one character remains and the player skips it. The skipped character returns to the pool, but the no-immediate-redraw rule excludes it, leaving nothing to draw. This only happens when the pool is at its minimum size. **Resolved \[F\]:** a skip is rejected unless at least one other character is available besides the held one.
- **Re-roll via crash.** If the bot restarts after a draw is revealed but before it is saved, recovery could redraw. This breaks your "recovery must not grant redraws" rule. **Resolved \[F\]:** persist before reveal (Section 9.4).

### 2.4 Strategy risks (no mechanic added)

| Concern | Verdict |
| --- | --- |
| Rarity hunting via skips | Limited to 2 skips. Acceptable. |
| Saving skips for the final role | A real, interesting decision. Keep. |
| Denial drafting (parking a strong character in a useless role) | Costs the player a role. Keep. |
| Stalling | Handled by timers in Module 5. |
| Second-player information edge | Unproven. Measure first (Section 8). |

## 3. Recommended complete drafting rules

Rules marked \[F\] are finalized and approved. Rules marked \[T\] are technical defaults that do not change gameplay.

- **D1 \[F\]** Two players, seven roles each: Captain, Strategist, Attacker, Tank, Assassin, Support, Healer. One character per role, and each character is used once.
- **D2 \[F\]** The starting player is chosen randomly after the match enters drafting. Turns strictly alternate.
- **D3 \[F\]** On your turn, press Shuffle to reveal one character. You must then assign it to an empty role or skip.
- **D4 \[F\]** You have 2 skips. A skip returns the character to the pool and you keep your turn.
- **D5 \[F\]** The character you just skipped cannot be returned by your very next draw. After that draw, the restriction clears.
- **D6 \[F\]** A skip is not allowed if no other character is available besides the one you are holding.
- **D7 \[F\]** Assignment is permanent.
- **D8 \[F\]** Both players see both teams, remaining roles, remaining skips, and the held character with its rarity. Exact ratings are never part of the engine or its public view.
- **D9 \[T\]** Remaining skip counts are public. The engine keeps no skip history.
- **D10 \[F\]** The draft is complete when both teams have seven characters. The engine then hands off two teams and stops.
- **D11 \[T\]** A draft may also end early by external termination with a reason (forfeit, inactivity, abandonment, cancellation, administration). Termination releases any held character. The engine records the reason but does not choose winners or check permissions.
- **D12 \[F\]** Each draw selects a rarity among those that still have eligible characters, then a character uniformly within it.
- **D13 \[F\]** A draft requires a pool of at least 14 unique characters.

## 4. State machine and action transitions

### 4.1 States

| State | Meaning |
| --- | --- |
| AWAITING\_SHUFFLE | Active player must Shuffle. No character is held. |
| AWAITING\_DECISION | A character is held. Active player must Assign or Skip. |
| COMPLETED | Both teams are full. Terminal. |
| TERMINATED | Ended externally. Terminal. |

Phase is derived. While the match is active, the phase is AWAITING\_DECISION if and only if a character is held, otherwise AWAITING\_SHUFFLE. Terminal states hold no character.

### 4.2 Transition table

| # | From | Action (actor) | Guards | To | Effects |
| --- | --- | --- | --- | --- | --- |
| 1 | — | StartDraft (caller) | Valid config | AWAITING\_SHUFFLE | Pick starter, skips = 2 each, empty teams, pool = full catalog, store dataset version, revision 0 |
| 2 | AWAITING\_SHUFFLE | Shuffle (active player) | Eligible set non-empty | AWAITING\_DECISION | Draw character, remove from pool, hold it, clear last-skipped |
| 3 | AWAITING\_DECISION | Assign role (active player) | Role is empty | AWAITING\_SHUFFLE, or COMPLETED when 14th assignment | Place character, clear held, switch active player |
| 4 | AWAITING\_DECISION | Skip (active player) | Skips left > 0 and another character is available | AWAITING\_SHUFFLE (same player) | Skips − 1, return character to pool, set last-skipped |
| 5 | Any non-terminal | Terminate (external authority) | Active match, known reason | TERMINATED | Release any held character to the pool, clear last-skipped, store terminal record, revision + 1. Teams and skips unchanged |
| 6 | COMPLETED or TERMINATED | Any action | — | unchanged | Reject MATCH\_NOT\_ACTIVE |

### 4.3 Validation order

**Drafting actions (Shuffle, Assign, Skip).** Check in this order and return the first failure: match active → player belongs to the match → revision is current → player is the active player → action allowed in this phase → action-specific guards.

**Terminate (external authority only).** Terminate is not a player action and is never exposed to players directly. Match Management, inactivity handling or administration call it, and a player's forfeit request reaches the engine only through Match Management. The engine does not check permissions and does not decide winners. It validates only that the match is still active (else MATCH\_NOT\_ACTIVE), that the reason is a known code (else INVALID\_REASON), and that the optional subject player, if given, belongs to the match (else UNKNOWN\_PLAYER). There is no revision check, so termination always applies to the latest state.

Terminate is serialized with drafting actions. Whichever is processed first wins, and any drafting action processed afterward is rejected with MATCH\_NOT\_ACTIVE. The terminal record stores the reason, the optional subject player, a source label, a caller reference (all opaque) and the character that was held at termination, if any. \[T\]

### 4.4 Lifecycle walkthrough

1. Match enters drafting, starter chosen, state is AWAITING\_SHUFFLE.
2. Starter shuffles and a character is revealed.
3. Starter either assigns (turn passes) or skips (shuffles again).
4. After an assignment, the other player is now active in AWAITING\_SHUFFLE.
5. After 13 assignments the starter has finished. The other player takes the last turn.
6. After the 14th assignment the state is COMPLETED and teams go to Match Resolution.
7. At any point before that, a forfeit or inactivity ends the match as TERMINATED.

## 5. Logical game state requirements

### 5.1 Must be stored

| Item | Notes |
| --- | --- |
| Match id | Opaque. |
| Players (ordered pair) | Opaque ids. |
| Universe id and game mode | Pass-through. The engine does not interpret mode. |
| Draft config snapshot | Rarity weights, skips per player, role list. |
| Catalog snapshot | List of (character id, rarity id) frozen at start, plus an opaque dataset version that pins the Power and Role Fit data used later by Match Resolution. |
| Starting player | Stored explicitly so replays do not depend on RNG. |
| Both teams | Role to character id. |
| Skips remaining per player |  |
| Held character (or none) | Must survive restarts. |
| Last-skipped character (or none) |  |
| Match status and terminal record (reason code, subject player, source label, caller reference, character held at termination) |  |
| Revision | Increments on every accepted action. |
| Caller-supplied timestamps | Opaque. Only so Module 5 can compute deadlines. |

### 5.2 Derived, not stored

- Active player (from starter and number of assignments).
- Turn number.
- Phase.
- Available pool (catalog minus assigned minus held).
- Remaining roles per player.
- Progress (assignments out of 14).
- Whether a skip is currently allowed.

### 5.3 Event and skip history

The engine keeps no action history and no skip history. Every accepted action returns events (action, actor, revision, character shown), so Persistence, Profiles or the UI can build whatever history they need. Players see remaining skip counts only. Core gameplay does not need a visible skip history, so none is required. \[T\]

### 5.4 Randomness

**Production recovery preserves committed results, not random generators.** A draw is committed when its result (the held character) is saved together with the new revision, and it is revealed only after that save (Section 9.4). After a restart the engine restores the saved state exactly. A Shuffle that was never committed was never revealed, so drawing again afterward reveals nothing that was lost and grants no advantage. Snapshots therefore contain no random-number state, no seed and no draw history. \[T\]

**Tests control randomness through an injected draw source.** The contract: starting-player selection makes one call to the source, and each Shuffle makes exactly one call, passing the eligible characters with their rarity weights. Production uses an unpredictable system source and never records a seed. Tests use a seeded or scripted source owned by the test harness. To compare an interrupted draft with an uninterrupted one, the harness restores its own source to the matching position. The engine itself never persists or restores randomness. \[T\]

### 5.5 Internal snapshot versus public view

The engine produces two different projections of the same draft. The public view is a pure function of the internal state and adds nothing to it. \[T\]

| Item | Internal snapshot (persistence) | Public view (players and UI) |
| --- | --- | --- |
| Match id, players, universe, mode | Yes | Yes |
| Status, phase, revision, active player, progress | Yes | Yes |
| Both teams (role to character id) | Yes | Yes |
| Remaining roles and remaining skips | Yes | Yes |
| Held character and its rarity id | Yes | Yes |
| Last-skipped character | Yes | No |
| Available pool contents | Yes (derivable) | No |
| Catalog snapshot, rarity weights, draw probabilities | Yes | No |
| Dataset version | Yes | No |
| Timestamps and caller references | Yes | No |
| Terminal record | Yes | Reason code and subject player only |
| Power, Role Fit, scoring weights | Never held by the engine | Never |
| Random seed or draw-source state | Never stored | Never |

Rules:

- Persistence uses the internal snapshot only. The UI receives the public view only and never the raw snapshot.
- Future draws cannot be predicted from the public view, because it exposes neither the pool contents nor the odds, and production randomness is unseeded.
- Exact ratings cannot leak from the engine because it never holds them. Match Resolution looks them up at the end using the dataset version.
- Whether the UI should show any remaining-pool information is a Module 6 product decision \[D\]. Any new public field requires a change to this specification.

## 6. Character drawing and pool management

### 6.1 Intended behavior

1. Eligible set = available pool minus the last-skipped character (if set).
2. Choose a rarity among the rarities that still have eligible characters, weighted by the configured rarity weights.
3. Choose uniformly among eligible characters of that rarity.

When a rarity runs out, its weight is dropped and the remaining weights renormalize. Probability of rarity *t* = its weight ÷ the sum of weights of non-empty rarities.

### 6.2 Rarity-first versus single-stage weighting

| Approach | Advantage | Disadvantage |
| --- | --- | --- |
| **A. Rarity first, then uniform within rarity (recommended)** | Designers set intended odds per rarity ("X% of draws are rare") independent of universe size. Easy to explain to players. | Odds shift as rarities empty. Few-character rarities deplete quickly. |
| B. One weight per character | Single step, simple to code. | Rarity odds then depend on how many characters a universe has in each tier, so universes feel different. |

**Approved \[F\]: Approach A.** Depletion is a feature, since the pool genuinely shrinks as the draft proceeds, but it must be documented.

### 6.3 Held, skipped and assigned characters

- A held character leaves the pool immediately, so the opponent cannot affect it.
- A skipped character returns to the pool and is only excluded from the very next draw.
- Assigned characters are permanently removed.
- Consecutive skips are allowed: after skipping A and drawing B, skipping B excludes B only, so A is eligible again.

### 6.4 Exposed distribution function

The engine should expose a pure function returning the exact probability of every eligible character in a given state. Tests can then verify expected odds exactly, rather than only statistically, and balance analysis uses the same function.

### 6.5 Valid pool and exhaustion

- A valid pool has at least 14 unique characters (hard minimum \[F\]), each assigned to a rarity with positive weight.
- With 14 characters the last draw sees exactly one character, so the skip guard (D6) is required.
- At any AWAITING\_SHUFFLE, pool size is at least 1 and the eligible set is non-empty, so exhaustion is impossible for valid pools.
- Small pools reduce the value of skips because opponents consume much of the pool. The product-level minimum pool size is deferred to Module 4 \[D\]. The engine enforces only the hard minimum of 14.

## 7. Action validation and exploit prevention

Every rejection returns an error code and the current state, never changes state, and never consumes a skip.

| Scenario | Result |
| --- | --- |
| Opponent presses Shuffle | NOT\_YOUR\_TURN |
| Second Shuffle while a character is held | WRONG\_PHASE |
| Assign with nothing drawn | NO\_CHARACTER\_DRAWN |
| Skip with nothing drawn | NO\_CHARACTER\_DRAWN |
| Assign to occupied role | ROLE\_OCCUPIED |
| Unknown role name | INVALID\_ROLE |
| Skip with 0 skips | NO\_SKIPS\_REMAINING |
| Skip that would leave no draw | SKIP\_NOT\_POSSIBLE |
| Request from an earlier turn or button | STALE\_REVISION |
| Repeated button press | STALE\_REVISION (first press already advanced revision) |
| Simultaneous skip and assign | Serialized per match: first accepted, second STALE\_REVISION |
| Action after completion or termination | MATCH\_NOT\_ACTIVE |
| Unknown player | UNKNOWN\_PLAYER |

**Terminate errors \[T\]:** MATCH\_NOT\_ACTIVE (already completed or terminated), INVALID\_REASON, UNKNOWN\_PLAYER. Terminate is validated separately from drafting actions (Section 4.3), takes no revision check, and is processed in the same per-match order as drafting actions.

**Concurrency rule \[F\]:** each match processes actions one at a time, and every action carries the revision the caller last saw.

**Retries \[T\]:** a caller that did not receive a response simply fetches current state. No separate request-id memory is needed.

**Restart while a character is held \[T\]:** restoring the saved state keeps the held character. Shuffle is rejected (WRONG\_PHASE), and the UI re-displays the same character. No skip is granted or lost.

## 8. Fairness and strategic considerations

- **Random starter.** Fair by symmetry. The starter gets first access to rare draws, while the second player reacts to more information on each role. Whether these cancel out is an empirical question. No compensation for now \[F\]. Evaluation is deferred to Module 3 \[D\].
- **Alternating turns and shared pool.** Interaction without a complicated mechanic. Keep.
- **Public teams.** Allows counter-picking in role matchups. Keep.
- **Permanent assignment.** Gives real weight to every placement. Keep.
- **Two skips.** Creates the "spend early or save for the last role" tension. Keep.
- **Hidden ratings, visible rarity.** Rarity is an honest hint while placement stays a knowledge test. Keep.
- **No guaranteed role-specific draws.** Accepted per your decision. Healer scarcity risk lives in Module 4 data composition, not in this engine.
- **Different knowledge levels.** Intended. The game rewards knowledge.
- **Rarity hunting.** Bounded. At most 2 skips means at most 9 characters seen.
- **Last-role forced assignment.** The final role is always forced, so skip timing matters most late. That is strategic depth, not a flaw.

## 9. Module interfaces and dependencies

### 9.1 Inputs to the engine

- **From Challenge & Match Management:** match id, ordered players, universe id, mode (pass-through), and later Shuffle, Assign and Skip actions carrying the expected revision. Separately, Terminate requests from authorized external services only. A forced starting player is accepted for tests only.
- **From Character Database:** a frozen list of (character id, rarity id), rarity weights, and one opaque dataset version that identifies the exact Power and Role Fit data for this match. The engine stores the version and never reads ratings.
- **From Persistence & Recovery:** a stored internal snapshot to restore, validated against the invariants.
- **From the host application:** an injected draw source (production: unpredictable; tests: seeded or scripted).

### 9.2 Outputs

- **To Telegram UI:** the public view (Section 5.5) plus the events from each action. Nothing else.
- **To Match Resolution:** on COMPLETED only: match id, universe id, mode, starting player, dataset version, and both complete teams (role to character id). Match Resolution must read ratings from that dataset version, so later data updates cannot change the result. Keeping dataset versions retrievable is a Module 4 responsibility \[D\].
- **To Persistence:** the internal snapshot and revision after every accepted action.
- **To Match Management:** the terminal record when a draft is terminated.

### 9.3 Terminate boundary

The engine accepts Terminate(reason, optional subject player, source label, caller reference). Reasons: forfeit, inactivity of one player, both inactive, cancelled, administrative. Authorization belongs to Match Management and Administration, not to the engine. The engine validates only as described in Section 4.3, releases any held character, and stores the terminal record. Match Management decides winners and abandonment outcomes.

### 9.4 Commit protocol \[F\]

The engine takes a state and an action and returns a new state or an error. The caller must save the new state with compare-and-set on revision **before** revealing the drawn character to players. If saving fails, the action counts as not applied. This closes the re-roll exploit.

## 10. Independent testing plan

All tests use fictional pools and a controllable draw source. No Telegram or anime data.

### 10.1 Invariants (must hold after every accepted action)

1. Pool, held character, team A and team B are disjoint and together equal the catalog.
2. Each team has at most one character per role, and only the seven valid roles.
3. Assignment counts differ by at most one, and the starter is never behind.
4. Skips remaining is between 0 and 2, and never increases.
5. While the match is ACTIVE, a held character exists if and only if the phase is AWAITING\_DECISION. In terminal states no character is held and last-skipped is empty.
6. Active player equals the starter when total assignments are even, otherwise the other player.
7. Revision increases by exactly 1 per accepted action (drafting or Terminate) and never on rejection.
8. Last-skipped, when set, is in the pool, is set only while AWAITING\_SHUFFLE, and is excluded from the next draw.
9. COMPLETED implies both teams are full. Terminal states never change after entry.
10. A draw never returns an assigned or held character.
11. Whenever a Shuffle is legal, the eligible set is non-empty.
12. Accepted drafting actions in a draft never exceed 36 (14 assignments, at most 4 skips, at most 18 shuffles).
13. The public view never contains pool contents, rarity weights, probabilities, ratings, the dataset version or draw-source information.
14. The internal snapshot contains no random-number state, and the dataset version is unchanged from start to end.

### 10.2 Normal drafts

Scripted full drafts with no skips, with skips, and with both players using both skips at different moments. Verify final teams match the script.

### 10.3 Starting player

Both possible starters, via the forced-starter test hook, produce correct turn order. A seeded run confirms the starter is stored and does not change.

### 10.4 Skip behavior

Skip keeps the turn; counter decrements; last-skipped excluded from next draw only; consecutive skips; exhausted skips; skip rejected when no other character is available; skipped character may be drawn by the opponent later.

### 10.5 Role assignment and duplicates

Occupied role, invalid role, all roles filled in every order, same character never appears twice across any state.

### 10.6 Pool boundaries

Pools of 13 (rejected), 14 (valid), 15, and large. Single-rarity pool. Rarity with weight zero rejected. Rarity empties mid-draft. Duplicate ids rejected.

### 10.7 Weighted randomness

- Exact: verify the exposed distribution function against hand-computed values, including depletion renormalization.
- Statistical: with fixed seeds, 100,000 first draws match expected rarity frequencies (chi-square at p ≥ 0.001). Fixed seeds keep tests non-flaky.
- Uniformity within a rarity.

### 10.8 Invalid, repeated and simultaneous actions

Every error code in Section 7 has at least one test. Rejected actions leave a byte-identical snapshot. Simultaneous submissions (many parallel attempts of Skip and Assign) yield exactly one accepted action.

### 10.9 Restoration, termination and simulation

- **Restoration (production):** snapshot after every step of scripted drafts, restore, and continue with the same scripted actions. The restored state equals the saved state exactly. Results match the uninterrupted run when the test harness restores its own draw source to the matching position. Restoring while a character is held grants no skip and no redraw, and the held character is unchanged.
- **Draw source contract:** exactly one call for the starter and one per Shuffle. A scripted source flags any extra or missing call.
- **Termination:** each reason from each non-terminal state, including while a character is held (it is released to the pool, invariant 5 holds, and the terminal record is stored). Invalid reason and unknown subject player are rejected. Terminate needs no revision. Race tests: Terminate and Assign submitted together give a consistent result in either order. All later actions are rejected.
- **Public view:** projection tests confirm only the allowed fields appear (invariant 13), and that two different pools with identical public fields produce identical views.
- **Dataset version:** stored at start, never changes, and appears in the completed-draft output.
- **Large-scale simulation:** at least 100,000 random drafts across pool sizes 14–200 and varied bot behavior (never skip, always skip, random). Invariants checked after every action. Zero deadlocks.
- **Deferred to Module 3 \[D\]:** first and second-player advantage, including random-play baselines and strategic-play simulations (role placement and reacting to the opponent's team). The strategies are designed there, not here.

## 11. Acceptance criteria

The module is complete when all of the following are true:

1. All fourteen invariants hold across at least 100,000 simulated drafts with zero violations and zero deadlocks.
2. Every action in Section 4 and every error code in Sections 4.3 and 7 has automated tests.
3. The same seed (or scripted source) and action list always produce identical final state (verified by state hash).
4. A restored snapshot equals the saved state exactly at every step. Continuing with a draw source restored to the matching position reproduces the uninterrupted draft exactly. The snapshot contains no random-number state.
5. Exact probability checks pass for at least three depletion scenarios, and statistical rarity checks pass at p ≥ 0.001.
6. The module runs a complete draft using a fictional 20-character pool, with no Telegram, database or dataset imports.
7. A draft never exceeds 36 accepted drafting actions.
8. Rejected actions never change state, revision or skip counts.
9. In all tested states the public view contains only the fields listed in Section 5.5.
10. Termination from any non-terminal state, including with a held character, ends in a state that satisfies all invariants.
11. The decision register (Section 12) has no open decisions.

## 12. Decisions register

### Finalized \[F\]

Original gameplay decisions: two players, seven roles with one character each, unique characters, permanent assignment, random starter, strict alternation with no snake draft, manual Shuffle, one drawn character at a time, rarity-weighted drawing with visible rarity and hidden ratings, two skips that return characters and keep the turn, no immediate redraw, no timer reset, no pity or guaranteed role draws, one active match per player, and identical drafting in Ranked and Friendly modes.

Approved in the review of Draft v1:

- Rarity-first drawing, then uniform selection within the rarity, with renormalization when rarities become empty.
- No first-player or second-player compensation for now.
- Hard technical minimum of 14 unique characters.
- A skip is rejected when no alternative character is available.
- Persist-before-reveal to prevent free redraws after crashes.
- Frozen catalog snapshots, revision-based action validation and serialized per-match actions.
- The last-skipped character is excluded from exactly the next draw.
- The product-level minimum pool size is deferred to Module 4, and 28 is not adopted.

### Technical defaults adopted \[T\]

These have no gameplay impact.

- Production recovery preserves committed draws. Snapshots hold no random state, and tests supply their own draw source (Section 5.4).
- Internal snapshot and public view are separate projections (Section 5.5).
- Terminate releases any held character, and the held-character invariant applies to active matches.
- Drafting actions and Terminate are validated separately. The engine neither authorizes callers nor decides winners (Section 4.3).
- An opaque dataset version is stored and returned to Match Resolution.
- Public skip counts only. The engine keeps no skip or action history.
- The engine never reads a clock and never holds ratings.
- A turn ends only by assignment.

### Open decisions

None.

## 13. Deferred considerations \[D\]

| Module | Item |
| --- | --- |
| 2 Evaluation & Scoring | Rating consistency, rarity classification rules, and how Power and Role Fit data are defined and versioned. |
| 3 Match Resolution | Pairings, winner calculation and ties. Reading ratings from the dataset version in the completed draft. First and second-player advantage analysis, including random-play baselines and strategic simulations (role placement and reacting to the opponent's team), with the strategies designed there. |
| 4 Database | Product-level minimum pool size (28 not adopted), pool validity checks, keeping dataset versions immutable and retrievable for active and past matches, and healer-capable character data standards. |
| 5 Challenge & Match Management | Timers, inactivity and extension, forfeit authority, authorizing Terminate callers, one match per player, and delivering Terminate. |
| 6 Telegram UI | Revision in button data, link-preview images, showing public skip counts, and whether to show any remaining-pool information. |
| 7 Persistence | Compare-and-set saving, the persist-before-reveal implementation, restart recovery and message recovery. |
| 8 Profiles | Ranked rating, and statistics built from emitted events. |
| 9 Administration | Admin cancellation through Terminate and abandoned match cleanup. |

## Decisions requiring your approval

None. Module 1 is complete pending your read-through of Final v1.0. Module 2 has not been started.
