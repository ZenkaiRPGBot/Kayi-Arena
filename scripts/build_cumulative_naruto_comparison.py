"""Construct cumulative Naruto comparison datasets and distribution analysis.

Dataset A: reconstructed current roster from the initial 60 draft evaluation snapshot.
Dataset B: A + eligible Batches 003-004 draft characters.
Dataset C: B + the 52 audited Batch 005 importable characters.

No exact verified published production snapshot is available in the repository;
all datasets are explicitly labelled reconstructed draft snapshots.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.scoring.engine import score_record
from app.scoring.models import SCORING_ROLES

ROOT = Path("data")
ROLES = list(SCORING_ROLES)
PREPARED_DATE = "2026-11-27"


def load(name: str) -> Any:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def write(name: str, payload: Any) -> None:
    (ROOT / name).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def norm_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def normalize(record: dict[str, Any], *, source: str, batch: str) -> dict[str, Any]:
    power = int(record["power"])
    fit = {role: int(record["fit"][role]) for role in ROLES}
    scores = dict(
        score_record({"character_id": record["character_id"], "power": power, "fit": fit}).scores
    )
    rarity = record["rarity"]
    if isinstance(rarity, dict):
        rarity = rarity.get("final_rarity") or rarity.get("base_rarity")
    return {
        "character_id": record["character_id"],
        "name": record.get("name") or record.get("catalogue_name") or record["character_id"],
        "canonical_name": record.get("canonical_name") or record.get("name") or record["character_id"],
        "universe_id": "naruto",
        "canonical_version": record.get("canonical_version", ""),
        "power": power,
        "fit": fit,
        "scores": scores,
        "rarity": rarity,
        "source": source,
        "batch": batch,
        "review_status": record.get("evaluation_status", "draft"),
    }


def dedupe(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    by_id: dict[str, dict[str, Any]] = {}
    by_name: dict[str, str] = {}
    removed: list[dict[str, str]] = []
    for item in records:
        cid = item["character_id"]
        key = norm_name(item["canonical_name"])
        if cid in by_id:
            removed.append({"character_id": cid, "name": item["name"], "reason": "duplicate character_id"})
            continue
        if key in by_name:
            removed.append(
                {
                    "character_id": cid,
                    "name": item["name"],
                    "reason": f"duplicate canonical identity of {by_name[key]}",
                }
            )
            continue
        by_id[cid] = item
        by_name[key] = cid
    return list(by_id.values()), removed


def counts_by_roles(records: list[dict[str, Any]], threshold: int) -> dict[str, int]:
    return {
        role: sum(1 for item in records if item["fit"][role] >= threshold)
        for role in ROLES
    }


def distribution(records: list[dict[str, Any]]) -> dict[str, Any]:
    power = Counter(item["power"] for item in records)
    rarity = Counter(item["rarity"] for item in records)
    fit_counts = {
        role: Counter(item["fit"][role] for item in records) for role in ROLES
    }
    avg_scores = {
        role: round(sum(item["scores"][role] for item in records) / len(records), 2)
        for role in ROLES
    }
    versatility = {
        "roles_fit_ge_2_avg": round(
            sum(sum(1 for role in ROLES if item["fit"][role] >= 2) for item in records)
            / len(records),
            2,
        ),
        "roles_fit_ge_3_avg": round(
            sum(sum(1 for role in ROLES if item["fit"][role] >= 3) for item in records)
            / len(records),
            2,
        ),
        "roles_fit_ge_4_avg": round(
            sum(sum(1 for role in ROLES if item["fit"][role] >= 4) for item in records)
            / len(records),
            2,
        ),
    }
    no_specialist = sum(
        1 for item in records if all(item["fit"][role] <= 1 for role in ROLES)
    )
    return {
        "character_count": len(records),
        "power_distribution": {str(level): power[level] for level in (1, 2, 3, 4, 5)},
        "rarity_distribution": {
            tier: rarity[tier] for tier in ("Common", "Uncommon", "Rare", "Epic", "Legendary")
        },
        "role_fit_distribution": {
            role: {str(level): fit_counts[role][level] for level in range(6)} for role in ROLES
        },
        "average_role_scores": avg_scores,
        "versatility": versatility,
        "specialists_fit_ge_3": counts_by_roles(records, 3),
        "specialists_fit_ge_4": counts_by_roles(records, 4),
        "specialists_fit_5": counts_by_roles(records, 5),
        "healer_fit_counts": {
            f"ge_{level}": sum(1 for item in records if item["fit"]["healer"] >= level)
            for level in (1, 2, 3, 4, 5)
        },
        "support_specialists_fit_ge_3": sum(1 for item in records if item["fit"]["support"] >= 3),
        "strategist_specialists_fit_ge_3": sum(
            1 for item in records if item["fit"]["strategist"] >= 3
        ),
        "support_specialists_fit_ge_4": sum(1 for item in records if item["fit"]["support"] >= 4),
        "strategist_specialists_fit_ge_4": sum(
            1 for item in records if item["fit"]["strategist"] >= 4
        ),
        "characters_with_no_meaningful_specialist_role": no_specialist,
    }


def main() -> None:
    initial = load("naruto_evaluated_60_dataset.json")["characters"]
    expansion = load("naruto_expansion_003_004_evaluated_dataset.json")["characters"]
    b005 = load("naruto_batch_005_audited_evaluations.json")["evaluations"]
    held = load("naruto_batch_005_held_candidates.json")["candidates"]

    a_records = [
        normalize(item, source="naruto_evaluated_60_dataset.json", batch="initial_60")
        for item in initial
        if not item.get("held") and item.get("evaluation_status") != "held"
    ]
    b_records = a_records + [
        normalize(item, source="naruto_expansion_003_004_evaluated_dataset.json", batch="003_004")
        for item in expansion
        if not item.get("held") and item.get("evaluation_status") != "held"
    ]
    c_records = b_records + [
        normalize(item, source="naruto_batch_005_audited_evaluations.json", batch="005_audited")
        for item in b005
    ]

    a_records, a_removed = dedupe(a_records)
    b_records, b_removed = dedupe(b_records)
    c_records, c_removed = dedupe(c_records)

    datasets = {
        "A": {
            "description": "Reconstructed current Naruto roster from the initial 60 draft evaluation snapshot.",
            "verified_published_snapshot": False,
            "snapshot_status": "reconstructed_draft",
            "source_file": "data/naruto_evaluated_60_dataset.json",
            "excluded_held_count": sum(
                1 for item in initial if item.get("held") or item.get("evaluation_status") == "held"
            ),
            "duplicates_removed": a_removed,
            "characters": a_records,
            "analysis": distribution(a_records),
        },
        "B": {
            "description": "Dataset A plus eligible Batches 003-004 draft characters.",
            "verified_published_snapshot": False,
            "snapshot_status": "reconstructed_draft",
            "source_files": [
                "data/naruto_evaluated_60_dataset.json",
                "data/naruto_expansion_003_004_evaluated_dataset.json",
            ],
            "excluded_held_count": sum(
                1 for item in initial if item.get("held") or item.get("evaluation_status") == "held"
            )
            + sum(
                1
                for item in expansion
                if item.get("held") or item.get("evaluation_status") == "held"
            ),
            "duplicates_removed": b_removed,
            "characters": b_records,
            "analysis": distribution(b_records),
        },
        "C": {
            "description": "Dataset B plus the 52 audited Batch 005 importable characters.",
            "verified_published_snapshot": False,
            "snapshot_status": "reconstructed_draft_plus_audited_batch_005",
            "source_files": [
                "data/naruto_evaluated_60_dataset.json",
                "data/naruto_expansion_003_004_evaluated_dataset.json",
                "data/naruto_batch_005_audited_evaluations.json",
            ],
            "excluded_held_count": sum(
                1 for item in initial if item.get("held") or item.get("evaluation_status") == "held"
            )
            + sum(
                1
                for item in expansion
                if item.get("held") or item.get("evaluation_status") == "held"
            )
            + len(held),
            "duplicates_removed": c_removed,
            "characters": c_records,
            "analysis": distribution(c_records),
        },
    }

    deltas = {
        "B_minus_A": {
            key: datasets["B"]["analysis"][key] - datasets["A"]["analysis"][key]
            for key in ("character_count", "characters_with_no_meaningful_specialist_role")
        },
        "C_minus_B": {
            key: datasets["C"]["analysis"][key] - datasets["B"]["analysis"][key]
            for key in ("character_count", "characters_with_no_meaningful_specialist_role")
        },
    }
    for label, dataset in datasets.items():
        pass

    write(
        "naruto_cumulative_roster_comparison.json",
        {
            "universe_id": "naruto",
            "prepared_date": PREPARED_DATE,
            "canonical_policy": "NARUTO-CANON-0.1",
            "scoring_version": "SCORE-1.0",
            "rarity_version": "RARITY-0.2",
            "snapshot_note": (
                "No exact verified published production snapshot is present in the "
                "repository. Datasets A/B/C are reconstructed from draft evaluation "
                "snapshots, with Held records excluded."
            ),
            "datasets": datasets,
            "headline_deltas": deltas,
        },
    )
    print(
        json.dumps(
            {
                label: {
                    "count": data["analysis"]["character_count"],
                    "duplicates_removed": len(data["duplicates_removed"]),
                    "power": data["analysis"]["power_distribution"],
                    "rarity": data["analysis"]["rarity_distribution"],
                    "healer": data["analysis"]["healer_fit_counts"],
                }
                for label, data in datasets.items()
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
