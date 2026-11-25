"""Advisory-only scoring diagnostics (R5 revised: computed for any sample size)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Sequence

from app.scoring.models import CharacterScoreOutput, SCORING_ROLES

PRELIMINARY_SAMPLE_THRESHOLD = 50


@dataclass(frozen=True, slots=True)
class DiagnosticsReport:
    """Advisory diagnostics for a scored dataset (never mutates ratings or blocks)."""

    sample_size: int
    is_preliminary: bool
    sample_status: str
    pearson_power_fit: Mapping[str, float | None]
    high_fit_roles_per_character: Mapping[str, int]
    mean_high_fit_roles: float
    tie_pair_counts: Mapping[str, int]
    total_tie_pairs: int
    advisory_flags: tuple[str, ...]
    advisory_only: bool = True


def _pearson(xs: Sequence[int], ys: Sequence[int]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    dx = [x - mean_x for x in xs]
    dy = [y - mean_y for y in ys]
    sum_xx = sum(a * a for a in dx)
    sum_yy = sum(b * b for b in dy)
    if sum_xx == 0.0 or sum_yy == 0.0:
        return None
    return sum(a * b for a, b in zip(dx, dy)) / math.sqrt(sum_xx * sum_yy)


def compute_diagnostics(
    records: Sequence[CharacterScoreOutput],
    *,
    universe_count: int | None = None,
) -> DiagnosticsReport:
    """Compute advisory diagnostics even for small/single-universe samples (R5 revised).

    - Below 50 approved characters: labeled ``is_preliminary=True`` (``"preliminary"``).
    - Single-universe sets are analyzed directly without requiring multiple universes.
    - Undefined correlations (empty or constant values) yield ``None`` safely.
    """
    n = len(records)
    is_preliminary = n < PRELIMINARY_SAMPLE_THRESHOLD
    sample_status = "preliminary" if is_preliminary else "sufficient"

    powers = [r.power for r in records]
    pearson_map: dict[str, float | None] = {}
    tie_counts: dict[str, int] = {}
    flags: list[str] = []

    if is_preliminary:
        flags.append("preliminary_sample_below_50")
    if universe_count is not None and universe_count == 1:
        flags.append("single_universe_sample")

    for role in SCORING_ROLES:
        fits = [r.fit[role] for r in records]
        corr = _pearson(powers, fits)
        pearson_map[role] = corr
        if corr is not None and corr > 0.9:
            flags.append(f"high_power_fit_correlation:{role}")

        scores = [r.scores[role] for r in records]
        ties = 0
        for i in range(n):
            si = scores[i]
            for j in range(i + 1, n):
                if si == scores[j]:
                    ties += 1
        tie_counts[role] = ties

    high_fit_counts = {
        r.character_id: sum(1 for role in SCORING_ROLES if r.fit[role] >= 4)
        for r in records
    }
    mean_high_fit = (sum(high_fit_counts.values()) / n) if n > 0 else 0.0
    if n > 0 and mean_high_fit > 2.0:
        flags.append("high_versatility_mean_above_2")

    return DiagnosticsReport(
        sample_size=n,
        is_preliminary=is_preliminary,
        sample_status=sample_status,
        pearson_power_fit=MappingProxyType(pearson_map),
        high_fit_roles_per_character=MappingProxyType(high_fit_counts),
        mean_high_fit_roles=mean_high_fit,
        tie_pair_counts=MappingProxyType(tie_counts),
        total_tie_pairs=sum(tie_counts.values()),
        advisory_flags=tuple(flags),
        advisory_only=True,
    )
