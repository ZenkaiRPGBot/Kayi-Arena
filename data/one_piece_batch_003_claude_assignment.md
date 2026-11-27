# Kayi Arena — One Piece Batch 003 Independent Character Evaluation

## 0. Self-contained assignment

This prompt is self-contained. Do not rely on prior conversations, repository
access or unpublished decisions. Use only the material attached below and any
sources you inspect yourself while following the canonical policy.

You are an independent evaluator for Kayi Arena. You are not responsible for
coding, artwork, database integration, rarity calculation or gameplay.

## 1. Universe and canonical policy

- Universe ID: `one_piece`
- Universe name: One Piece
- Canonical policy: `ONE-PIECE-CANON-0.1`
- Manga cutoff: Chapter 1100
- Framework: `EVAL-FRAMEWORK-1.0`
- Scoring version: `SCORE-1.0`
- Prepared date: 2026-11-27

Policy:

1. Use manga canon through Chapter 1100. Anime-only, movie-only, game-only,
   novel-only and SBS-only abilities are excluded unless supported by a cited
   manga chapter within the cutoff.
2. Evaluate one sustainable canonical version per individual character. Prefer
   demonstrated prime capability within the cutoff; do not combine incompatible
   periods or forms.
3. Repeatable transformations and accessible power-ups may count. One-time
   external boosts, fatal techniques and borrowed or externally controlled
   abilities must be flagged and treated cautiously.
4. Rank, bounty, reputation and Devil Fruit classification are context only.
   Ratings must rest on demonstrated actions, techniques or specialist functions.
5. The research package uses inspected secondary One Piece Wiki pages. Chapter
   references were extracted from those pages; primary manga was not directly
   opened. Treat them as leads, not as independently verified primary evidence.
6. Unknown evidence must remain unknown. Do not fabricate feats or references.

## 2. Attached material

- `one_piece_batch_003_research.json` — only RESEARCH_READY candidates with factual ability research and traceable sources.
- `one_piece_batch_003_catalogue.json` — identity and artwork metadata.
- `one_piece_batch_003_claude_assignment.md` — this assignment.

The research package contains 32 candidates. No Power, Role Fit,
rarity, score, approval or publication status has been allocated.

## 3. Evaluation framework

### Power (integer 1–5)

Power is overall combat capability relative to the One Piece universe.

- 1 — Very limited combat capability.
- 2 — Modest but demonstrated combat capability.
- 3 — Capable and accomplished combatant.
- 4 — Exceptional, high-level combatant.
- 5 — Among the universe's highest demonstrated combat capabilities.

These are anchors, not automatic classifications by rank or reputation.

### Role Fit (integer 0–5, seven independent roles)

- 0 — No meaningful demonstrated suitability.
- 1 — Minimal suitability.
- 2 — Limited but useful suitability.
- 3 — Competent suitability.
- 4 — Exceptional suitability.
- 5 — Outstanding specialist capability.

Roles:

- `captain` — leadership, coordination, judgment, command.
- `strategist` — planning, analysis, tactical intelligence, adaptation.
- `attacker` — direct offensive ability and effectiveness.
- `tank` — damage resistance, durability, defensive techniques, protecting allies.
- `assassin` — stealth, infiltration, surprise, precision elimination.
- `support` — battlefield control, sensing, restraint, mobility assistance, enhancements.
- `healer` — demonstrated treatment or restoration of others. Self-regeneration alone is insufficient.

Power and Role Fit are independent. Do not distribute points to manufacture a
balanced roster. Do not manipulate ratings for rarity outcomes. Support unusual
ratings with specific evidence.

## 4. Calibration guidance

There are no approved One Piece evaluations yet. Do not treat any provisional
One Piece rating as an approved anchor. Use the framework anchors above and
maintain consistency within this batch. If you rely on cross-universe intuition,
state that it is provisional and do not present it as approved One Piece
calibration. Incorporate approved One Piece evaluations only in future batches.

## 5. Evidence handling

Every `draft` record must have at least one traceable source supporting
meaningful ability claims. Prefer:

1. Primary manga chapters within the cutoff, if you inspect them.
2. Official franchise sources.
3. The inspected secondary profiles supplied in the research package, with chapter leads.

Record actual URLs and chapter references. Distinguish directly inspected
primary sources, inspected secondary sources and unverified recollection. Mark
records `held` when identity, eligibility or evidence is insufficient. Do not
invent placeholder ratings for held records.

## 6. Required output

Return one JSON object with exactly these root fields:

```json
{
  "universe_id": "one_piece",
  "batch_id": "one-piece-batch-003",
  "mode": "independent_evaluation",
  "evaluation_framework_version": "EVAL-FRAMEWORK-1.0",
  "scoring_version": "SCORE-1.0",
  "canonical_policy_version": "ONE-PIECE-CANON-0.1",
  "prepared_date": "2026-11-27",
  "batch_status": "evaluation_submission",
  "notes": [],
  "characters": []
}
```

Each character record must contain exactly:

```json
{
  "id": "one_piece_candidate_id",
  "name": "Display name",
  "canonical_name": "Canonical name",
  "aliases": [],
  "canonical_version": "Selected version and cutoff",
  "power": 1,
  "fit": {
    "captain": 0,
    "strategist": 0,
    "attacker": 0,
    "tank": 0,
    "assassin": 0,
    "support": 0,
    "healer": 0
  },
  "justification": "Concise evidence-based rationale.",
  "evidence_leads": [
    {
      "lead": "What the evidence supports.",
      "check": "How to verify it.",
      "source_note": "URL and/or chapter lead."
    }
  ],
  "confidence": "high",
  "review_flags": [],
  "evaluation_status": "draft"
}
```

Rules:

- `power` must be an integer from 1 to 5.
- Every `fit` value must be an integer from 0 to 5.
- `confidence` must be `high`, `medium` or `low`.
- `evaluation_status` must be `draft` or `held`.
- Every candidate in the roster below must appear exactly once.
- Do not add `approved`, `rarity` or `role_score` fields.

## 7. Candidate roster

| `one_piece_candidate_id` | Display name | Faction | Evidence focus |
| --- | --- | --- | --- |
| `one_piece_benn_beckman` | Benn Beckman | Red Hair Pirates | offense, defense durability, tactics |
| `one_piece_yasopp` | Yasopp | Red Hair Pirates | offense |
| `one_piece_avalo_pizarro` | Avalo Pizarro | Blackbeard Pirates | offense, defense durability |
| `one_piece_vasco_shot` | Vasco Shot | Blackbeard Pirates | offense, defense durability |
| `one_piece_sanjuan_wolf` | San Juan Wolf | Blackbeard Pirates | offense |
| `one_piece_laffitte` | Lafitte | Blackbeard Pirates | offense, defense durability, support control |
| `one_piece_hatchan` | Hatchan | Arlong Pirates | offense |
| `one_piece_kuroobi` | Kuroobi | Arlong Pirates | offense |
| `one_piece_chew` | Choo | Arlong Pirates | offense |
| `one_piece_alvida` | Alvida | Alvida Pirates | offense |
| `one_piece_cabaji` | Cabaji | Buggy Pirates | offense, defense durability |
| `one_piece_gem` | Mr. 5 | Baroque Works | offense |
| `one_piece_mikita` | Miss Valentine | Baroque Works | offense |
| `one_piece_mr_9` | Mr. 9 | Baroque Works | offense |
| `one_piece_otohime` | Otohime | Fish-Man Kingdom | offense, defense durability |
| `one_piece_zeo` | Zeo | New Fish-Man Pirates | offense, defense durability |
| `one_piece_ikaros_much` | Ikaros | New Fish-Man Pirates | offense, defense durability |
| `one_piece_pedro` | Pedro | Mink Tribe | offense, defense durability, tactics |
| `one_piece_carrot` | Carrot | Mink Tribe | offense, defense durability |
| `one_piece_wanda` | Wanda | Mink Tribe | offense, defense durability |
| `one_piece_shishilian` | Shishilian | Mink Tribe | offense, defense durability |
| `one_piece_bepo` | Bepo | Heart Pirates | offense, defense durability |
| `one_piece_perona` | Perona | Thriller Bark Pirates | offense, support control, medical healing |
| `one_piece_kureha` | Kureha | Drum Kingdom | offense, defense durability, support control, medical healing |
| `one_piece_hiriluk` | Hiluluk | Drum Kingdom | offense, support control, medical healing |
| `one_piece_mansherry` | Mansherry | Dressrosa | offense |
| `one_piece_suleiman` | Suleiman | Straw Hat Grand Fleet | offense |
| `one_piece_charlotte_cadenza` | Charlotte Cadenza | Big Mom Pirates | offense, defense durability |
| `one_piece_kurozumi_orochi` | Kurozumi Orochi | Kurozuki Family | offense, tactics |
| `one_piece_kurozumi_higurashi` | Kurozumi Higurashi | Kurozuki Family | offense |
| `one_piece_onimaru` | Gyukimaru | Wano Country | offense |
| `one_piece_minotaurus` | Minotaurus | Impel Down | offense |

## 8. Ready-to-use prompt

Evaluate all 32 candidates listed above using the attached research
package and the framework in this document. Return only the required JSON object
plus a concise exception report listing held candidates and why they are held.
Do not approve, publish or calculate rarity. Do not rely on previous conversations.

## 9. Completion checklist

- Every research-ready candidate appears once.
- Power and all seven Role Fits are integers in range.
- Justifications cite demonstrated abilities, not metadata alone.
- Continuity-sensitive or adaptation-sensitive claims are flagged.
- Held records explain the missing evidence.
- No approval, rarity or publication status is allocated.
