"""Corrected cumulative Naruto simulation with explicit, bounded metrics.

Fixes:
- role-score average denominator (assignments, not matchup count);
- per-team vs combined match score labels;
- percentiles computed from per-team score histograms;
- explicit Fit 0 / low-value assignment denominators;
- healer absolute counts vs proportions vs acquisition rates;
- verification of 14 assignments and exact team-score sums per match.
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
ROLES = ("captain", "strategist", "attacker", "tank", "assassin", "support", "healer")
LOW_VALUE_SCORE_THRESHOLD = 50  # below half of the 100-point role maximum


def percentile_from_histogram(histogram: Counter[int], fraction: float) -> int:
    total = sum(histogram.values())
    if total == 0:
        return 0
    target = fraction * (total - 1)
    cumulative = 0
    for score in sorted(histogram):
        cumulative += histogram[score]
        if cumulative > target:
            return score
    return max(histogram)


def build_reader(dataset: dict[str, Any], version: str) -> RepositoryDatasetReader:
    records = [
        DatasetRecord(
            character_id=item["character_id"],
            power=item["power"],
            fit=item["fit"],
            scores=item["scores"],
            status=RecordStatus.DRAFT,
            revision_ref="cumulative-analysis-corrected",
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
        assert 0 <= s1 <= 100 and 0 <= s2 <= 100
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
    version = f"naruto-cumulative-{label.lower()}-corrected"
    reader = build_reader(dataset, version)
    fit_by_id = {item["character_id"]: item["fit"] for item in characters}
    score_by_id = {item["character_id"]: item["scores"] for item in characters}
    catalog = tuple(
        CatalogEntry(character_id=item["character_id"], rarity_id=item["rarity"])
        for item in characters
    )
    non_common_ids = {item["character_id"] for item in characters if item["rarity"] in NON_COMMON}

    draw_source = SeededDrawSource(seed=DRAW_SEED)
    role_rng = random.Random(ROLE_SEED)
    rarity_draws: Counter[str] = Counter()
    assignment_counts_by_role: Counter[str] = Counter()
    role_score_sum: Counter[str] = Counter()
    role_score_min: dict[str, int] = {role: 100 for role in ROLES}
    role_score_max: dict[str, int] = {role: 0 for role in ROLES}
    fit_distribution_by_role: dict[str, Counter[int]] = {role: Counter() for role in ROLES}
    fit0_by_role: Counter[str] = Counter()
    fit0_score_sum_by_role: Counter[str] = Counter()
    matchup_counts: Counter[str] = Counter()
    matchup_draws: Counter[str] = Counter()
    matchup_margins: Counter[str] = Counter()
    team_score_histogram: Counter[int] = Counter()
    combined_score_sum = 0
    healer_fit_sum = 0
    healer_score_sum = 0
    healer_assignment_counts: Counter[int] = Counter()
    teams_with_healer_ge3 = 0
    teams_with_healer_ge4 = 0
    skip_count = 0
    attempts = 0
    completed = 0
    verified_14_assignments = 0
    verified_team_sums = 0
    outcomes: Counter[str] = Counter()
    decided_by: Counter[str] = Counter()
    total_assignments = 0
    fit0_assignments = 0
    fit0_score_sum = 0
    fit_le1_assignments = 0
    low_value_assignments = 0
    crosscheck_total = 0
    crosscheck_matches = 0
    crosscheck_score_matches = 0

    for index in range(matches):
        attempts += 1
        snap = start_draft(
            match_id=f"cum-corrected-{label}-{index}",
            players=("p1", "p2"),
            universe_id="naruto",
            mode="ranked",
            catalog=catalog,
            rarity_weights=DEFAULT_RARITY_WEIGHTS,
            dataset_version=version,
            draw_source=draw_source,
        ).snapshot
        match_assignments = 0
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
            role = chosen_role.lower()
            fit = fit_by_id[held.character_id][role]
            score = score_by_id[held.character_id][role]
            assert 0 <= score <= 100
            snap = assign_role(
                snap, player_id=actor, role=chosen_role, expected_revision=snap.revision
            ).snapshot

            assignment_counts_by_role[role] += 1
            role_score_sum[role] += score
            role_score_min[role] = min(role_score_min[role], score)
            role_score_max[role] = max(role_score_max[role], score)
            fit_distribution_by_role[role][fit] += 1
            total_assignments += 1
            match_assignments += 1
            if fit == 0:
                fit0_assignments += 1
                fit0_score_sum += score
                fit0_by_role[role] += 1
                fit0_score_sum_by_role[role] += score
            if fit <= 1:
                fit_le1_assignments += 1
            if score < LOW_VALUE_SCORE_THRESHOLD:
                low_value_assignments += 1

        if snap.status is not MatchStatus.COMPLETED:
            continue
        completed += 1
        if match_assignments == 14:
            verified_14_assignments += 1
        else:
            continue

        result = fast_resolve(snap, score_by_id)
        team_scores = {
            "player_1": sum(score_by_id[cid][role.lower()] for role, cid in snap.teams["p1"].items()),
            "player_2": sum(score_by_id[cid][role.lower()] for role, cid in snap.teams["p2"].items()),
        }
        assert team_scores["player_1"] == result["totals"]["player_1"]
        assert team_scores["player_2"] == result["totals"]["player_2"]
        assert all(0 <= value <= 700 for value in team_scores.values())
        verified_team_sums += 1
        combined_score_sum += team_scores["player_1"] + team_scores["player_2"]
        for value in team_scores.values():
            team_score_histogram[value] += 1

        if index < CROSSCHECK_MATCHES:
            authoritative = resolve_match(
                build_resolve_request_from_completed_draft(snap), reader
            )
            crosscheck_total += 1
            if authoritative.ok:
                same_result = (
                    authoritative.outcome == result["outcome"]
                    and authoritative.decided_by == result["decided_by"]
                    and all(
                        authoritative.matchups[i].winner
                        == result["matchups"][role]["winner"]
                        for i, role in enumerate(ROLES)
                    )
                )
                same_scores = (
                    authoritative.summary.total_player_1 == result["totals"]["player_1"]
                    and authoritative.summary.total_player_2 == result["totals"]["player_2"]
                )
                if same_result:
                    crosscheck_matches += 1
                if same_scores:
                    crosscheck_score_matches += 1

        outcomes[result["outcome"].value] += 1
        decided_by[result["decided_by"].value] += 1
        for role, info in result["matchups"].items():
            matchup_counts[role] += 1
            matchup_margins[role] += abs(info["margin"])
            if info["winner"] is MatchupWinner.DRAW:
                matchup_draws[role] += 1
        for team in snap.teams.values():
            healer_cid = team["Healer"]
            healer_fit = fit_by_id[healer_cid]["healer"]
            healer_score = score_by_id[healer_cid]["healer"]
            healer_fit_sum += healer_fit
            healer_score_sum += healer_score
            healer_assignment_counts[healer_fit] += 1
            if healer_fit >= 3:
                teams_with_healer_ge3 += 1
            if healer_fit >= 4:
                teams_with_healer_ge4 += 1

    total_draws = sum(rarity_draws.values())
    team_count = sum(team_score_histogram.values())
    roster = dataset["analysis"]
    return {
        "dataset": label,
        "pool_size": len(characters),
        "matches_requested": matches,
        "matches_completed": completed,
        "draft_completion_rate_pct": round(100.0 * completed / attempts, 2),
        "verification": {
            "completed_matches_with_exactly_14_assignments": verified_14_assignments,
            "completed_matches_with_verified_team_sums": verified_team_sums,
            "maximum_role_score_observed": max(role_score_max.values()),
            "maximum_team_score_observed": max(team_score_histogram),
            "team_score_bounds_ok": 0 <= min(team_score_histogram) and max(team_score_histogram) <= 700,
        },
        "seeds": {"draw": DRAW_SEED, "role_assignment": ROLE_SEED},
        "assignment_strategy": (
            "uniform random role from remaining roles; skip the first Common draw per "
            "player when a non-Common character remains and skips are available"
        ),
        "resolution_method": (
            "canonical RES-1.0 fast path, cross-checked against app.resolution.resolve_match "
            "for outcome, tiebreaker, matchup winners and team score totals"
        ),
        "resolution_crosscheck": {
            "matches_checked": crosscheck_total,
            "outcome_and_winners_identical": crosscheck_matches,
            "team_totals_identical": crosscheck_score_matches,
            "identical_pct": round(100.0 * crosscheck_matches / max(1, crosscheck_total), 2),
            "score_identical_pct": round(100.0 * crosscheck_score_matches / max(1, crosscheck_total), 2),
        },
        "rarity_weights": dict(DEFAULT_RARITY_WEIGHTS),
        "rarity_draw_distribution_pct": {
            tier: round(100.0 * rarity_draws[tier] / total_draws, 2)
            for tier in DEFAULT_RARITY_WEIGHTS
        },
        "team_score": {
            "scope": "one team = seven assigned roles; maximum 700",
            "mean": round(sum(k * v for k, v in team_score_histogram.items()) / team_count, 2),
            "p10": percentile_from_histogram(team_score_histogram, 0.10),
            "p25": percentile_from_histogram(team_score_histogram, 0.25),
            "p50": percentile_from_histogram(team_score_histogram, 0.50),
            "p75": percentile_from_histogram(team_score_histogram, 0.75),
            "p90": percentile_from_histogram(team_score_histogram, 0.90),
            "histogram": dict(sorted(team_score_histogram.items())),
        },
        "combined_match_score": {
            "scope": "both teams, fourteen assigned roles; maximum 1400",
            "mean": round(combined_score_sum / completed, 2),
        },
        "average_assigned_role_scores": {
            role: round(role_score_sum[role] / assignment_counts_by_role[role], 2)
            for role in ROLES
        },
        "role_score_bounds": {
            role: {
                "assignments": assignment_counts_by_role[role],
                "min": role_score_min[role],
                "max": role_score_max[role],
                "mean": round(role_score_sum[role] / assignment_counts_by_role[role], 2),
            }
            for role in ROLES
        },
        "assignment_metrics": {
            "denominator": "one denominator = one role assignment; 14 assignments per completed match",
            "total_assignments": total_assignments,
            "fit_0_assignments": fit0_assignments,
            "fit_0_assignment_rate_pct": round(100.0 * fit0_assignments / total_assignments, 2),
            "mean_fit_0_role_score": round(fit0_score_sum / max(1, fit0_assignments), 2),
            "fit_0_by_role": {
                role: {
                    "assignments": fit0_by_role[role],
                    "mean_score": round(
                        fit0_score_sum_by_role[role] / max(1, fit0_by_role[role]), 2
                    ),
                }
                for role in ROLES
            },
            "fit_le_1_assignments": fit_le1_assignments,
            "fit_le_1_assignment_rate_pct": round(
                100.0 * fit_le1_assignments / total_assignments, 2
            ),
            "low_value_assignments_score_lt_50": low_value_assignments,
            "low_value_assignment_rate_pct": round(
                100.0 * low_value_assignments / total_assignments, 2
            ),
        },
        "role_assignment_fit_distribution": {
            role: {str(level): fit_distribution_by_role[role][level] for level in range(6)}
            for role in ROLES
        },
        "healer_metrics": {
            "roster_absolute": {
                f"fit_ge_{level}": roster["healer_fit_counts"][f"ge_{level}"]
                for level in (1, 2, 3, 4, 5)
            },
            "roster_proportion_pct": {
                f"fit_ge_{level}": round(
                    100.0 * roster["healer_fit_counts"][f"ge_{level}"] / roster["character_count"], 2
                )
                for level in (1, 2, 3, 4, 5)
            },
            "healer_assignments": len(healer_assignment_counts) and sum(healer_assignment_counts.values()),
            "mean_assigned_healer_fit": round(healer_fit_sum / team_count, 3),
            "mean_assigned_healer_role_score": round(healer_score_sum / team_count, 2),
            "assigned_healer_fit_distribution": {
                str(level): healer_assignment_counts[level] for level in range(6)
            },
            "teams_with_healer_fit_ge_3": teams_with_healer_ge3,
            "teams_with_healer_fit_ge_3_pct": round(100.0 * teams_with_healer_ge3 / team_count, 2),
            "teams_with_healer_fit_ge_4": teams_with_healer_ge4,
            "teams_with_healer_fit_ge_4_pct": round(100.0 * teams_with_healer_ge4 / team_count, 2),
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
        "winner_claim": "none",
        "approval_claim": "none",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matches", type=int, default=20_000)
    parser.add_argument("--out", default="naruto_cumulative_balance_simulation_corrected.json")
    args = parser.parse_args()
    comparison = json.loads((ROOT / "naruto_cumulative_roster_comparison.json").read_text(encoding="utf-8"))
    results: dict[str, Any] = {
        "generated_at": "2026-11-27",
        "engine": "app.engine + RES-1.0 fast path cross-checked with app.resolution.resolve_match",
        "matches_per_dataset": args.matches,
        "datasets": {},
        "strategy_note": "Deterministic simulated behavior; not representative of human play.",
        "correction_note": (
            "Corrects role-score average denominator, per-team/combined score labels, "
            "percentile source, assignment denominators and healer metric distinctions."
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
            "team_mean": data["team_score"]["mean"],
            "combined_mean": data["combined_match_score"]["mean"],
            "fit0_pct": data["assignment_metrics"]["fit_0_assignment_rate_pct"],
            "healer_ge3_pct": data["healer_metrics"]["teams_with_healer_fit_ge_3_pct"],
            "p10": data["team_score"]["p10"],
        }
        for label, data in results["datasets"].items()
    }, indent=2))


if __name__ == "__main__":
    main()
