"""Regression tests for Naruto cumulative simulation integrity."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from app.scoring.models import SCORE_1_0_CONFIG

ROOT = Path("data")
ROLES = ("captain", "strategist", "attacker", "tank", "assassin", "support", "healer")


def load(name: str):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def percentile(histogram: dict[str, int], fraction: float) -> int:
    counts = Counter({int(k): int(v) for k, v in histogram.items()})
    total = sum(counts.values())
    target = fraction * (total - 1)
    cumulative = 0
    for score in sorted(counts):
        cumulative += counts[score]
        if cumulative > target:
            return score
    return max(counts)


def test_previous_artifacts_preserved() -> None:
    assert (ROOT / "naruto_cumulative_balance_simulation_previous.json").exists()
    assert (Path("docs") / "NARUTO_CUMULATIVE_BALANCE_REPORT_PREVIOUS.md").exists()
    assert (Path("docs") / "NARUTO_SIMULATION_INTEGRITY_AUDIT_REPORT.md").exists()


@pytest.mark.parametrize("label", ["A", "B", "C"])
def test_score_bounds_and_assignment_integrity(label: str) -> None:
    data = load("naruto_cumulative_balance_simulation_corrected.json")["datasets"][label]
    verification = data["verification"]
    assert verification["maximum_role_score_observed"] <= 100
    assert verification["maximum_team_score_observed"] <= 700
    assert verification["team_score_bounds_ok"] is True
    assert verification["completed_matches_with_exactly_14_assignments"] == data["matches_completed"]
    assert verification["completed_matches_with_verified_team_sums"] == data["matches_completed"]
    assert data["matches_completed"] >= 20_000
    assert data["draft_completion_rate_pct"] == 100.0


@pytest.mark.parametrize("label", ["A", "B", "C"])
def test_reported_means_and_percentiles_match_histogram(label: str) -> None:
    data = load("naruto_cumulative_balance_simulation_corrected.json")["datasets"][label]
    histogram = {int(k): int(v) for k, v in data["team_score"]["histogram"].items()}
    count = sum(histogram.values())
    assert count == 2 * data["matches_completed"]
    mean = sum(score * n for score, n in histogram.items()) / count
    assert abs(mean - data["team_score"]["mean"]) <= 0.01
    for key, fraction in (("p10", 0.10), ("p25", 0.25), ("p50", 0.50), ("p75", 0.75), ("p90", 0.90)):
        assert data["team_score"][key] == percentile(histogram, fraction)
    expected_combined = 2 * mean
    assert abs(data["combined_match_score"]["mean"] - expected_combined) <= 0.02


@pytest.mark.parametrize("label", ["A", "B", "C"])
def test_role_scores_obey_scoring_bounds(label: str) -> None:
    data = load("naruto_cumulative_balance_simulation_corrected.json")["datasets"][label]
    for role in ROLES:
        bounds = data["role_score_bounds"][role]
        assert 0 <= bounds["min"] <= bounds["max"] <= 100
        assert bounds["assignments"] > 0
        average = data["average_assigned_role_scores"][role]
        assert average == bounds["mean"]
        assert 0 <= average <= 100
        power_points = SCORE_1_0_CONFIG.weights[role].power_points
        fit0_max = 5 * power_points
        fit0_mean = data["assignment_metrics"]["fit_0_by_role"][role]["mean_score"]
        assert 0 <= fit0_mean <= fit0_max


@pytest.mark.parametrize("label", ["A", "B", "C"])
def test_assignment_denominators_and_aggregate_bounds(label: str) -> None:
    data = load("naruto_cumulative_balance_simulation_corrected.json")["datasets"][label]
    metrics = data["assignment_metrics"]
    assert "one role assignment" in metrics["denominator"]
    assert metrics["total_assignments"] == 14 * data["matches_completed"]
    assert 0 <= metrics["fit_0_assignment_rate_pct"] <= 100
    assert 0 <= metrics["fit_le_1_assignment_rate_pct"] <= 100
    assert 0 <= metrics["low_value_assignment_rate_pct"] <= 100
    assert abs(sum(data["match_outcomes"].values()) - 100.0) <= 0.1
    assert abs(sum(data["decided_by"].values()) - 100.0) <= 0.1
    assert abs(sum(data["rarity_draw_distribution_pct"].values()) - 100.0) <= 0.1


@pytest.mark.parametrize("label", ["A", "B", "C"])
def test_healer_metric_distinctions(label: str) -> None:
    data = load("naruto_cumulative_balance_simulation_corrected.json")["datasets"][label]
    healer = data["healer_metrics"]
    pool = data["pool_size"]
    for level in (1, 2, 3, 4, 5):
        absolute = healer["roster_absolute"][f"fit_ge_{level}"]
        proportion = healer["roster_proportion_pct"][f"fit_ge_{level}"]
        assert 0 <= absolute <= pool
        assert abs(proportion - round(100.0 * absolute / pool, 2)) <= 0.01
    assert healer["roster_absolute"]["fit_ge_3"] >= healer["roster_absolute"]["fit_ge_4"]
    assert healer["teams_with_healer_fit_ge_3"] >= healer["teams_with_healer_fit_ge_4"]
    assert healer["healer_assignments"] == 2 * data["matches_completed"]
    assert 0 <= healer["mean_assigned_healer_fit"] <= 5


def test_fast_path_crosscheck_against_authoritative_resolution() -> None:
    for label in ("A", "B", "C"):
        data = load("naruto_cumulative_balance_simulation_corrected.json")["datasets"][label]
        assert data["resolution_crosscheck"]["matches_checked"] == 100
        assert data["resolution_crosscheck"]["identical_pct"] == 100.0
        assert data["resolution_crosscheck"]["score_identical_pct"] == 100.0
