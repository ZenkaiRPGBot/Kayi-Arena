"""Run 10,000-draft balance simulations with the actual drafting engine."""

from __future__ import annotations

import json
import random
from collections import Counter
from pathlib import Path

from app.engine import (
    CatalogEntry,
    MatchStatus,
    SeededDrawSource,
    assign_role,
    shuffle,
    start_draft,
)

EXPANSION = Path("data/naruto_expansion_003_004_evaluated_dataset.json")
ORIGINAL_60 = Path("data/naruto_evaluated_60_dataset.json")
OUT = Path("data/naruto_expansion_003_004_balance_report.json")

DRAFTS = 10_000
WEIGHTS = {"Common": 30.0, "Uncommon": 30.0, "Rare": 22.0, "Epic": 13.0, "Legendary": 5.0}


def load_records() -> tuple[list[dict], list[dict], list[dict]]:
    expansion = json.loads(EXPANSION.read_text(encoding="utf-8"))
    original = json.loads(ORIGINAL_60.read_text(encoding="utf-8"))

    expansion_records = [
        r for r in expansion["characters"] if r.get("rarity") is not None and not r.get("held")
    ]
    original_records = [
        r for r in original["characters"] if r.get("rarity") is not None and not r.get("held")
    ]
    seen = {r["character_id"] for r in original_records}
    combined = list(original_records)
    for record in expansion_records:
        if record["character_id"] in seen:
            continue
        seen.add(record["character_id"])
        combined.append(record)
    return original_records, expansion_records, combined


def run_simulation(records: list[dict], drafts: int, seed: int) -> dict:
    by_id = {r["character_id"]: r for r in records}
    catalog = tuple(CatalogEntry(character_id=r["character_id"], rarity_id=r["rarity"]) for r in records)
    draw_source = SeededDrawSource(seed=seed)
    rng = random.Random(seed + 1)

    completed = 0
    failed = 0
    action_counts: list[int] = []
    first_player_wins = 0
    ties = 0
    role_counts: Counter[str] = Counter()
    rarity_counts: Counter[str] = Counter()
    healer_specialist_picks = 0
    player_drafts_with_healer = 0
    score_totals: Counter[str] = Counter()
    failure_reasons: Counter[str] = Counter()

    for index in range(drafts):
        try:
            snapshot = start_draft(
                match_id=f"sim-{seed}-{index}",
                players=("p1", "p2"),
                universe_id="naruto",
                mode="ranked",
                catalog=catalog,
                rarity_weights=WEIGHTS,
                dataset_version="naruto-expansion-003-004",
                draw_source=draw_source,
            ).snapshot
        except Exception as exc:  # pragma: no cover - defensive
            failed += 1
            failure_reasons[f"start:{type(exc).__name__}"] += 1
            continue

        actions = 0
        ok = True
        while snapshot.status is MatchStatus.ACTIVE:
            actor = snapshot.active_player_id
            if actor is None:
                ok = False
                failure_reasons["no_active_player"] += 1
                break
            try:
                snapshot = shuffle(
                    snapshot,
                    player_id=actor,
                    expected_revision=snapshot.revision,
                    draw_source=draw_source,
                ).snapshot
                actions += 1
                remaining = snapshot.remaining_roles()[actor]
                if not remaining:
                    ok = False
                    failure_reasons["no_remaining_roles"] += 1
                    break
                chosen = rng.choice(remaining)
                result = assign_role(snapshot, player_id=actor, role=chosen, expected_revision=snapshot.revision)
                if not result.accepted:
                    ok = False
                    failure_reasons["assign_rejected"] += 1
                    break
                snapshot = result.snapshot
                actions += 1
            except Exception as exc:  # pragma: no cover - defensive
                ok = False
                failure_reasons[f"loop:{type(exc).__name__}"] += 1
                break
            if actions > 500:
                ok = False
                failure_reasons["action_cap"] += 1
                break

        if not ok or snapshot.status is MatchStatus.ACTIVE:
            failed += 1
            continue

        completed += 1
        action_counts.append(actions)

        team_scores: dict[str, int] = {}
        for player_id in ("p1", "p2"):
            total = 0
            has_healer = False
            for role, character_id in snapshot.teams[player_id].items():
                record = by_id.get(character_id)
                if record is None:
                    continue
                role_counts[role] += 1
                rarity_counts[record["rarity"]] += 1
                total += record["scores"].get(role.lower(), 0)
                if record["fit"].get("healer", 0) >= 4:
                    healer_specialist_picks += 1
                    has_healer = True
            team_scores[player_id] = total
            score_totals[player_id] += total
            if has_healer:
                player_drafts_with_healer += 1

        if team_scores["p1"] > team_scores["p2"]:
            first_player_wins += 1
        elif team_scores["p1"] == team_scores["p2"]:
            ties += 1

    decisive = completed - ties
    total_picks = sum(rarity_counts.values())
    return {
        "drafts_requested": drafts,
        "completed": completed,
        "failed": failed,
        "failure_reasons": dict(failure_reasons),
        "average_actions_per_draft": round(sum(action_counts) / max(1, len(action_counts)), 2),
        "first_player_wins": first_player_wins,
        "ties": ties,
        "first_player_win_rate_all_completed": round(first_player_wins / max(1, completed), 4),
        "first_player_win_rate_decisive": round(first_player_wins / max(1, decisive), 4),
        "first_player_advantage_decisive": round(first_player_wins / max(1, decisive) - 0.5, 4),
        "average_team_score": {
            player: round(score_totals[player] / max(1, completed), 2) for player in ("p1", "p2")
        },
        "role_distribution": dict(role_counts),
        "rarity_distribution": dict(rarity_counts),
        "effective_rarity_share": {
            rarity: round(count / max(1, total_picks), 4) for rarity, count in rarity_counts.items()
        },
        "healing": {
            "healer_fit_4_plus_picks": healer_specialist_picks,
            "player_drafts_with_healer_specialist": player_drafts_with_healer,
            "share_of_player_drafts_with_healer_specialist": round(
                player_drafts_with_healer / max(1, completed * 2), 4
            ),
        },
    }


def main() -> None:
    original_records, expansion_records, combined_records = load_records()
    expansion_result = run_simulation(expansion_records, DRAFTS, seed=42)
    combined_result = run_simulation(combined_records, DRAFTS, seed=43)

    healer_pool = [
        {"name": r["name"], "healer_fit": r["fit"]["healer"], "rarity": r["rarity"]}
        for r in combined_records
        if r["fit"].get("healer", 0) >= 4
    ]

    report = {
        "simulation": {
            "engine": "app.engine start_draft / shuffle / assign_role",
            "drafts_per_scenario": DRAFTS,
            "total_drafts": DRAFTS * 2,
            "strategy": (
                "Each turn the active player shuffles with a seeded draw source, then assigns a "
                "uniformly random remaining role. Both players follow the same policy. Team strength "
                "is the sum of SCORE-1.0 role scores for the assigned roles."
            ),
            "seeds": {"expansion_only": 42, "combined": 43},
        },
        "catalog": {
            "original_60_playable": len(original_records),
            "expansion_playable": len(expansion_records),
            "combined_playable": len(combined_records),
            "rarity_weights": WEIGHTS,
            "combined_rarity_pool_counts": dict(Counter(r["rarity"] for r in combined_records)),
        },
        "expansion_only": expansion_result,
        "combined": combined_result,
        "healing": {
            "healer_fit_4_plus_pool": healer_pool,
            "pool_size": len(healer_pool),
        },
        "notes": [
            "Only Draft records with complete ratings enter each pool; Held records are excluded.",
            "Balance analysis does not modify any canonical rating.",
            "Effective rarity share is empirical picks / total picks in that scenario.",
        ],
    }
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        json.dumps(
            {
                "catalog": report["catalog"],
                "expansion_only": expansion_result,
                "combined": combined_result,
                "healing": report["healing"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
