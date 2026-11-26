# Kayi Arena — Module 3: Match Resolution Specification (`RES-1.0`)

Preserved from finalized requirements and approved decisions **D1–D6**.

## 1. Scope & Resolution Version

- **Resolution version:** `RES-1.0`
- **Supported scoring version:** `SCORE-1.0` (obtained from the pinned dataset manifest, never supplied independently by Module 1).
- Pure, deterministic, instant match resolution over 14 assigned characters across 7 canonical roles (`captain`, `strategist`, `attacker`, `tank`, `assassin`, `support`, `healer`).
- Ranked and Friendly modes resolve identically. No combat simulation, random bonuses, role counters, team synergy, active abilities, or progressive reveals.
- Externally terminated drafts are handled by Module 5 and must never enter normal resolution.

## 2. Gameplay Resolution Rules

1. **Individual matchups (7 canonical roles):** Compare each character's assigned-role score (`SCORE-1.0`). Higher score wins (`player_1` or `player_2`). Equal scores produce `draw`; Power and Role Fit are never used as individual tiebreakers.
2. **Overall winner:**
   - Higher individual matchup victory count wins (`decided_by = matchup_count`).
   - If victories are equal, higher combined 7-role score wins (`decided_by = combined_score`). Combined scores never override more matchup victories.
   - If both victories and combined totals are equal, overall outcome is `draw` (`decided_by = none`).

## 3. Approved Decisions (D1–D6)

- **D1:** Store resolution version `RES-1.0` in every result.
- **D2:** Retain Power, assigned-role Fit, and assigned-role score for each matchup participant; full 7-role Fit vectors stay in the pinned dataset.
- **D3:** Module 4 must generate advisory dataset health reports (never blocking publication or forcing rating changes).
- **D4:** Fail fast on the first validation error using deterministic precedence (Stages 1–9).
- **D5:** Reverify stored scores during resolution using Module 2's existing validation/scoring logic.
- **D6:** Repeat strategic balance simulations using actual character datasets during Module 4.

## 4. Validation Precedence (Fail-Fast)

1. `MALFORMED_REQUEST` (Stages 1–4 perform zero dataset access)
2. `INVALID_ROLE` (exact lowercase canonical roles only; no silent normalization)
3. `INCOMPLETE_TEAM`
4. `DUPLICATE_CHARACTER`
5. `DATASET_NOT_FOUND`
5b. `DATASET_UNAVAILABLE` (only retryable error)
6. `DATASET_INTEGRITY_FAILURE`
7. `UNSUPPORTED_SCORING_VERSION` (`SCORE-1.0` only)
8. `CHARACTER_NOT_FOUND`
9. `CHARACTER_RECORD_INVALID`

Ordering within stages: `player_1` before `player_2`, canonical role order, unknown string keys lexicographically.

## 5. Canonical Serialization

- UTF-8 JSON (`ensure_ascii=False` — Unicode preserved directly in UTF-8 without `\uXXXX` escaping).
- Keys sorted at every level, compact separators (`","` and `":"`), no trailing newline.
- Plain base-10 integers, no floats/`NaN`/`Infinity`, no `null` values (optional `details` omitted when empty), `matchups` array in canonical role order, no timestamps or RNG.

## 6. Resolution Invariants (I1–I9)

- **I1:** `wins_player_1 + wins_player_2 + draws == 7`.
- **I2:** Exactly 7 matchups in canonical role order.
- **I3:** All role scores are valid integers.
- **I4:** `decided_by == matchup_count` iff victory counts differ.
- **I5:** `decided_by == combined_score` iff victory counts are equal and totals differ.
- **I6:** `decided_by == none` iff victory counts and totals are equal.
- **I7:** Equal victory counts require an odd number of drawn matchups (`1, 3, 5, 7`).
- **I8:** Swapping player slots, teams, and identity mappings mirrors the result.
- **I9:** Outcome depends only on the 7 assigned-role score pairs.

## 7. Worked Examples (1–6)

1. **Normal victory:** `[72, 57, 80, 70, 73, 74, 43]` (469) vs `[68, 43, 60, 60, 79, 57, 74]` (441) → P1 wins 5–2 (`matchup_count`).
2. **Victory despite lower total:** `[72, 57, 60, 60, 7, 3, 3]` (262) vs `[68, 43, 50, 50, 79, 94, 94]` (478) → P1 wins 4–3 (`matchup_count`).
3. **Drawn matchups:** `[72, 57, 80, 70, 73, 74, 43]` (469) vs `[72, 43, 80, 60, 79, 57, 74]` (465) → P1 wins 3–2 with 2 draws (`matchup_count`).
4. **Combined-score tiebreaker:** `[100, 43, 90, 80, 54, 43, 43]` (453) vs `[68, 57, 70, 60, 79, 74, 43]` (451) → 3–3–1, P1 wins (`combined_score`).
5. **Overall draw:** `[72, 43, 80, 60, 73, 54, 74]` (456) vs `[60, 43, 70, 70, 73, 66, 74]` (456) → 2–2–3, `draw` (`none`).
6. **All 7 drawn:** Identical valid role-score vectors, distinct character IDs → 0–0–7, `draw` (`none`).

## 8. Future Module Requirements Recorded

- Five rarity tiers: `Common`, `Uncommon`, `Rare`, `Epic`, `Legendary`.
- Eligible sentient non-human characters may be independently draftable.
- Module 4 must generate advisory dataset health reports (never blocking publication or forcing rating changes).
- Real-data balance simulations are required; alternative rarity distributions remain untested (prior synthetic simulations are not production balance evidence).
- Character image validation must occur before production publication, subject to final Module 4 specification.
- Current Naruto character catalogue and rarities are provisional.
- No artificial rating caps, mandatory healer availability, or pity systems.
- Externally terminated matches (Module 5) must never enter normal resolution.
