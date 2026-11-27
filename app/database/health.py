"""Mandatory advisory dataset health reports (reusing Module 2 diagnostics)."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from app.database.models import CharacterEntry, RARITY_TIERS
from app.scoring import (
    CharacterScoreOutput,
    DiagnosticsReport,
    SCORING_ROLES,
    compute_diagnostics,
)


@dataclass(frozen=True, slots=True)
class DatasetHealthReport:
    """Advisory publication health report (never blocks or alters ratings)."""

    dataset_version: str
    universe_id: str
    total_characters: int
    rarity_distribution: Mapping[str, int]
    power_distribution: Mapping[int, int]
    fit_distributions: Mapping[str, Mapping[int, int]]
    specialist_count: int
    healer_capable_count: int
    healer_any_count: int
    role_score_concentration: Mapping[str, Mapping[str, float]]
    estimated_tie_frequencies: Mapping[str, float]
    diagnostics: DiagnosticsReport
    advisory_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_version": self.dataset_version,
            "universe_id": self.universe_id,
            "total_characters": self.total_characters,
            "rarity_distribution": {r: self.rarity_distribution[r] for r in RARITY_TIERS},
            "power_distribution": {str(k): v for k, v in self.power_distribution.items()},
            "fit_distributions": {
                role: {str(k): v for k, v in self.fit_distributions[role].items()}
                for role in SCORING_ROLES
            },
            "specialist_count": self.specialist_count,
            "healer_capable_count": self.healer_capable_count,
            "healer_any_count": self.healer_any_count,
            "role_score_concentration": {
                role: dict(self.role_score_concentration[role]) for role in SCORING_ROLES
            },
            "estimated_tie_frequencies": {
                role: self.estimated_tie_frequencies[role] for role in SCORING_ROLES
            },
            "diagnostics": {
                "sample_size": self.diagnostics.sample_size,
                "is_preliminary": self.diagnostics.is_preliminary,
                "sample_status": self.diagnostics.sample_status,
                "pearson_power_fit": dict(self.diagnostics.pearson_power_fit),
                "mean_high_fit_roles": self.diagnostics.mean_high_fit_roles,
                "tie_pair_counts": dict(self.diagnostics.tie_pair_counts),
                "total_tie_pairs": self.diagnostics.total_tie_pairs,
                "advisory_flags": list(self.diagnostics.advisory_flags),
                "advisory_only": self.diagnostics.advisory_only,
            },
            "advisory_only": self.advisory_only,
        }


def build_dataset_health_report(
    *,
    dataset_version: str,
    universe_id: str,
    entries: Sequence[CharacterEntry],
    scored_outputs: Sequence[CharacterScoreOutput],
) -> DatasetHealthReport:
    """Compute mandatory advisory health report from scored character entries."""
    n = len(entries)
    rarity_dist = {tier: 0 for tier in RARITY_TIERS}
    power_dist = {lvl: 0 for lvl in range(1, 6)}
    fit_dist = {role: {lvl: 0 for lvl in range(6)} for role in SCORING_ROLES}

    specialist_count = 0
    healer_capable_count = 0
    healer_any_count = 0

    for entry, out in zip(entries, scored_outputs):
        rarity_dist[entry.rarity] = rarity_dist.get(entry.rarity, 0) + 1
        power_dist[out.power] = power_dist.get(out.power, 0) + 1
        high_roles = 0
        for role in SCORING_ROLES:
            f_val = out.fit[role]
            fit_dist[role][f_val] += 1
            if f_val >= 4:
                high_roles += 1
        # Specialist: excels in 1-2 roles (Fit >= 4) rather than broad generalists
        if 1 <= high_roles <= 2:
            specialist_count += 1
        if out.fit["healer"] >= 3:
            healer_capable_count += 1
        if out.fit["healer"] >= 1:
            healer_any_count += 1

    diagnostics = compute_diagnostics(scored_outputs, universe_count=1)

    concentration: dict[str, Mapping[str, float]] = {}
    tie_freqs: dict[str, float] = {}
    total_pairs = (n * (n - 1)) // 2

    for role in SCORING_ROLES:
        role_scores = [out.scores[role] for out in scored_outputs]
        if role_scores:
            top_score = max(role_scores)
            top_count = sum(1 for s in role_scores if s == top_score)
            concentration[role] = MappingProxyType(
                {
                    "min": float(min(role_scores)),
                    "max": float(top_score),
                    "mean": sum(role_scores) / len(role_scores),
                    "top_score_share": top_count / len(role_scores),
                }
            )
        else:
            concentration[role] = MappingProxyType(
                {"min": 0.0, "max": 0.0, "mean": 0.0, "top_score_share": 0.0}
            )
        tie_pairs = diagnostics.tie_pair_counts[role]
        tie_freqs[role] = (tie_pairs / total_pairs) if total_pairs > 0 else 0.0

    return DatasetHealthReport(
        dataset_version=dataset_version,
        universe_id=universe_id,
        total_characters=n,
        rarity_distribution=MappingProxyType(rarity_dist),
        power_distribution=MappingProxyType(power_dist),
        fit_distributions=MappingProxyType(
            {role: MappingProxyType(fit_dist[role]) for role in SCORING_ROLES}
        ),
        specialist_count=specialist_count,
        healer_capable_count=healer_capable_count,
        healer_any_count=healer_any_count,
        role_score_concentration=MappingProxyType(concentration),
        estimated_tie_frequencies=MappingProxyType(tie_freqs),
        diagnostics=diagnostics,
        advisory_only=True,
    )
