"""Tests T1-T5, T7-T9 for Module 2 Core Scoring Engine."""

from __future__ import annotations

import copy
from collections import Counter

import pytest

from app.scoring import (
    SCORE_1_0_CONFIG,
    SCORE_1_0_PERCENT_WEIGHTS,
    SCORE_1_0_VERSION,
    SCORING_ROLES,
    score_batch,
    score_record,
)

# Independently hand-derived role weights (%) from Spec §3.1
_INDEPENDENT_PERCENT_WEIGHTS: dict[str, tuple[int, int]] = {
    "captain": (60, 40),
    "strategist": (85, 15),
    "attacker": (50, 50),
    "tank": (50, 50),
    "assassin": (65, 35),
    "support": (85, 15),
    "healer": (85, 15),
}


def _independent_expected_score(role: str, fit: int, power: int) -> int:
    fit_w, power_w = _INDEPENDENT_PERCENT_WEIGHTS[role]
    numerator = fit * fit_w + power * power_w
    assert numerator % 5 == 0
    return numerator // 5


def _full_fit(value: int = 0) -> dict[str, int]:
    return {role: value for role in SCORING_ROLES}


def test_t1_exhaustive_210_role_fit_power_combinations() -> None:
    """T1: All 30 Fit x Power pairs in each of 7 roles (210 cases) match independent table."""
    checked = 0
    for role in SCORING_ROLES:
        for fit_val in range(6):
            for power_val in range(1, 6):
                fit_map = _full_fit(0)
                fit_map[role] = fit_val
                out = score_record(
                    {"character_id": f"{role}_{fit_val}_{power_val}", "power": power_val, "fit": fit_map},
                    SCORE_1_0_CONFIG,
                )
                assert out.scores[role] == _independent_expected_score(role, fit_val, power_val)
                checked += 1
    assert checked == 210


def test_t2_score_ranges_minimums_and_maximums() -> None:
    """T2: Role minimums 8, 3, 10, 10, 7, 3, 3; every max 100; 0 never attainable."""
    expected_mins = {
        "captain": 8,
        "strategist": 3,
        "attacker": 10,
        "tank": 10,
        "assassin": 7,
        "support": 3,
        "healer": 3,
    }
    min_out = score_record({"character_id": "min_char", "power": 1, "fit": _full_fit(0)})
    max_out = score_record({"character_id": "max_char", "power": 5, "fit": _full_fit(5)})

    for role in SCORING_ROLES:
        assert min_out.scores[role] == expected_mins[role]
        assert max_out.scores[role] == 100
        for fit_val in range(6):
            for power_val in range(1, 6):
                fit_map = _full_fit(0)
                fit_map[role] = fit_val
                s = score_record({"character_id": "c", "power": power_val, "fit": fit_map}).scores[role]
                assert expected_mins[role] <= s <= 100
                assert s != 0


def test_t3_distinct_score_counts_per_role() -> None:
    """T3: Captain 22, Strategist 30, Attacker 10, Tank 10, Assassin 30, Support 30, Healer 30."""
    expected_distinct = {
        "captain": 22,
        "strategist": 30,
        "attacker": 10,
        "tank": 10,
        "assassin": 30,
        "support": 30,
        "healer": 30,
    }
    for role in SCORING_ROLES:
        seen = set()
        for fit_val in range(6):
            for power_val in range(1, 6):
                fit_map = _full_fit(0)
                fit_map[role] = fit_val
                seen.add(score_record({"character_id": "c", "power": power_val, "fit": fit_map}).scores[role])
        assert len(seen) == expected_distinct[role]


def test_t4_uniform_equal_score_probability() -> None:
    """T4: Attacker/Tank 12.2%, Captain 5.1%, others 3.3% (one decimal place)."""
    expected_pct = {
        "captain": 5.1,
        "strategist": 3.3,
        "attacker": 12.2,
        "tank": 12.2,
        "assassin": 3.3,
        "support": 3.3,
        "healer": 3.3,
    }
    for role in SCORING_ROLES:
        counts: Counter[int] = Counter()
        for fit_val in range(6):
            for power_val in range(1, 6):
                fit_map = _full_fit(0)
                fit_map[role] = fit_val
                score = score_record({"character_id": "c", "power": power_val, "fit": fit_map}).scores[role]
                counts[score] += 1
        # Uniform random pair with replacement over 30 (Fit, Power) combinations
        prob_pct = round(sum((c / 30.0) ** 2 for c in counts.values()) * 100.0, 1)
        assert prob_pct == expected_pct[role]


def test_t5_monotonicity_fit_power_swap_and_role_independence() -> None:
    """T5: Monotonic in Fit & Power; Fit dominates Strategist/Support/Healer; swap; independence."""
    for role in SCORING_ROLES:
        for fit_val in range(6):
            for power_val in range(1, 6):
                fit_map = _full_fit(0)
                fit_map[role] = fit_val
                base = score_record({"character_id": "c", "power": power_val, "fit": fit_map}).scores[role]
                if fit_val < 5:
                    fit_up = _full_fit(0)
                    fit_up[role] = fit_val + 1
                    assert score_record({"character_id": "c", "power": power_val, "fit": fit_up}).scores[role] > base
                if power_val < 5:
                    assert score_record({"character_id": "c", "power": power_val + 1, "fit": fit_map}).scores[role] > base

    # Strategist, Support, Healer: 1 Fit level (17) outweighs max Power gap (4*3 = 12)
    for role in ("strategist", "support", "healer"):
        for fit_low in range(5):
            f_low = _full_fit(0)
            f_low[role] = fit_low
            f_high = _full_fit(0)
            f_high[role] = fit_low + 1
            s_low_max_p = score_record({"character_id": "a", "power": 5, "fit": f_low}).scores[role]
            s_high_min_p = score_record({"character_id": "b", "power": 1, "fit": f_high}).scores[role]
            assert s_high_min_p > s_low_max_p

    # Attacker & Tank swap Fit and Power equivalently (over shared range 1..5)
    for role in ("attacker", "tank"):
        for a in range(1, 6):
            for b in range(1, 6):
                fa = _full_fit(0)
                fa[role] = a
                fb = _full_fit(0)
                fb[role] = b
                assert (
                    score_record({"character_id": "x", "power": b, "fit": fa}).scores[role]
                    == score_record({"character_id": "y", "power": a, "fit": fb}).scores[role]
                )

    # Role independence: changing one Fit changes only that role's score
    base_fit = _full_fit(2)
    base_scores = score_record({"character_id": "indep", "power": 3, "fit": base_fit}).scores
    for changed_role in SCORING_ROLES:
        mod_fit = dict(base_fit)
        mod_fit[changed_role] = 5
        mod_scores = score_record({"character_id": "indep", "power": 3, "fit": mod_fit}).scores
        for r in SCORING_ROLES:
            if r == changed_role:
                assert mod_scores[r] != base_scores[r]
            else:
                assert mod_scores[r] == base_scores[r]


def test_t7_t8_determinism_order_independence_immutability_and_passthrough() -> None:
    """T7 & T8: Same batch 3x and reversed -> identical per-record output, no mutation."""
    raw_batch = [
        {
            "character_id": "alpha",
            "power": 5,
            "fit": {"captain": 4, "strategist": 3, "attacker": 5, "tank": 3, "assassin": 1, "support": 4, "healer": 1},
        },
        {
            "character_id": "beta",
            "power": 2,
            "fit": {"captain": 2, "strategist": 2, "attacker": 1, "tank": 1, "assassin": 2, "support": 4, "healer": 1},
        },
    ]
    snapshot_input = copy.deepcopy(raw_batch)

    runs = [score_batch(raw_batch) for _ in range(3)]
    rev_run = score_batch(list(reversed(raw_batch)))

    assert raw_batch == snapshot_input  # no input mutation
    for run in runs:
        assert run.accepted
        assert run.scoring_version == SCORE_1_0_VERSION
        assert [r.to_dict() for r in run.results] == [r.to_dict() for r in runs[0].results]

    rev_by_id = {r.character_id: r for r in rev_run.results}
    for out in runs[0].results:
        assert rev_by_id[out.character_id].to_dict() == out.to_dict()

    # T8: exact pass-through of Power and Fit
    for orig, out in zip(raw_batch, runs[0].results):
        assert out.character_id == orig["character_id"]
        assert out.power == orig["power"]
        assert dict(out.fit) == orig["fit"]


# 14 provisional Naruto calibration fixtures from Module 2B §2.1 & §2.2 (arithmetic regression only)
_NARUTO_FIXTURES: list[tuple[str, int, tuple[int, ...], tuple[int, ...]]] = [
    ("naruto", 5, (4, 3, 5, 3, 1, 4, 1), (88, 66, 100, 80, 48, 83, 32)),
    ("sasuke", 5, (2, 3, 5, 3, 3, 2, 0), (64, 66, 100, 80, 74, 49, 15)),
    ("shikamaru", 3, (4, 5, 2, 1, 2, 3, 0), (72, 94, 50, 40, 47, 60, 9)),
    ("sakura", 3, (2, 2, 3, 2, 1, 3, 4), (48, 43, 60, 50, 34, 60, 77)),
    ("tsunade", 4, (4, 3, 4, 3, 1, 3, 5), (80, 63, 80, 70, 41, 63, 97)),
    ("kakashi", 4, (4, 4, 4, 2, 4, 3, 0), (80, 80, 80, 60, 80, 63, 12)),
    ("itachi", 4, (3, 5, 4, 4, 4, 2, 0), (68, 97, 80, 80, 80, 46, 12)),
    ("gaara", 4, (4, 3, 3, 4, 1, 4, 0), (80, 63, 70, 80, 41, 80, 12)),
    ("minato", 4, (3, 4, 4, 2, 4, 4, 0), (68, 80, 80, 60, 80, 80, 12)),
    ("madara", 5, (4, 4, 5, 4, 1, 1, 0), (88, 83, 100, 90, 48, 32, 15)),
    ("rock_lee", 3, (2, 2, 4, 2, 2, 1, 0), (48, 43, 70, 50, 47, 26, 9)),
    ("hinata", 3, (2, 2, 3, 3, 3, 3, 1), (48, 43, 60, 60, 60, 60, 26)),
    ("kabuto", 4, (3, 4, 3, 2, 4, 2, 3), (68, 80, 70, 60, 80, 46, 63)),
    ("ino", 2, (2, 2, 1, 1, 2, 4, 1), (40, 40, 30, 30, 40, 74, 23)),
]


def test_t9_regression_14_naruto_calibration_sets_98_scores() -> None:
    """T9: All 98 role scores from 2B §2.1 & §2.2 match exactly."""
    records = [
        {
            "character_id": cid,
            "power": power,
            "fit": dict(zip(SCORING_ROLES, fits)),
        }
        for cid, power, fits, _ in _NARUTO_FIXTURES
    ]
    batch = score_batch(records)
    assert batch.accepted is True
    assert len(batch.results) == 14

    compared = 0
    for (_, _, _, expected_scores), result in zip(_NARUTO_FIXTURES, batch.results):
        for role, expected in zip(SCORING_ROLES, expected_scores):
            assert result.scores[role] == expected
            compared += 1
    assert compared == 98
