# Kayi Arena — Versioned Import & Export Format (`KA-IMPORT-1.0`)

Parallel development contract for OpenCode (character catalogue & image tooling) and Claude (AI evaluation batches). Independent of external source providers, scrapers, or image downloaders.

## 1. Character Catalogue Batch (`batch_type = "catalogue"`)

Supports incomplete candidate records (missing `power` / `fit` are stored as `draft` and cannot enter production datasets until evaluated, approved, and image-verified).

```json
{
  "format_version": "KA-IMPORT-1.0",
  "batch_type": "catalogue",
  "universe_id": "naruto",
  "characters": [
    {
      "character_id": "naruto_naruto_uzumaki",
      "name": "Naruto Uzumaki",
      "aliases": ["Seventh Hokage", "Child of Prophecy"],
      "species": "human",
      "canonical_version": "Part II Fourth War",
      "rarity": "Legendary",
      "image": {
        "url_or_ref": "assets/naruto/naruto_uzumaki.png",
        "source_ref": "manga-ch-645",
        "mime_type": "image/png",
        "width": 512,
        "height": 512,
        "checksum": "sha256-...",
        "status": "pending"
      },
      "source_references": ["manga-ch-1-700"],
      "revision_ref": "cat-1"
    }
  ]
}
```

- Required per character: `character_id` (unique string), `name`, `canonical_version`, `rarity` (`Common` | `Uncommon` | `Rare` | `Epic` | `Legendary`).
- Optional: `aliases`, `species` (`human` | `non_human`, default `human`), `power`, `fit`, `evidence`, `source_references`, `image`, `revision_ref`.
- Imported records always enter `EvaluationStatus.DRAFT`.

## 2. AI Evaluation Batch (`batch_type = "evaluation"`)

```json
{
  "format_version": "KA-IMPORT-1.0",
  "batch_type": "evaluation",
  "universe_id": "naruto",
  "evaluations": [
    {
      "character_id": "naruto_naruto_uzumaki",
      "power": 5,
      "fit": {
        "captain": 4,
        "strategist": 3,
        "attacker": 5,
        "tank": 3,
        "assassin": 1,
        "support": 4,
        "healer": 1
      },
      "evidence": [
        {
          "target": "power",
          "grade": "A",
          "source_ref": "Pain arc / War arc",
          "summary": "Sustained Kurama + Sage Mode feats"
        }
      ],
      "source_references": ["manga-vol-48"],
      "revision_ref": "eval-1",
      "submit_for_review": true
    }
  ]
}
```

- Ratings are validated and scored via Module 2 (`SCORE-1.0`).
- `submit_for_review: true` transitions the record from `draft` to `review`; human/admin approval (`approve_character`) is still required before production publication.
