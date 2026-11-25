"""Tests for pool boundaries, rarity weights, exact probabilities, and statistics."""

from __future__ import annotations

import math
from collections import Counter

import pytest

from app.engine import (
    CatalogEntry,
    EngineConfigError,
    MatchStatus,
    ScriptedDrawSource,
    SeededDrawSource,
    assign_role,
    character_probabilities,
    compute_character_probabilities,
    shuffle,
    start_draft,
)
from tests.conftest import DEFAULT_WEIGHTS, make_catalog


def _chi_square_p_value(observed: list[float], expected: list[float]) -> float:
    """Upper-tail p-value for Pearson chi-square using Wilson-Hilferty / exact df."""
    chi2 = sum((o - e) ** 2 / e for o, e in zip(observed, expected))
    df = len(observed) - 1
    if df <= 0:
        return 1.0
    # Regularized upper incomplete gamma Q(df/2, chi2/2) via series / continued fraction
    # For small df (1..10), simple numerical survival via math.erfc or series is exact.
    a = df / 2.0
    x = chi2 / 2.0
    if x <= 0.0:
        return 1.0
    # Lower incomplete gamma P(a, x) via power series when x < a + 1
    if x < a + 1.0:
        term = 1.0 / a
        total = term
        k = 1
        while abs(term) > 1e-14 * abs(total):
            term *= x / (a + k)
            total += term
            k += 1
        lower = total * math.exp(-x + a * math.log(x) - math.lgamma(a))
        return max(0.0, 1.0 - lower)
    # Continued fraction for upper incomplete gamma Q(a, x)
    b = x + 1.0 - a
    c = 1.0 / 1e-30
    d = 1.0 / b
    h = d
    for i in range(1, 200):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < 1e-30:
            d = 1e-30
        c = b + an / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-14:
            break
    return max(0.0, min(1.0, math.exp(-x + a * math.log(x) - math.lgamma(a)) * h))


def test_pool_size_and_validation_boundaries() -> None:
    with pytest.raises(EngineConfigError):
        start_draft(
            match_id="m13",
            players=("p1", "p2"),
            universe_id="u1",
            mode="ranked",
            catalog=make_catalog(13),
            rarity_weights=DEFAULT_WEIGHTS,
            dataset_version="ds-1",
        )

    # 14 unique chars is valid
    res = start_draft(
        match_id="m14",
        players=("p1", "p2"),
        universe_id="u1",
        mode="ranked",
        catalog=make_catalog(14),
        rarity_weights=DEFAULT_WEIGHTS,
        dataset_version="ds-1",
        draw_source=SeededDrawSource(1),
    )
    assert res.accepted

    # Duplicate IDs rejected
    dup_catalog = make_catalog(14) + (CatalogEntry("char_000", "Common"),)
    with pytest.raises(EngineConfigError):
        start_draft(
            match_id="mdup",
            players=("p1", "p2"),
            universe_id="u1",
            mode="ranked",
            catalog=dup_catalog,
            rarity_weights=DEFAULT_WEIGHTS,
            dataset_version="ds-1",
        )

    # Zero rarity weight rejected
    bad_weights = dict(DEFAULT_WEIGHTS, Mythic=0.0)
    with pytest.raises(EngineConfigError):
        start_draft(
            match_id="mzero",
            players=("p1", "p2"),
            universe_id="u1",
            mode="ranked",
            catalog=make_catalog(14),
            rarity_weights=bad_weights,
            dataset_version="ds-1",
        )


def test_single_rarity_pool_completes() -> None:
    catalog = tuple(CatalogEntry(f"c_{i}", "Common") for i in range(14))
    source = SeededDrawSource(seed=42)
    snap = start_draft(
        match_id="m-single-rarity",
        players=("p1", "p2"),
        universe_id="u1",
        mode="friendly",
        catalog=catalog,
        rarity_weights={"Common": 100.0},
        dataset_version="ds-1",
        draw_source=source,
    ).snapshot

    probs = character_probabilities(snap)
    assert len(probs) == 14
    assert all(math.isclose(p, 1.0 / 14.0) for p in probs.values())

    while snap.status is MatchStatus.ACTIVE:
        actor = snap.active_player_id
        assert actor is not None
        snap = shuffle(snap, player_id=actor, expected_revision=snap.revision, draw_source=source).snapshot
        role = snap.remaining_roles()[actor][0]
        snap = assign_role(snap, player_id=actor, role=role, expected_revision=snap.revision).snapshot

    assert snap.status is MatchStatus.COMPLETED


def test_exact_probabilities_across_three_depletion_scenarios() -> None:
    """Acceptance criterion 5: exact probability checks for >= 3 depletion scenarios."""
    weights = {"Mythic": 20.0, "Rare": 30.0, "Common": 50.0}
    catalog = (
        tuple(CatalogEntry(f"m{i}", "Mythic") for i in range(2))
        + tuple(CatalogEntry(f"r{i}", "Rare") for i in range(6))
        + tuple(CatalogEntry(f"c{i}", "Common") for i in range(6))
    )

    # Scenario 1: all 3 rarities present (total weight = 100)
    p1 = compute_character_probabilities(catalog, weights)
    assert math.isclose(p1["m0"], 0.20 / 2)
    assert math.isclose(p1["r0"], 0.30 / 6)
    assert math.isclose(p1["c0"], 0.50 / 6)
    assert math.isclose(sum(p1.values()), 1.0)

    # Scenario 2: Mythic depleted -> Rare (30) + Common (50) renormalize over 80
    no_mythic = tuple(c for c in catalog if c.rarity_id != "Mythic")
    p2 = compute_character_probabilities(no_mythic, weights)
    assert "m0" not in p2
    assert math.isclose(p2["r0"], (30.0 / 80.0) / 6)
    assert math.isclose(p2["c0"], (50.0 / 80.0) / 6)
    assert math.isclose(sum(p2.values()), 1.0)

    # Scenario 3: Mythic & Rare depleted -> Common gets 100% split across remaining 3 chars
    only_3_common = tuple(CatalogEntry(f"c{i}", "Common") for i in range(3))
    p3 = compute_character_probabilities(only_3_common, weights)
    assert all(math.isclose(v, 1.0 / 3.0) for v in p3.values())
    assert math.isclose(sum(p3.values()), 1.0)


def test_statistical_rarity_distribution_and_uniformity_100k_draws() -> None:
    """Acceptance criterion 5: 100,000 first draws match expected frequencies (p >= 0.001)."""
    weights = {"Mythic": 10.0, "Rare": 30.0, "Common": 60.0}
    catalog = (
        tuple(CatalogEntry(f"m{i}", "Mythic") for i in range(2))
        + tuple(CatalogEntry(f"r{i}", "Rare") for i in range(5))
        + tuple(CatalogEntry(f"c{i}", "Common") for i in range(8))
    )
    rng = SeededDrawSource(seed=20261125)
    rarity_counts: Counter[str] = Counter()
    rare_char_counts: Counter[str] = Counter()

    n_draws = 100_000
    for _ in range(n_draws):
        chosen = rng.draw_character(catalog, weights)
        rarity_counts[chosen.rarity_id] += 1
        if chosen.rarity_id == "Rare":
            rare_char_counts[chosen.character_id] += 1

    # Rarity chi-square
    p_rarity = _chi_square_p_value(
        [rarity_counts["Mythic"], rarity_counts["Rare"], rarity_counts["Common"]],
        [n_draws * 0.10, n_draws * 0.30, n_draws * 0.60],
    )
    assert p_rarity >= 0.001

    # Uniformity within Rare (5 characters)
    total_rare = sum(rare_char_counts.values())
    p_uniform = _chi_square_p_value(
        [rare_char_counts[f"r{i}"] for i in range(5)],
        [total_rare / 5.0] * 5,
    )
    assert p_uniform >= 0.001


def test_seeded_determinism_and_draw_source_call_counts() -> None:
    catalog = make_catalog(18)

    def run_once(seed: int) -> str:
        src = SeededDrawSource(seed)
        snap = start_draft(
            match_id="det-1",
            players=("p1", "p2"),
            universe_id="u1",
            mode="ranked",
            catalog=catalog,
            rarity_weights=DEFAULT_WEIGHTS,
            dataset_version="v1",
            draw_source=src,
        ).snapshot
        while snap.status is MatchStatus.ACTIVE:
            actor = snap.active_player_id
            assert actor is not None
            snap = shuffle(snap, player_id=actor, expected_revision=snap.revision, draw_source=src).snapshot
            role = snap.remaining_roles()[actor][0]
            snap = assign_role(snap, player_id=actor, role=role, expected_revision=snap.revision).snapshot
        assert src.starter_calls == 1
        assert src.draw_calls == 14
        return snap.state_hash()

    assert run_once(777) == run_once(777)
    assert run_once(777) != run_once(778)
