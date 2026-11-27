# Naruto Batch 005 — self-contained Claude evaluation assignment (corrected research package)

## Ready-to-use prompt

> You are evaluating **Naruto Batch 005 Stage 02** from the corrected research package. Work only from the files listed below. The earlier metadata-only package and its placeholder evaluation are preserved for reference but are **not** the evaluation basis.
>
> 1. Read `naruto_batch_005_research.json` (**62 research-ready candidates**), `naruto_batch_005_catalogue.json`, `naruto_batch_005_calibration.json`, `naruto_batch_005_image_manifest.json`, `naruto_batch_005_completeness_report.json` and `naruto_batch_005_selection_summary.json`. Read `NARUTO_BATCH_005_RESEARCH_REPORT.md` if present in the same delivery folder.
> 2. Apply the embedded `EVAL-FRAMEWORK-1.0`, `NARUTO-CANON-0.1`, `SCORE-1.0` boundary rules and `KA-IMPORT-1.0` output contract in this document.
> 3. Evaluate exactly the 62 `candidate_id` values in the research file, in order. Do not add, remove, merge or rename candidates. `naruto_batch_005_unresolved_candidates.json` and `Enma` are **not** part of this evaluation.
> 4. Use the two-pass procedure: **Pass A — Fit only, with Power values hidden** (use only `fit_reference` in the calibration file). **Pass B — Power** (then open `power_reference`). Do not revise Fit after seeing Power except to correct a documented factual error; cite the evidence, never the Power value.
> 5. Each research-ready record contains demonstrated capabilities and a traceable inspected-secondary source; 39 records also carry canonical chapter/episode/databook references checked against that page text. Primary manga, databook and anime material was not directly opened in Stage 01B. Treat page citations as leads, not primary quotations. If a rating depends on an unverified detail, grade it `C`, keep confidence low and prefer the supported lower level. Never invent feats.
> 6. Do not allocate rarity, role scores, matchups or publication status. Set `submit_for_review: true` for Draft records if the import contract requires it; that is **not** approval.
> 7. Output one JSON file named `naruto_batch_005_claude_evaluation.json` with exactly the structure in section 8. Return the JSON as a fenced code block and state that you used Fit-first/Power-hidden ordering.

## 1. Files in this self-contained package

| File | Purpose |
|---|---|
| `data/naruto_batch_005_research.json` | 62 gated research-ready records: canonical version, demonstrated abilities, capability summaries, limitations and traceable evidence. No ratings. |
| `data/naruto_batch_005_catalogue.json` | The same 62 identities with source URLs, aliases, debut/rank metadata and validated image records. |
| `data/naruto_batch_005_calibration.json` | Compact reviewed-draft anchors, split into fit-only and power sections for the two-pass workflow. |
| `data/naruto_batch_005_image_manifest.json` | Per-image URL, hash, dimensions, accessibility, identity-review and usage-permission status. |
| `data/naruto_batch_005_completeness_report.json` | Separate catalogue/artwork/research/evaluation/publication status. Research gate passed; evaluation and publication not started. |
| `data/naruto_batch_005_selection_summary.json` | Actual coverage: 156 researched, 87 initially ready, 62 final after canon/continuity/artwork exclusions; no padding. |
| `data/naruto_batch_005_unresolved_candidates.json` | Preserved partial, insufficient, continuity-sensitive, adaptation-only and artwork-failed candidates. Not for evaluation. |
| `data/naruto_batch_005_original_claude_evaluation.json` | Preserved earlier placeholder evaluation (1 Draft, 99 Held, Power 1 floors). Reference only; never import. |
| `data/naruto_batch_005_claude_assignment.md` | This document. |
| `docs/NARUTO_BATCH_005_RESEARCH_REPORT.md` | Coverage, source quality, exclusions, replacements and limitations. |

If delivered into one folder for Claude, use the bare filenames above.

## 2. Hard constraints

- Universe: `naruto`. Batch: `naruto-batch-005`. Framework: `EVAL-FRAMEWORK-1.0`. Canon: `NARUTO-CANON-0.1`. Scoring version referenced for boundary purposes: `SCORE-1.0`. Rarity version is out of scope.
- **No ratings or rarity exist in Stage 01B.** Claude creates the first real ratings.
- Power is an integer **1–5**. Each of the seven Role Fit values is an integer **0–5**.
- Seven roles only: `captain`, `strategist`, `attacker`, `tank`, `assassin`, `support`, `healer`.
- **No distribution caps.** Any number of characters may reach any level if evidence meets the standard.
- **Fit first, Power hidden.** General strength counts only in Power; no Fit rating may use "this character is strong" as its reason.
- Do not calculate or insert role scores, ECV scores or rarity. `SCORE-1.0`/Module 2 derives scores later.
- Do not evaluate, approve, reject or publish. Imported records are `draft`; `submit_for_review: true` only moves a draft toward review.
- Do not composite incompatible versions. Anime-only or game-only additions are excluded by default unless the research record's manga/databook references support the same capability.
- Rank, title, reputation and popularity are context only, not evidence of ability or leadership.
- For low-evidence minors, a defensible `Held`/Draft, low-confidence outcome is preferred to invented detail.

## 3. `NARUTO-CANON-0.1` — canon and version policy

1. **Source tiers.** Original manga is decisive. Official databooks and licensed novels/support material may clarify or support but cannot override clear manga. Official adaptations may confirm but adaptation-only additions are excluded by default. Wikis, games, films and fan material are not independent evidence.
2. **One Eligible Canonical Version (ECV) per character.** Use the `canonical_version` and `canonical_version_basis` supplied for each record. Choose a coherent period/state and state it explicitly in companion notes. The ECV is the character’s **prime**: the highest reasonably sustainable canonical state across a meaningful stretch of story time or multiple engagements, not a single peak moment.
3. **No cross-version compositing.** Abilities, techniques and equipment from rejected versions do not carry into the ECV. Persistent traits such as intelligence, training, experience and leadership habits may cross versions only if they do not depend on abilities the ECV lacks, and the source period must be noted.
4. **Ability classes.** Before an ability supports a rating, classify it:
   - **Core (C):** on demand/routine, repeatable, sustainable through a typical engagement, no unusual cost or outside help — counts fully.
   - **Conditional (K):** the character’s own repeatable ability but limited by time, cost, recovery, terrain, preparation, partner or risk — weigh accessibility, sustainability, cost and reliability; no fixed numerical cap.
   - **Excluded (X):** one-time, unrepeatable, externally dependent, borrowed, non-prime or outside the ECV — does not count.
   - Normal operating requirements (a healer touching a patient, a sensor’s range) are not conditions.
5. **Conditional test.** Ask: how effective when used; how easily reached; how long sustained and what recovery; what cost/risk; how reliably canon shows it working. Include only if reusable, sustainable, character-owned and within the ECV.
6. **Identity check.** Verify that the name, aliases and page identity match. Do not merge identities on macron/spelling similarity. In particular, `Kosuke` (Kirigakure Anbu) is unresolved and not in this package; `Kōsuke` the messenger toad was never selected. `Shin Uchiha` is unresolved because of clone-group/continuity ambiguity; `Shin` (Root, Sai’s brother) is a different selected identity.
7. **Artwork check.** The manifest confirms 63 valid images covering all 62 candidates. Artwork confirms the selected source record; it is not feat evidence and does not grant publication rights.

## 4. `EVAL-FRAMEWORK-1.0` — Power

**Definition:** “Power is a character's overall canonical combat effectiveness relative to their own universe, for the single eligible canonical version. It is judged by the threats the character can credibly defeat, neutralize or withstand, not by destructive scale alone, popularity or story importance. Power is the only rating where general strength counts.”

| Level | Meaning | Typical capability |
|---|---|---|
| **5 Apex** | Among the universe's top threats | Defeats or neutralizes almost any opponent, contends on even terms with the strongest. |
| **4 Elite** | A leading fighter | Defeats most high-level opponents; seriously challenged only by the very top. |
| **3 Strong** | Dependable high-level fighter | Handles most standard threats and competes with elites on favorable terms. |
| **2 Capable** | Trained fighter | Handles ordinary threats; outclassed by strong fighters. |
| **1 Limited** | Minimal or no combat role | Non-combatant, trainee, or fights ineffectively. |

- Assign the **highest level whose description is demonstrably met in typical high-stakes performance** within the ECV.
- Check coverage of offense, defence, mobility, utility and sustained performance. These are evidence categories, not added sub-scores.
- Ratings are outputs, never evidence. Judge opponents by their demonstrated capability, not their labels; evaluate outward from anchors; cut circular chains at anchors.
- Power is not a win guarantee. Counters and circumstances can create legitimate exceptions.
- Few scenes lower confidence, not necessarily the rating. An outlier that contradicts two or more independent demonstrations is excluded and logged.
- Default evidence ceilings: Grade A → up to 4; Grade B → up to 3; Grade C → up to 2. Higher levels require a justified exception with specific evidence, reliability explanation, failure condition, at least Medium confidence and an independent-review flag.

## 5. `EVAL-FRAMEWORK-1.0` — Role Fit

**Fit measures suitability, not whether the character formally held the role.** “Suitability, not occupancy.”

### Universal 0–5 scale

| Fit | Name | Meaning |
|---|---|---|
| **0** | None | No relevant capability, or canon shows the opposite. |
| **1** | Incidental | Relevant ability appears once or only in minor form. |
| **2** | Capable | Shown more than once/reliably within limits, but limited, conditional or below a dedicated member. |
| **3** | Competent | Performs the core function reliably at the standard of a dedicated member. |
| **4** | Excellent | Clearly above that standard under demanding conditions, acknowledged by canon or decisive in important outcomes. |
| **5** | Benchmark | Highest standard shown in the universe, decisive and corroborated. A small elite team under extreme stakes qualifies equally with a large command. |

Two zeros: **absent zero** = canon contradicts/makes the capability implausible; **unevidenced zero** = nothing found after a documented search. For roles with no evidence, use Fit 0 and record which kind.

### Role definitions and boundary tests

| Role | Core question | Counts | Does not count |
|---|---|---|---|
| **Captain** | Do others follow this character into hard situations, and does it work? | Command decisions, followers’ response, coordination, morale, accountability, delegation, calm under pressure. | Protagonist status, popularity, raw strength, rank/title without evidence of leading. |
| **Strategist** | Does this character's thinking change outcomes? | Multi-step plans, anticipation, exploiting information, adaptation, contingencies, success against stronger/better-informed opposition. | Book knowledge, general intelligence not applied tactically, leadership rank. |
| **Attacker** | Can this character drive an engagement offensively? | Initiative, offensive repertoire/range, defence-breaking, sustained pressure, finishing power, damage against resisting targets. | Durability, speed alone, intelligence, destruction without a resisting target, general strength. |
| **Tank** | Who takes the hit, and can they hold? | Durability, mitigation, shielding self/others by body or technique, interception, drawing/holding attention, blocking passage/position. | General combat strength, avoidance by speed alone, shields cast from a safe position (Support). |
| **Assassin** | Can this character reach and remove an unaware/protected target? | Stealth, infiltration, ambush, precision, reaching protected targets, targeted neutralization. | Speed, lethality or power alone; a formal assassination record is not required. |
| **Support** | Are allies measurably more effective with this character present? | Enhancement, sensing/information, communication, ally-helpful control, protection granted to others, rescue, transport, resource/energy sharing. | Restoring injuries (Healer), planning (Strategist), taking the hit (Tank). |
| **Healer** | Can this character restore someone else? | Treating injuries, curing poison/illness, reviving, caring for many people. | Self-regeneration, personal durability, temporary shields, restoring depleted energy. |

Boundary notes: Captain directs people in real time; Strategist designs/reads. Attacker applies open sustained pressure; Assassin uses covert targeted removal. Tank takes the threat; Support grants protection without taking the hit. Restoring energy is not healing. Self-only regeneration is **Healer Fit 0** but counts for Power/Tank durability.

### Condensed role level standards

- **Captain:** 1 led once/by default; 2 informal/situational mixed results; 3 recognized leader or repeated effective demanding leadership; 4 high-stakes coordination with notable success and canon recognition; 5 benchmark leadership under the universe’s most demanding conditions, decisive and standard-setting.
- **Strategist:** 1 one clever move; 2 sound instincts in own fights; 3 reliable reading/adaptation/planning on more than one occasion; 4 plans deciding important engagements against stronger/better-informed opposition; 5 benchmark plans overcoming severe disadvantage, repeatedly or defining with corroboration.
- **Attacker:** 1 minor/occasional offense; 2 offense exists but is not primary method; 3 reliable contributor who initiates/damages/finishes standard threats; 4 primary threat with varied or defence-breaking pressure against strong opponents; 5 benchmark offense against the most demanding defences.
- **Tank:** 1 minor toughness; 2 durable/protective with important weaknesses; 3 very durable personally or limited protective ability; 4 demonstrated protective/holding function in demanding conditions **or** exceptional reliable durability that would clearly let the character hold threats for teammates; 5 benchmark protection/holding against the universe’s most dangerous threats. Level 4 does not require repeated protection.
- **Assassin:** 1 one ambush/incidental stealth; 2 fast/lethal but not subtle, or stealth without precision; 3 competent stealth/precision/targeted neutralization; 4 reliable reaching/neutralizing with notable infiltration/ambush/precision; 5 benchmark against well-defended/difficult targets with clear corroboration.
- **Support:** 1 minor assistance; 2 occasional real help; 3 reliable utility improving allies; 4 strong enablement shaping outcomes; 5 team effectiveness depends on the character and otherwise-impossible results follow.
- **Healer:** 1 trivial first aid; 2 basic skill or limited healing of others; 3 competent treatment of serious injuries/ailments; 4 advanced healing of grave injuries or many people; 5 near-fatal/large-scale restoration or revival, repeatedly or in a defining case.

Default Fit ceilings follow the evidence grade: A → up to 4, B → up to 3, C → up to 2, contradicted/no evidence → 0. Fit 5 and B/Fit exceptions require the same documented exception standard as Power. Doubt rule: if two adjacent levels are equally supported, choose the lower, record the higher as plausible, and flag it.

## 6. Evidence grades, confidence and status

| Grade | Description |
|---|---|
| **A — Direct demonstration** | Ability/outcome shown in canon, effect clear, verifiable from source. |
| **B — Reliable inference or authoritative statement** | Follows from Grade A facts through a stated mechanism, or an authoritative source with specific credible grounds. |
| **C — Weak** | Vague reputation, boast, rumor, ambiguous scene, unexplained claim, or stretched inference. |

- Quality, not count, decides grade: one clear demonstration is A; five vague mentions remain C.
- Reliable inference requires A/authoritative-B premises, a stated 1–2 sentence mechanism, no more than one inferential step, no contradiction, and reviewer agreement.
- Confidence: **High** = Grade A, no unresolved conflict, insensitive to reasonable alternate reading; **Medium** = single A, A+B with minor ambiguity, or consistent B; **Low** = B/C only, conflicts, sparse evidence, adaptation-only or reading-sensitive.
- Status path: `Draft → Evidence-complete → Reviewed → Approved`; records that cannot reach Approved are `Held`. Nothing in this batch is Approved.
- Trigger independent review for Power 5, any Fit 5, Low confidence, ceiling exception, inference, contradiction, outlier, adaptation-only evidence, disputed ECV, or dependence on unevaluated characters.

## 7. Calibration use and two-pass workflow

**Pass A — Fit only.** Open `naruto_batch_005_calibration.json` and read only `fit_reference`. It contains 20 reviewed-draft anchors (R1=6, R2=7, R3=7) with Power values withheld. Treat them as Draft records reviewed locally, **not** Approved. The 93 non-anchor preliminary drafts, 18 disputed names and 49 held-excluded names are cautionary research targets only, never anchors.

**Pass B — Power.** After the seven Fit ratings for all 62 candidates are fixed, read `power_reference`. Assign Power using the same tier policy. Do not revisit Fit except for a documented factual error.

If evidence supports two adjacent levels equally, choose the lower and record the higher as the plausible alternative in the companion notes. Do not force a distribution.

## 8. Exact `KA-IMPORT-1.0` output structure

Output one JSON object. Required top-level keys: `format_version`, `batch_type`, `universe_id`, `evaluations`. Optional batch metadata may be added only if the consumer expects it; do not add rarity or scores.

```json
{
  "format_version": "KA-IMPORT-1.0",
  "batch_type": "evaluation",
  "universe_id": "naruto",
  "batch_id": "naruto-batch-005",
  "evaluation_framework_version": "EVAL-FRAMEWORK-1.0",
  "scoring_version": "SCORE-1.0",
  "canonical_policy_version": "NARUTO-CANON-0.1",
  "batch_status": "draft",
  "global_notes": [
    "Fit was assigned before Power with Power values hidden.",
    "No rarity, role scores, approval or publication status is assigned.",
    "The corrected research package contains demonstrated capabilities; secondary sources are traceable but primary material was not opened."
  ],
  "evaluations": [
    {
      "character_id": "dattebayo:879",
      "power": 2,
      "fit": {
        "captain": 0,
        "strategist": 2,
        "attacker": 0,
        "tank": 0,
        "assassin": 0,
        "support": 2,
        "healer": 0
      },
      "evidence": [
        {
          "target": "support",
          "grade": "B",
          "source_ref": "naruto_batch_005_research.json:dattebayo:879",
          "summary": "Bound Naruto's movement with Shadow Imitation Technique until Nine-Tails Chakra Mode broke the hold."
        },
        {
          "target": "power",
          "grade": "B",
          "source_ref": "naruto_batch_005_catalogue.json:dattebayo:879",
          "summary": "Single demonstrated restraint against Naruto; no broader combat record supplied."
        }
      ],
      "source_references": ["https://naruto.fandom.com/wiki/Suzaku_Nara"],
      "revision_ref": "claude-batch-005-002",
      "submit_for_review": true
    }
  ]
}
```

Field rules:

- `character_id` must be copied exactly from `candidate_id` in the research/catalogue files (for example `dattebayo:879`). Produce exactly **62** objects in the same order as the research file.
- `power` is integer 1–5. `fit` has exactly the seven lowercase keys shown, each integer 0–5.
- `evidence[].target` is `power` or one of the seven lowercase role keys. Provide at least one evidence item for `power` and for each non-zero Fit rating; provide a short note for unevidenced zeros in the companion notes.
- `evidence[].grade` is `A`, `B` or `C`. `source_ref` must be a real locator in the supplied files or an actual chapter/page URL you verified. `summary` must be factual and concise.
- `source_references` contains actual URLs or file locators used. Do not fabricate chapter numbers.
- `revision_ref` is a stable label for this Claude run. `submit_for_review: true` is allowed; it does not mean Approved.
- **Do not include `rarity`, `role_score`, `ecv_score`, `matchups` or `approved` keys.**

### Companion notes (same response, separate fenced block)

Because `KA-IMPORT-1.0` is intentionally compact, also return a second JSON object labelled `evaluation_details`, keyed by `character_id`, containing for each candidate: `canonical_version`, `version_selection_reasoning`, `core_abilities`, `conditional_abilities`, `excluded_abilities`, `ability_classes_used`, `confidence` (object with `power` and seven role keys), `plausible_alternatives`, `contradictions_or_outliers`, `uncertainty_note`, and `review_flags`. This second object must not contain rarity or scores.

## 9. Final QA checklist before returning

- [ ] Exactly 62 `evaluations`; IDs match the research file exactly and in order.
- [ ] All seven Fit keys present for every record; values are integers in 0–5; Power is integer 1–5.
- [ ] Fit was completed before Power; no Fit was raised because of Power.
- [ ] No cross-version composites; ECV stated for every record in companion notes.
- [ ] No invented feats; the preserved placeholder evaluation was not reused.
- [ ] No unresolved, adaptation-only, continuity-excluded, artwork-failed, Enma or Kōsuke record was evaluated.
- [ ] No rarity, scores, matchups, approval or publication status.
- [ ] Low-confidence candidates flagged for independent review.
