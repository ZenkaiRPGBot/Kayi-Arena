"""Gameplay simulation for the audited Naruto Batch 005 importable pool.

Uses the repository's actual drafting engine and DEFAULT_RARITY_WEIGHTS.
No match resolution winner is claimed; team score is computed with SCORE-1.0.
"""

from __future__ import annotations

import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import DEFAULT_RARITY_WEIGHTS
from app.engine import (
    CatalogEntry,
    MatchStatus,
    SeededDrawSource,
    assign_role,
    shuffle,
    start_draft,
)

ROOT = Path("data")
MATCHES = 1_000
SEED = 20261127


def main() -> None:
    audit = json.loads((ROOT / "naruto_batch_005_audited_evaluations.json").read_text(encoding="utf-8"))
    records = audit["evaluations"]
    catalog = tuple(
        CatalogEntry(character_id=item["character_id"], rarity_id=item["rarity"]["final_rarity"])
        for item in records
    )
    score_by_id = {item["character_id"]: item["scores"] for item in records}
    fit_by_id = {item["character_id"]: item["fit"] for item in records}

    draw_source = SeededDrawSource(seed=SEED)
    role_rng = random.Random(SEED)
    rarity_draws: Counter[str] = Counter()
    role_counts: Counter[str] = Counter()
    score_sums: Counter[str] = Counter()
    team_score_diff = 0
    completed = 0
    healer_fit_ge3 = 0
    healer_fit_ge4 = 0
    total_teams = 0

    for index in range(MATCHES):
        result = start_draft(
            match_id=f"b005-audit-{index}",
            players=("p1", "p2"),
            universe_id="naruto",
            mode="ranked",
            catalog=catalog,
            rarity_weights=DEFAULT_RARITY_WEIGHTS,
            dataset_version="naruto-batch-005-audit",
            draw_source=draw_source,
        )
        snap = result.snapshot
        while snap.status is MatchStatus.ACTIVE:
            actor = snap.active_player_id
            assert actor is not None
            snap = shuffle(
                snap, player_id=actor, expected_revision=snap.revision, draw_source=draw_source
            ).snapshot
            assert snap.held_character is not None
            rarity_draws[snap.held_character.rarity_id] += 1
            roles = snap.remaining_roles()[actor]
            chosen_role = role_rng.choice(roles)
            snap = assign_role(
                snap, player_id=actor, role=chosen_role, expected_revision=snap.revision
            ).snapshot
        if snap.status is not MatchStatus.COMPLETED:
            continue
        completed += 1

        team_scores: dict[str, int] = {}
        for player_id, team in snap.teams.items():
            total = 0
            for role, cid in team.items():
                normalized_role = role.lower()
                role_counts[normalized_role] += 1
                role_score = score_by_id[cid][normalized_role]
                score_sums[normalized_role] += role_score
                total += role_score
                if normalized_role == "healer":
                    if fit_by_id[cid]["healer"] >= 3:
                        healer_fit_ge3 += 1
                    if fit_by_id[cid]["healer"] >= 4:
                        healer_fit_ge4 += 1
                total_teams += 1
            team_scores[player_id] = total
        if team_scores["p1"] > team_scores["p2"]:
            team_score_diff += 1

    total_draws = sum(rarity_draws.values())
    report = {
        "simulation": "naruto_batch_005_audited_importable_pool",
        "engine": "app.engine deterministic draft engine",
        "matches_requested": MATCHES,
        "matches_completed": completed,
        "seed": SEED,
        "role_selection": "uniform random from remaining roles with Python random.Random(seed)",
        "rarity_weights": dict(DEFAULT_RARITY_WEIGHTS),
        "pool_size": len(catalog),
        "rarity_draw_pct": {
            rarity: round(100.0 * rarity_draws[rarity] / total_draws, 2)
            for rarity in DEFAULT_RARITY_WEIGHTS
        },
        "role_avg_score": {
            role: round(score_sums[role] / role_counts[role], 2)
            for role in sorted(role_counts)
        },
        "healer_availability": {
            "teams_with_healer_fit_ge_3_pct": round(100.0 * healer_fit_ge3 / total_teams, 2),
            "teams_with_healer_fit_ge_4_pct": round(100.0 * healer_fit_ge4 / total_teams, 2),
        },
        "team_score_advantage": {
            "player_1_higher_score_pct": round(100.0 * team_score_diff / completed, 2),
            "note": "Draft-order comparison of summed SCORE-1.0 role scores, not canonical match resolution.",
        },
        "winner_claim": "none",
        "approval_claim": "none",
    }
    (ROOT / "naruto_batch_005_audit_simulation.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
