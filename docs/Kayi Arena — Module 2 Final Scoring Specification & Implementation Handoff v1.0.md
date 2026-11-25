# Kayi Arena — Module 2: Final Scoring Specification & Implementation Handoff v1.0

Kayi Bots · Planning document, no implementation code · Finalizes Module 2A Draft v3 and Module 2B Draft v1

Labels: \[F\] approved · \[R\] proposed, approved together with this specification · \[D\] deferred · \[U\] unresolved

## 1. Scope and status

- **Preserved \[F\]:** Role Score = (Fit × Fit weight + Power × Power weight) ÷ 5; approved weights; Power 1–5; seven independent Fit ratings 0–5, all integers; no distribution caps; hidden exact ratings; one canonical version per character; the 2A evaluation framework.
- **Calibration status:** The 14 Naruto ratings are provisional Draft records. They are not production data and are not repeated here. Independent review confirmed all 98 role scores, totals, correlations and tie frequencies.
- **Testability:** The scoring engine must be implementable and testable with synthetic ratings alone. No approved character database is needed.
- **Out of scope:** tie-breaking, matchups, winners, rarity, schemas, code, production ratings.

## 2. Consistency corrections (2B §5, applied)

These supersede the conflicting text in 2A Draft v3. No approved decision is reopened.

**C1. Score range (2A §2 introduction).** Every score is a whole number between the role's minimum and 100. Minimums, reached by Fit 0 with Power 1: Captain 8, Strategist 3, Attacker 10, Tank 10, Assassin 7, Support 3, Healer 3. A score of 0 is not attainable.

**C2. Inclusion test (2A §6.3).** Classification depends on how an ability fails the four questions, not on how many limits it has.

- **Core:** all four answers are an unqualified yes.
- **Conditional:** the ability belongs to the version (Q4) and the character can use it by their own method (Q1, Q3), but Q1–Q3 carry one or more limits (time, cost, cooldown, terrain, preparation, partner, risk). Any number of limits keeps it Conditional. Limits lower its effect in the five-question weighing and never convert it to Excluded by count. Partner-dependent abilities are Conditional.
- **Excluded:** a flat no on Q1 (cannot be reused), Q3 (another being's ability, one-off help) or Q4 (outside the version). Fatal techniques are Excluded.
- If limits leave no reliable effect, the ability stays Conditional and yields no uplift.

**C3. Evidence grades (2A §7.4).** Grade A means the capability or outcome itself is shown in canon, with its effect, so a reviewer can point to the scene. Grade B means the rating needs a step beyond what is shown: an authoritative statement, or an inference that a shown capability would suffice in an unshown situation. The grade attaches to the evidence for the level claimed, not to the scene. One rating may use both: the shown capability is A, and the added inference is B and sets the ceiling for the increment that depends on it (one inferential step at most, §7.6). Example: Susanoo withstanding a major attack is A for durability; concluding it could hold a line for teammates is B. A role record is still not required for Fit.

**C4. Confidence (replaces 2A §7.9 table).**

| Level | Meaning |
| --- | --- |
| High | Two independent Grade A items, or one decisive and acknowledged Grade A item; no unresolved conflict; level not sensitive to a reasonable alternative reading |
| Medium | One Grade A item; or A plus B; or consistent, reliable Grade B (Grade A or authoritative premises, stated mechanism, one inferential step, no contradiction). Minor ambiguity allowed |
| Low | Grade C only; Grade B that is single-sourced, exceeds one inferential step or has a plausible alternative level; unresolved conflict; sparse evidence; adaptation-only support; level sensitive to the reading |

A justified exception to a default ceiling still requires at least Medium.

## 3. Scoring inputs, outputs and validation

### 3.1 Constants (scoring version SCORE-1.0)

| Role | Fit points per level | Power points per level | Min | Max |
| --- | --- | --- | --- | --- |
| Captain | 12 | 8 | 8 | 100 |
| Strategist | 17 | 3 | 3 | 100 |
| Attacker | 10 | 10 | 10 | 100 |
| Tank | 10 | 10 | 10 | 100 |
| Assassin | 13 | 7 | 7 | 100 |
| Support | 17 | 3 | 3 | 100 |
| Healer | 17 | 3 | 3 | 100 |

These are the approved percentage weights divided by 5 (Captain 60/40, Strategist 85/15, Attacker 50/50, Tank 50/50, Assassin 65/35, Support 85/15, Healer 85/15). Score = Fit × Fit points + Power × Power points, in integer arithmetic.

### 3.2 Input

One rating record: **character\_id** (non-empty string), **power** (integer 1–5), **fit** (exactly seven integer values, 0–5, keyed captain, strategist, attacker, tank, assassin, support, healer). The scoring configuration (constants above plus scoring version) is a separate, versioned input.

### 3.3 Output

Per record: character\_id, power and the seven Fit values passed through unchanged, the seven integer role scores, and the scoring version. The engine produces no totals, ranks, tie-breaks, rarity or winners. Module 3 uses Fit and Power separately as tie-break keys \[D\].

### 3.4 Behavior rules

- Pure and deterministic: same input and configuration give identical output. No randomness, clock, network or storage access.
- Integer arithmetic only. No rounding, no decimals, no clamping. Calculated scores are never edited.
- Ignores evidence, confidence and approval status. Those belong to the dataset layer (§4).
- Never mutates input. Output for a record is independent of other records and of batch order.
- Roles are independent: changing one Fit value changes only that role's score.

### 3.5 Validation rules

Batches are all-or-nothing. A failing batch returns every error with record identifier and code, and no scores.

| Code | Rule |
| --- | --- |
| V01 | Record missing a required field or containing an unknown field |
| V02 | power or any Fit value is not an integer type (reject floats, including 3.0, strings, booleans, null) \[R\] |
| V03 | power outside 1–5 |
| V04 | fit keys are not exactly the seven roles |
| V05 | any Fit value outside 0–5 |
| V06 | character\_id empty or duplicated within the batch |
| V07 | configuration invalid: not exactly seven roles, Fit and Power percent weights not summing to 100, or a weight not a multiple of 5 |
| V08 | computed score outside the role's min–100 range (internal check; must be unreachable with valid input) |

## 4. Dataset and scoring version requirements

**Scoring version.** Identifies the formula, weights, rating ranges, role list and arithmetic rule. Immutable once published. Any change to these is a new scoring version, and weight changes need your approval (2A §2.6).

**Dataset version manifest (logical requirements, not a schema):**

| Element | Requirement |
| --- | --- |
| Identifier | Opaque, unique |
| Kind | production, sandbox or test |
| Scoring version | Exactly one |
| Records | character\_id, power, seven Fit values, role scores, record status and revision reference |
| Governing versions | Universe policy, anchor set and calibration set versions in force |
| Integrity | Content hash |
| Created | Timestamp, with predecessor identifier if any |

**Rules:**

- **DV1.** Production versions contain Approved records only. Sandbox and test versions may contain Draft records. Test and synthetic versions are never promoted to production.
- **DV2.** A published version is never modified. Any correction creates a new version.
- **DV3.** The hash is verified on every load. A mismatch fails closed.
- **DV4.** Stored role scores must equal the engine's recomputation at publication. A mismatch blocks publication \[R\].
- **DV5.** A version stays retrievable and unchanged for every active and past match that used it (retention by Module 4).
- **DV6.** The identifier is opaque to Modules 1 and 3.
- **DV7.** One character\_id appears at most once per version (one canonical version per character).
- **DV8.** Changing the scoring version requires a new dataset version.

## 5. Interfaces

| Module | Receives from Module 2 | Must not |
| --- | --- | --- |
| 1 (engine) | Nothing beyond storing the opaque dataset version identifier | Read, interpret or cache ratings; assume identifier structure |
| 3 (match resolution) | Read access, by dataset version and character\_id, to Power, seven Fit values and seven role scores from the version the match started on | Recompute with a different scoring version; modify ratings; resolve a match against any other version. Tie-breaking, matchups and winners are Module 3 work |
| 4 (data) | Scoring version, validation rules (§3.5), manifest requirements (§4) | Publish production versions with non-Approved records; edit published versions; use rarity as a scoring input |

Module 4 supplies Approved records and stores versions. Rarity, healer-capable pool standards and the final evidence record schema are Module 4 work \[D\].

## 6. Automated tests and acceptance criteria

All tests use synthetic ratings and require no production data.

| ID | Test | Pass criterion |
| --- | --- | --- |
| T1 | Exhaustive: all 30 Fit × Power pairs in each of 7 roles (210 cases) against an independently written expected table | 210 of 210 exact |
| T2 | Range: minimum and maximum per role | Minimums 8, 3, 10, 10, 7, 3, 3; every maximum 100; no score of 0 |
| T3 | Distinct scores per role across the 30 pairs | Captain 22, Strategist 30, Attacker 10, Tank 10, Assassin 30, Support 30, Healer 30 |
| T4 | Uniform equal-score probability | Attacker and Tank 12.2%, Captain 5.1%, others 3.3% (one decimal) |
| T5 | Properties: monotonic in Fit and Power; in Strategist, Support and Healer one Fit level outweighs any Power gap (17 > 12); Attacker and Tank swap Fit and Power equivalently; role independence | Zero violations over the full grid |
| T6 | Negative validation: at least two cases per code V01–V07 | Every case rejected with the exact code; no scores emitted; no false rejections of valid records |
| T7 | Determinism: same batch run three times, and in reversed order | Identical per-record output; no input mutation |
| T8 | Pass-through: Fit and Power in output | Equal to input for every record |
| T9 | Regression: the 14 calibration rating sets from 2B §2.1 | 98 of 98 scores equal 2B §2.2. This tests arithmetic only and does not validate or approve any rating |
| T10 | Version rules: hash mismatch, mixed scoring versions, Draft record in production kind, duplicate character\_id, stored score mismatch | Each blocked (DV1, DV3, DV4, DV7, DV8) |
| T11 | Replay: publish version B after A, resolve a match started on A | Uses A's contents and scoring version unchanged |
| T12 | Diagnostics (advisory): correlation, roles at Fit 4 or higher, tie counts computed on synthetic sets; report marked insufficient sample below 50 approved characters across several universes \[R\] | Values match hand calculation; no rating or score changes; never blocks publication |

**Acceptance:** Module 2 is accepted when T1–T12 pass, every validation code has a covering negative test, and an implementer who has only this document and Module 2A reproduces T1–T3 independently.

## 7. Unresolved character-specific decisions for Module 4

All calibration ratings remain provisional. Every cited reference in 2B is unverified or located by index only (Tier 4), so none can support approval. The independent review required by 2A §7.10 has not been run on the six records with Power 5 or Fit 5.

| ID | Decision | Why it matters |
| --- | --- | --- |
| U1 | Naruto: include or exclude Six Paths Sage Mode (N-1, currently excluded as a one-time grant) | Most rating-sensitive policy call; may raise Attacker, Tank and Support |
| U2 | Tank suitability for Naruto and Sasuke (currently 3, alternative 4) | Possible underrating. Durability is shown (Grade A), but holding a line for others needs a Grade B step under C3 |
| U3 | Tank 4 for Itachi and Gaara; Assassin 4 for Kakashi and 3 for Hinata | Capability-based inference; reviewers may differ by 1 |
| U4 | Naruto Support 4 (depends on Kurama's cooperation) | Reclassify under C2 as Conditional, partner-dependent; confirm weighing |
| U5 | Healer 1 for Naruto, Hinata and Ino on unverified Grade C evidence | Likely unevidenced 0 unless a scene is verified |
| U6 | Power 5 and Fit 5 exceptions (for example Naruto and Sasuke Power; Shikamaru Strategist 5) | Need independent review and verified second demonstrations |
| U7 | Madara version (Rinne Tensei-revived, Ten-Tails Jinchūriki) | Large swing from policy, not rubric |
| U8 | Edo Tensei handling for Itachi and Minato (living version as ECV) and for Kabuto's planning credit | Policy swing; confirm persisting-trait use under 2A §6.6 |
| U9 | Sasuke Captain 2 versus 3; Rock Lee Power 3 versus 4 (Gate weighing); Ino Support 4 versus 5 | Adjacent-level doubt; lower level stands unless evidence is verified |
| U10 | Reapply C2 and C3 to all 14 records, then re-confirm confidence under C4 | Corrections change classification and confidence wording, not formula |

## 8. Final decision register

| # | Decision | Status |
| --- | --- | --- |
| F1 | Formula, weights, Power 1–5, Fit 0–5, integer ratings, seven roles, no caps, hidden ratings | \[F\] unchanged |
| F2 | Healer self-only regeneration is Fit 0; trivial first aid is Fit 1 (2A D1) | \[F\] |
| F3 | Evidence grades with default ceilings and justified exceptions (D2) | \[F\] as revised, with C3 and C4 |
| F4 | Fit rated first with Power hidden (D3); universe-relative standard (D5) | \[F\] |
| F5 | Conditional abilities weighed on actual effectiveness, no numeric cap (D4) | \[F\] as revised, with C2 |
| F6 | Role suitability evidence, no role record required (D6) | \[F\] as revised |
| F7 | Adaptation-only content excluded by default (D7); doubt takes the lower level (D8); Approved only in production | \[F\] |
| F8 | Diagnostics advisory only (D9); AI-assisted review with human batch approval (D10) | \[F\] |
| F9 | Naruto is the calibration universe, not a confirmed roster; original work is the primary medium | \[F\] |
| A1 | Corrections C1–C4 | Applied per your instruction |
| R1 | Strict integer typing (V02) | \[R\] |
| R2 | Scoring version separate from dataset version, one per dataset (DV7, DV8) | \[R\] |
| R3 | Scores precomputed at publication and verified by recomputation (DV4) | \[R\] |
| R4 | Engine ignores status; production eligibility enforced at dataset layer (DV1) | \[R\] |
| R5 | Diagnostics suppressed below 50 approved characters across several universes | \[R\] |
| D1 | Tie-breaking, matchups, winners | \[D\] Module 3 |
| D2 | Rarity, healer-capable pool standards, evidence record schema, version retention | \[D\] Module 4 |
| D3 | 55/45 weight split for Attacker and Tank | \[D\] not recommended |
| U1–U10 | Character-specific decisions (§7) | \[U\] Module 4 |
