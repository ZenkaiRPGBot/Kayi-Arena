"""Exhaustive boundary tests for Rarity Points v0.2 (Section 18)."""

from __future__ import annotations

from app.scoring import RARITY_V02_VERSION, SCORING_ROLES, classify_rarity_v02


def _fits(**overrides: int) -> dict[str, int]:
    base = {role: 0 for role in SCORING_ROLES}
    base.update(overrides)
    return base


def test_rarity_v02_thresholds_and_bonuses() -> None:
    # Common: RP < 60 -> Fit 3 Attacker (13*3=39), Power 2 (7*2=14) => 53, no bonuses
    # Wait: Attacker is 65/35 -> 13*3 + 7*2 = 53; Captain is 60/40 -> 12*3 + 8*2 = 52; Healer is 85/15 -> 17*2 + 3*2 = 40
    common = classify_rarity_v02(power=2, role_fits=_fits(healer=2))
    assert common.version == RARITY_V02_VERSION
    assert common.rarity_points == 40
    assert common.base_rarity == "Common"
    assert common.final_rarity == "Common"

    # Uncommon boundary: RP == 60 -> Healer Fit 3 (51) + Power 3 (9) = 60
    uncommon = classify_rarity_v02(power=3, role_fits=_fits(healer=3))
    assert uncommon.rarity_points == 60
    assert uncommon.base_rarity == "Uncommon"

    # Rare boundary: Healer Fit 4 (68) + Power 4 (12) = 80 + combat_bonus(3) = 83
    rare = classify_rarity_v02(power=4, role_fits=_fits(healer=4))
    assert rare.highest_role_score == 80
    assert rare.combat_bonus == 3
    assert rare.rarity_points == 83
    assert rare.base_rarity == "Rare"

    # Epic boundary: Strategist Fit 5 (85) + Power 1 (3) = 88 + specialist(3) = 91
    epic = classify_rarity_v02(power=1, role_fits=_fits(strategist=5))
    assert epic.highest_role_score == 88
    assert epic.specialist_bonus == 3
    assert epic.rarity_points == 91
    assert epic.base_rarity == "Epic"

    # Legendary boundary: Attacker Fit 5 (65) + Power 5 (35) = 100 + combat(5) = 105
    legendary = classify_rarity_v02(power=5, role_fits=_fits(attacker=5))
    assert legendary.combat_bonus == 5
    assert legendary.rarity_points == 105
    assert legendary.base_rarity == "Legendary"


def test_rarity_v02_specialist_once_and_versatility_bonus() -> None:
    # Multiple specialist 5s only grant +3 once
    res = classify_rarity_v02(
        power=3,
        role_fits=_fits(Strategist=5, Support=5, Healer=5),
    )
    # Score = 5*17 + 3*3 = 94 in all 3 -> highest=94, specialist=3, versatility=2*(3-1)=4
    assert res.highest_role_score == 94
    assert res.specialist_bonus == 3
    assert res.versatility_bonus == 4
    assert res.rarity_points == 101
    assert res.final_rarity == "Legendary"


def test_naruto_healer_provisional_floors() -> None:
    # Healer Fit 4, Power 1 => score 68 + 3 = 71 (Uncommon) -> floored to Rare
    h4 = classify_rarity_v02(
        power=1,
        role_fits=_fits(Healer=4),
        apply_naruto_healer_floor=True,
    )
    assert h4.base_rarity == "Uncommon"
    assert h4.final_rarity == "Rare"
    assert h4.floor_applied == "healer_fit_4_min_rare"

    # Healer Fit 4, Power 5 => score 83 + 5 = 88 (Rare) -> stays Rare (no floor needed)
    h4_high = classify_rarity_v02(
        power=5,
        role_fits=_fits(Healer=4),
        apply_naruto_healer_floor=True,
    )
    assert h4_high.base_rarity == "Rare"
    assert h4_high.final_rarity == "Rare"
    assert h4_high.floor_applied is None

    # Healer Fit 5, Power 1 => score 88 + 3(spec) = 91 (Epic) -> already Epic
    # Test with forced role_scores below 90 to verify Healer Fit 5 floor -> Epic
    h5_low = classify_rarity_v02(
        power=1,
        role_fits=_fits(Healer=5),
        role_scores={r: 70 for r in SCORING_ROLES},
        apply_naruto_healer_floor=True,
    )
    assert h5_low.base_rarity == "Common" or h5_low.base_rarity == "Uncommon"
    assert h5_low.final_rarity == "Epic"
    assert h5_low.floor_applied == "healer_fit_5_min_epic"
