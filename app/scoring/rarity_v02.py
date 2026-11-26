"""Rarity Points v0.2 classification utility (separate from scoring & Telegram UI).

Implements Claude's Rarity Points v0.2 formula for balance testing without
modifying canonical Power/Fit ratings or existing published datasets.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from app.scoring.engine import score_record
from app.scoring.models import RatingInput, SCORING_ROLES

RARITY_V02_VERSION = "RARITY-0.2"

_RARITY_ORDER: dict[str, int] = {
    "Common": 0,
    "Uncommon": 1,
    "Rare": 2,
    "Epic": 3,
    "Legendary": 4,
}


@dataclass(frozen=True, slots=True)
class RarityClassificationResult:
    """Breakdown of Rarity Points v0.2 calculation and resulting tier."""

    version: str
    rarity_points: int
    base_rarity: str
    final_rarity: str
    highest_role_score: int
    combat_bonus: int
    specialist_bonus: int
    versatility_bonus: int
    floor_applied: str | None = None


def _tier_from_rp(rp: int) -> str:
    if rp >= 100:
        return "Legendary"
    if rp >= 90:
        return "Epic"
    if rp >= 80:
        return "Rare"
    if rp >= 60:
        return "Uncommon"
    return "Common"


def _max_tier(a: str, b: str) -> str:
    return a if _RARITY_ORDER[a] >= _RARITY_ORDER[b] else b


def classify_rarity_v02(
    *,
    power: int,
    role_fits: Mapping[str, int],
    role_scores: Mapping[str, int] | None = None,
    apply_naruto_healer_floor: bool = False,
) -> RarityClassificationResult:
    """Classify a character's rarity tier using Rarity Points v0.2.

    RP = highest_role_score + combat_bonus + specialist_bonus + versatility_bonus
    """
    normalized_fits = {str(k).lower(): int(v) for k, v in role_fits.items()}
    if role_scores is None:
        rating_input = RatingInput(
            character_id="_rarity_eval",
            power=power,
            fit=normalized_fits,
        )
        computed = score_record(rating_input).scores
    else:
        computed = {role: int(role_scores[role]) for role in SCORING_ROLES}

    ordered_scores = [int(computed[role]) for role in SCORING_ROLES]
    highest_role_score = max(ordered_scores)

    if power == 5:
        combat_bonus = 5
    elif power == 4:
        combat_bonus = 3
    else:
        combat_bonus = 0

    specialist_bonus = (
        3
        if any(normalized_fits.get(role, 0) == 5 for role in ("strategist", "support", "healer"))
        else 0
    )

    # +2 for each additional role scoring >= 80, excluding exactly one highest-scoring role.
    scores_ge_80 = sum(1 for s in ordered_scores if s >= 80)
    versatility_bonus = max(0, scores_ge_80 - 1) * 2 if highest_role_score >= 80 else 0

    rp = highest_role_score + combat_bonus + specialist_bonus + versatility_bonus
    base_rarity = _tier_from_rp(rp)
    final_rarity = base_rarity
    floor_applied: str | None = None

    if apply_naruto_healer_floor:
        healer_fit = normalized_fits.get("healer", 0)
        if healer_fit == 5:
            floored = _max_tier(base_rarity, "Epic")
            if floored != base_rarity:
                floor_applied = "healer_fit_5_min_epic"
            final_rarity = floored
        elif healer_fit == 4:
            floored = _max_tier(base_rarity, "Rare")
            if floored != base_rarity:
                floor_applied = "healer_fit_4_min_rare"
            final_rarity = floored

    return RarityClassificationResult(
        version=RARITY_V02_VERSION,
        rarity_points=rp,
        base_rarity=base_rarity,
        final_rarity=final_rarity,
        highest_role_score=highest_role_score,
        combat_bonus=combat_bonus,
        specialist_bonus=specialist_bonus,
        versatility_bonus=versatility_bonus,
        floor_applied=floor_applied,
    )
