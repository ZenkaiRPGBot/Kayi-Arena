# Kayi Arena — One Piece Batch 001 Independent Character Evaluation

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

- `one_piece_batch_001_research.json` — only RESEARCH_READY candidates with factual ability research and traceable sources.
- `one_piece_batch_001_catalogue.json` — identity and artwork metadata.
- `one_piece_batch_001_claude_assignment.md` — this assignment.

The research package contains 69 candidates. No Power, Role Fit,
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
  "batch_id": "one-piece-batch-001",
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
| `one_piece_monkey_d_luffy` | Monkey D. Luffy | Straw Hat Pirates | offense, defense durability, tactics, support control |
| `one_piece_roronoa_zoro` | Roronoa Zoro | Straw Hat Pirates | offense, defense durability, tactics |
| `one_piece_nami` | Nami | Straw Hat Pirates | offense, defense durability, tactics, support control |
| `one_piece_usopp` | Usopp | Straw Hat Pirates | offense, defense durability, tactics, support control |
| `one_piece_sanji` | Vinsmoke Sanji | Straw Hat Pirates | offense, defense durability, tactics, support control |
| `one_piece_tony_tony_chopper` | Tony Tony Chopper | Straw Hat Pirates | offense, defense durability, tactics, support control |
| `one_piece_nico_robin` | Nico Robin | Straw Hat Pirates | offense, defense durability, tactics, support control |
| `one_piece_franky` | Franky | Straw Hat Pirates | offense, defense durability, tactics, support control |
| `one_piece_brook` | Brook | Straw Hat Pirates | offense, defense durability |
| `one_piece_jinbe` | Jinbe | Straw Hat Pirates | offense, defense durability, tactics |
| `one_piece_trafalgar_d_water_law` | Trafalgar D. Water Law | Worst Generation | offense, defense durability, tactics, support control |
| `one_piece_eustass_kid` | Eustass Kid | Worst Generation | offense, defense durability, tactics, support control |
| `one_piece_capone_bege` | Capone Bege | Worst Generation | offense, defense durability, tactics |
| `one_piece_jewelry_bonney` | Jewelry Bonney | Worst Generation | offense, defense durability |
| `one_piece_scratchmen_apoo` | Scratchmen Apoo | Worst Generation | offense, defense durability, tactics |
| `one_piece_basil_hawkins` | Basil Hawkins | Worst Generation | offense, tactics |
| `one_piece_x_drake` | X Drake | Worst Generation | offense, defense durability, tactics |
| `one_piece_urouge` | Urouge | Worst Generation | offense, defense durability |
| `one_piece_shanks` | Shanks | Red Hair Pirates | offense, defense durability, tactics |
| `one_piece_marshall_d_teach` | Marshall D. Teach | Blackbeard Pirates | offense, defense durability, tactics |
| `one_piece_charlotte_linlin` | Charlotte Linlin | Big Mom Pirates | offense, defense durability, tactics |
| `one_piece_kaidou` | Kaidou | Beasts Pirates | offense, defense durability, tactics |
| `one_piece_edward_newgate` | Edward Newgate | Whitebeard Pirates | offense, defense durability, tactics |
| `one_piece_buggy` | Buggy | Cross Guild | offense, defense durability |
| `one_piece_gol_d_roger` | Gol D. Roger | Roger Pirates | offense, defense durability, support control |
| `one_piece_silvers_rayleigh` | Silvers Rayleigh | Roger Pirates | offense, defense durability, tactics |
| `one_piece_dracule_mihawk` | Dracule Mihawk | Cross Guild | offense, defense durability, tactics |
| `one_piece_crocodile` | Crocodile | Cross Guild | offense, defense durability, tactics, support control |
| `one_piece_boa_hancock` | Boa Hancock | Amazon Lily | offense, defense durability, tactics |
| `one_piece_donquixote_doflamingo` | Donquixote Doflamingo | Donquixote Pirates | offense, defense durability, tactics |
| `one_piece_gecko_moria` | Gecko Moria | Thriller Bark Pirates | offense, defense durability, tactics |
| `one_piece_bartholomew_kuma` | Bartholomew Kuma | Revolutionary Army | offense, defense durability |
| `one_piece_monkey_d_garp` | Monkey D. Garp | Marines | offense, defense durability, tactics, support control |
| `one_piece_sakazuki` | Sakazuki | Marines | offense, defense durability, tactics |
| `one_piece_kuzan` | Kuzan | Marines | offense, defense durability |
| `one_piece_borsalino` | Borsalino | Marines | offense, defense durability, tactics |
| `one_piece_issho` | Issho | Marines | offense, defense durability, tactics |
| `one_piece_aramaki` | Aramaki | Marines | offense, defense durability, tactics |
| `one_piece_smoker` | Smoker | Marines | offense, defense durability, tactics |
| `one_piece_tashigi` | Tashigi | Marines | offense, defense durability |
| `one_piece_koby` | Koby | Marines | offense, defense durability, tactics |
| `one_piece_helmeppo` | Helmeppo | Marines | offense, defense durability |
| `one_piece_tsuru` | Tsuru | Marines | offense, tactics |
| `one_piece_sabo` | Sabo | Revolutionary Army | offense, defense durability, tactics |
| `one_piece_rob_lucci` | Rob Lucci | CP9 | offense, defense durability, tactics |
| `one_piece_kaku` | Kaku | CP9 | offense, defense durability, tactics |
| `one_piece_blueno` | Blueno | CP9 | offense, defense durability |
| `one_piece_kalifa` | Kalifa | CP9 | offense, defense durability |
| `one_piece_shiryu` | Shiryu | Impel Down | offense, defense durability |
| `one_piece_bentham` | Bentham | Impel Down | offense, defense durability |
| `one_piece_polo_marco` | Marco | Whitebeard Pirates | offense, defense durability, tactics |
| `one_piece_jozu` | Jozu | Whitebeard Pirates | offense, defense durability |
| `one_piece_izou` | Izo | Whitebeard Pirates | offense, defense durability |
| `one_piece_portgas_d_ace` | Portgas D. Ace | Whitebeard Pirates | offense, defense durability, tactics |
| `one_piece_yamato` | Yamato | Beasts Pirates | offense, defense durability, tactics |
| `one_piece_kouzuki_oden` | Kozuki Oden | Kozuki Clan | offense, defense durability, support control |
| `one_piece_kinemon` | Kin'emon | Nine Red Scabbards | offense, defense durability, tactics |
| `one_piece_kouzuki_momonosuke` | Kozuki Momonosuke | Kozuki Clan | offense, defense durability, support control |
| `one_piece_kikunojo` | Kikunojo | Nine Red Scabbards | offense, defense durability |
| `one_piece_raizo` | Raizo | Nine Red Scabbards | offense, defense durability |
| `one_piece_nekomamushi` | Nekomamushi | Nine Red Scabbards | offense, defense durability |
| `one_piece_inuarashi` | Inuarashi | Nine Red Scabbards | offense, defense durability |
| `one_piece_charlotte_katakuri` | Charlotte Katakuri | Big Mom Pirates | offense, defense durability, tactics |
| `one_piece_charlotte_smoothie` | Charlotte Smoothie | Big Mom Pirates | offense, defense durability |
| `one_piece_charlotte_cracker` | Charlotte Cracker | Big Mom Pirates | offense, defense durability |
| `one_piece_charlotte_perospero` | Charlotte Perospero | Big Mom Pirates | offense, defense durability, tactics |
| `one_piece_king` | King | Beasts Pirates | offense, defense durability |
| `one_piece_queen` | Queen | Beasts Pirates | offense, defense durability, support control, medical healing |
| `one_piece_kyros` | Kyros | Dressrosa | offense, defense durability, tactics |

## 8. Ready-to-use prompt

Evaluate all 69 candidates listed above using the attached research
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
