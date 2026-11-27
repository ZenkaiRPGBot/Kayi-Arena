"""Cumulative gameplay simulation for Datasets A, B and C.

Drafting uses the repository's authoritative app.engine implementation. Match
resolution uses the canonical RES-1.0 rule set via a fast in-process path; the
fast path is cross-checked against app.resolution.resolve_match on a sample of
matches per dataset before the full run.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import DEFAULT_RARITY_WEIGHTS
from app.engine import (
    CatalogEntry,
    MatchStatus,
    SeededDrawSource,
    assign_role,
    skip_character,
    shuffle,
    start_draft,
)
from app.resolution import (
    DecidedBy,
    MatchOutcome,
    MatchupWinner,
    RepositoryDatasetReader,
    build_resolve_request_from_completed_draft,
    resolve_match,
)
from app.scoring.datasets import (
    DatasetKind,
    DatasetRecord,
    GoverningVersions,
    InMemoryDatasetRepository,
    RecordStatus,
    build_signed_manifest,
)
from app.scoring.models import SCORE_1_0_CONFIG, SCORE_1_0_VERSION

ROOT = Path("data")
DRAW_SEED = 20261201
ROLE_SEED = 20261202
NON_COMMON = {"Uncommon", "Rare", "Epic", "Legendary"}
CROSSCHECK_MATCHES = 100


def percentile(values: list[int], fraction: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1))))
    return ordered[index]


def build_reader(dataset: dict[str, Any], version: str) -> RepositoryDatasetReader:
    records = [
        DatasetRecord(
            character_id=item["character_id"],
            power=item["power"],
            fit=item["fit"],
            scores=item["scores"],
            status=RecordStatus.DRAFT,
            revision_ref="cumulative-analysis",
            scoring_version=SCORE_1_0_VERSION,
        )
        for item in dataset["characters"]
    ]
    manifest = build_signed_manifest(
        dataset_version=version,
        kind=DatasetKind.TEST,
        config=SCORE_1_0_CONFIG,
        records=records,
        governing_versions=GoverningVersions(
            universe_policy_version="NARUTO-CANON-0.1",
            anchor_set_version="NARUTO-CAL-005-0.1",
            calibration_set_version="NARUTO-CAL-005-0.1",
        ),
        created_at="2026-11-27T00:00:00+00:00",
    )
    repository = InMemoryDatasetRepository()
    repository.publish(manifest, config=SCORE_1_0_CONFIG)
    return RepositoryDatasetReader(repository)


def fast_resolve(snap: Any, score_by_id: dict[str, dict[str, int]]) -> dict[str, Any]:
    teams = {"player_1": snap.teams["p1"], "player_2": snap.teams["p2"]}
    matchups: dict[str, dict[str, Any]] = {}
    wins = {"player_1": 0, "player_2": 0, "draw": 0}
    totals = {"player_1": 0, "player_2": 0}
    for team_role, cid1 in teams["player_1"].items():
        role = team_role.lower()
        cid2 = teams["player_2"][team_role]
        s1 = score_by_id[cid1][role]
        s2 = score_by_id[cid2][role]
        totals["player_1"] += s1
        totals["player_2"] += s2
        margin = s1 - s2
        if margin > 0:
            winner = MatchupWinner.PLAYER_1
            wins["player_1"] += 1
        elif margin < 0:
            winner = MatchupWinner.PLAYER_2
            wins["player_2"] += 1
        else:
            winner = MatchupWinner.DRAW
            wins["draw"] += 1
        matchups[role] = {"winner": winner, "margin": margin, "score_1": s1, "score_2": s2}
    if wins["player_1"] > wins["player_2"]:
        outcome, decided_by = MatchOutcome.PLAYER_1_WIN, DecidedBy.MATCHUP_COUNT
    elif wins["player_2"] > wins["player_1"]:
        outcome, decided_by = MatchOutcome.PLAYER_2_WIN, DecidedBy.MATCHUP_COUNT
    elif totals["player_1"] > totals["player_2"]:
        outcome, decided_by = MatchOutcome.PLAYER_1_WIN, DecidedBy.COMBINED_SCORE
    elif totals["player_2"] > totals["player_1"]:
        outcome, decided_by = MatchOutcome.PLAYER_2_WIN, DecidedBy.COMBINED_SCORE
    else:
        outcome, decided_by = MatchOutcome.DRAW, DecidedBy.NONE
    return {
        "outcome": outcome,
        "decided_by": decided_by,
        "matchups": matchups,
        "totals": totals,
        "wins": wins,
    }


def simulate(comparison: dict[str, Any], label: str, matches: int) -> dict[str, Any]:
    dataset = comparison["datasets"][label]
    characters = dataset["characters"]
    version = f"naruto-cumulative-{label.lower()}"
    reader = build_reader(dataset, version)
    fit_by_id = {item["character_id"]: item["fit"] for item in characters}
    score_by_id = {item["character_id"]: item["scores"] for item in characters}
    catalog = tuple(
        CatalogEntry(character_id=item["character_id"], rarity_id=item["rarity"])
        for item in characters
    )
    non_common_ids = {
        item["character_id"] for item in characters if item["rarity"] in NON_COMMON
    }

    draw_source = SeededDrawSource(seed=DRAW_SEED)
    role_rng = random.Random(ROLE_SEED)
    rarity_draws: Counter[str] = Counter()
    role_assignments: dict[str, Counter[int]] = {role: Counter() for role in fit_by_id[characters[0]["character_id"]]}
    role_score_sum: Counter[str] = Counter()
    matchup_counts: Counter[str] = Counter()
    matchup_draws: Counter[str] = Counter()
    matchup_margins: Counter[str] = Counter()
    team_scores: list[int] = []
    healer_fits: list[int] = []
    skip_count = 0
    attempts = 0
    completed = 0
    outcomes: Counter[str] = Counter()
    decided_by: Counter[str] = Counter()
    unusable_assignments = 0
    weak_assignments = 0
    total_assignments = 0
    crosscheck_total = 0
    crosscheck_matches = 0

    for index in range(matches):
        attempts += 1
        snap = start_draft(
            match_id=f"cum-{label}-{index}",
            players=("p1", "p2"),
            universe_id="naruto",
            mode="ranked",
            catalog=catalog,
            rarity_weights=DEFAULT_RARITY_WEIGHTS,
            dataset_version=version,
            draw_source=draw_source,
        ).snapshot
        guard = 0
        while snap.status is MatchStatus.ACTIVE:
            guard += 1
            if guard > 200:
                break
            actor = snap.active_player_id
            assert actor is not None
            snap = shuffle(
                snap, player_id=actor, expected_revision=snap.revision, draw_source=draw_source
            ).snapshot
            held = snap.held_character
            assert held is not None
            rarity_draws[held.rarity_id] += 1

            assigned_ids = {cid for team in snap.teams.values() for cid in team.values()}
            eligible_ids = non_common_ids - assigned_ids - {held.character_id}
            if (
                held.rarity_id == "Common"
                and snap.skips_remaining[actor] > 0
                and eligible_ids
                and snap.last_skipped_id != held.character_id
            ):
                snap = skip_character(
                    snap, player_id=actor, expected_revision=snap.revision
                ).snapshot
                skip_count += 1
                continue

            roles = snap.remaining_roles()[actor]
            chosen_role = role_rng.choice(roles)
            snap = assign_role(
                snap, player_id=actor, role=chosen_role, expected_revision=snap.revision
            ).snapshot
            fit = fit_by_id[held.character_id][chosen_role.lower()]
            role_assignments[chosen_role.lower()][fit] += 1
            total_assignments += 1
            if fit == 0:
                unusable_assignments += 1
            if fit <= 1:
                weak_assignments += 1

        if snap.status is not MatchStatus.COMPLETED:
            continue
        completed += 1
        result = fast_resolve(snap, score_by_id)

        if index < CROSSCHECK_MATCHES:
            authoritative = resolve_match(
                build_resolve_request_from_completed_draft(snap), reader
            )
            crosscheck_total += 1
            if authoritative.ok and (
                authoritative.outcome == result["outcome"]
                and authoritative.decided_by == result["decided_by"]
                and all(
                    authoritative.matchups[i].winner
                    == result["matchups"][role]["winner"]
                    for i, role in enumerate(
                        ("captain", "strategist", "attacker", "tank", "assassin", "support", "healer")
                    )
                )
            ):
                crosscheck_matches += 1

        outcomes[result["outcome"].value] += 1
        decided_by[result["decided_by"].value] += 1
        team_scores.append(result["totals"]["player_1"] + result["totals"]["player_2"])
        for role, info in result["matchups"].items():
            matchup_counts[role] += 1
            matchup_margins[role] += abs(info["margin"])
            if info["winner"] is MatchupWinner.DRAW:
                matchup_draws[role] += 1
        for team in snap.teams.values():
            for role, cid in team.items():
                role_score_sum[role.lower()] += score_by_id[cid][role.lower()]
            healer_fits.append(fit_by_id[team["Healer"]]["healer"])

    total_draws = sum(rarity_draws.values())
    return {
        "dataset": label,
        "pool_size": len(characters),
        "matches_requested": matches,
        "matches_completed": completed,
        "draft_completion_rate_pct": round(100.0 * completed / attempts, 2),
        "seeds": {"draw": DRAW_SEED, "role_assignment": ROLE_SEED},
        "assignment_strategy": (
            "uniform random role from remaining roles; skip the first Common draw per "
            "player when a non-Common character remains and skips are available"
        ),
        "resolution_method": (
            "canonical RES-1.0 rules via fast in-process path; cross-checked against "
            "app.resolution.resolve_match on sampled matches"
        ),
        "resolution_crosscheck": {
            "matches_checked": crosscheck_total,
            "matches_identical": crosscheck_matches,
            "identical_pct": round(100.0 * crosscheck_matches / max(1, crosscheck_total), 2),
        },
        "rarity_weights": dict(DEFAULT_RARITY_WEIGHTS),
        "rarity_draw_distribution_pct": {
            tier: round(100.0 * rarity_draws[tier] / total_draws, 2)
            for tier in DEFAULT_RARITY_WEIGHTS
        },
        "team_score": {
            "mean": round(sum(team_scores) / len(team_scores), 2),
            "p10": percentile(team_scores, 0.10),
            "p25": percentile(team_scores, 0.25),
            "p50": percentile(team_scores, 0.50),
            "p75": percentile(team_scores, 0.75),
            "p90": percentile(team_scores, 0.90),
        },
        "average_assigned_role_scores": {
            role: round(role_score_sum[role] / max(1, matchup_counts[role]), 2)
            for role in sorted(role_score_sum)
        },
        "role_assignment_fit_distribution": {
            role: {str(level): role_assignments[role][level] for level in range(6)}
            for role in sorted(role_assignments)
        },
        "healer_quality": {
            "mean_assigned_healer_fit": round(sum(healer_fits) / len(healer_fits), 3),
            "teams_with_healer_fit_ge_3_pct": round(
                100.0 * sum(1 for fit in healer_fits if fit >= 3) / len(healer_fits), 2
            ),
            "teams_with_healer_fit_ge_4_pct": round(
                100.0 * sum(1 for fit in healer_fits if fit >= 4) / len(healer_fits), 2
            ),
        },
        "skip_utilization": {
            "skips_used": skip_count,
            "skips_per_attempt": round(skip_count / attempts, 3),
        },
        "match_outcomes": {
            key: round(100.0 * outcomes[key] / completed, 2)
            for key in ("player_1_win", "player_2_win", "draw")
        },
        "decided_by": {
            key: round(100.0 * decided_by[key] / completed, 2)
            for key in (item.value for item in DecidedBy)
        },
        "role_matchups": {
            role: {
                "count": matchup_counts[role],
                "draw_pct": round(100.0 * matchup_draws[role] / matchup_counts[role], 2),
                "mean_abs_margin": round(matchup_margins[role] / matchup_counts[role], 2),
            }
            for role in sorted(matchup_counts)
        },
        "weak_or_unusable_assignments": {
            "fit_0_pct": round(100.0 * unusable_assignments / total_assignments, 2),
            "fit_le_1_pct": round(100.0 * weak_assignments / total_assignments, 2),
        },
        "winner_claim": "none",
        "approval_claim": "none",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matches", type=int, default=20_000)
    parser.add_argument("--out", default="naruto_cumulative_balance_simulation.json")
    args = parser.parse_args()
    comparison = json.loads((ROOT / "naruto_cumulative_roster_comparison.json").read_text(encoding="utf-8"))
    results: dict[str, Any] = {
        "generated_at": "2026-11-27",
        "engine": "app.engine draft engine + RES-1.0 fast resolver cross-checked with app.resolution",
        "matches_per_dataset": args.matches,
        "datasets": {},
        "strategy_note": (
            "Simulated strategies are deterministic and do not represent human behavior."
        ),
    }
    for label in ("A", "B", "C"):
        started = time.time()
        results["datasets"][label] = simulate(comparison, label, args.matches)
        results["datasets"][label]["runtime_seconds"] = round(time.time() - started, 2)
        print(f"dataset {label} done in {results['datasets'][label]['runtime_seconds']}s")
    (ROOT / args.out).write_text(
        json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        label: {
            "completed": data["matches_completed"],
            "mean_team_score": data["team_score"]["mean"],
            "healer_ge3_pct": data["healer_quality"]["teams_with_healer_fit_ge_3_pct"],
            "fit0_pct": data["weak_or_unusable_assignments"]["fit_0_pct"],
            "crosscheck": data["resolution_crosscheck"],
        }
        for label, data in results["datasets"].items()
    }, indent=2))


if __name__ == "__main__":
    main()
