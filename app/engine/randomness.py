"""Injectable draw sources and exact character probability computation."""

from __future__ import annotations

import random
import secrets
from typing import Mapping, Protocol, Sequence

from app.engine.models import CatalogEntry


class DrawSource(Protocol):
    """Randomness boundary for starting-player selection and character draws."""

    def choose_starting_player(self, players: tuple[str, str]) -> str:
        """Select one player from ``players`` (exactly 1 call per draft start)."""

    def draw_character(
        self,
        eligible: tuple[CatalogEntry, ...],
        rarity_weights: Mapping[str, float],
    ) -> CatalogEntry:
        """Select one character from ``eligible`` using rarity-first weighting."""


def compute_character_probabilities(
    eligible: Sequence[CatalogEntry],
    rarity_weights: Mapping[str, float],
) -> dict[str, float]:
    """Return exact draw probability for each character in ``eligible`` (Section 6.4).

    Implements rarity-first weighted selection with renormalization when rarities
    become empty, followed by uniform selection within the chosen rarity.
    """
    if not eligible:
        return {}

    by_rarity: dict[str, list[CatalogEntry]] = {}
    for entry in eligible:
        by_rarity.setdefault(entry.rarity_id, []).append(entry)

    active_weights = {
        rarity_id: float(rarity_weights[rarity_id])
        for rarity_id, items in by_rarity.items()
        if items and float(rarity_weights.get(rarity_id, 0.0)) > 0.0
    }
    total_weight = sum(active_weights.values())
    if total_weight <= 0.0:
        raise ValueError("No eligible characters belong to a positively weighted rarity")

    probs: dict[str, float] = {}
    for rarity_id, weight in active_weights.items():
        items = by_rarity[rarity_id]
        tier_prob = weight / total_weight
        per_char = tier_prob / len(items)
        for item in items:
            probs[item.character_id] = per_char
    return probs


def _weighted_rarity_draw(
    rng: random.Random,
    eligible: tuple[CatalogEntry, ...],
    rarity_weights: Mapping[str, float],
) -> CatalogEntry:
    if not eligible:
        raise ValueError("Eligible character set must not be empty")

    by_rarity: dict[str, list[CatalogEntry]] = {}
    for entry in eligible:
        bucket = by_rarity.get(entry.rarity_id)
        if bucket is None:
            by_rarity[entry.rarity_id] = [entry]
        else:
            bucket.append(entry)

    active_rarities: list[str] = []
    weights: list[float] = []
    total_weight = 0.0
    for rarity_id in by_rarity:
        w = float(rarity_weights.get(rarity_id, 0.0))
        if w > 0.0:
            active_rarities.append(rarity_id)
            weights.append(w)
            total_weight += w
    if not active_rarities:
        raise ValueError("No eligible characters belong to a positively weighted rarity")

    if len(active_rarities) == 1:
        chosen_rarity = active_rarities[0]
    else:
        pick = rng.random() * total_weight
        acc = 0.0
        chosen_rarity = active_rarities[-1]
        for rarity_id, w in zip(active_rarities, weights):
            acc += w
            if pick < acc:
                chosen_rarity = rarity_id
                break
    return rng.choice(by_rarity[chosen_rarity])


class SystemDrawSource:
    """Production draw source backed by OS CSPRNG (``secrets.SystemRandom``)."""

    def __init__(self) -> None:
        self._rng = secrets.SystemRandom()

    def choose_starting_player(self, players: tuple[str, str]) -> str:
        return self._rng.choice(players)

    def draw_character(
        self,
        eligible: tuple[CatalogEntry, ...],
        rarity_weights: Mapping[str, float],
    ) -> CatalogEntry:
        return _weighted_rarity_draw(self._rng, eligible, rarity_weights)


class SeededDrawSource:
    """Deterministic seeded draw source for reproducible tests and simulations."""

    def __init__(self, seed: int) -> None:
        self._rng = random.Random(seed)
        self.starter_calls = 0
        self.draw_calls = 0

    def choose_starting_player(self, players: tuple[str, str]) -> str:
        self.starter_calls += 1
        return self._rng.choice(players)

    def draw_character(
        self,
        eligible: tuple[CatalogEntry, ...],
        rarity_weights: Mapping[str, float],
    ) -> CatalogEntry:
        self.draw_calls += 1
        return _weighted_rarity_draw(self._rng, eligible, rarity_weights)


class ScriptedDrawSource:
    """Scripted draw source for exact deterministic test scenarios & call counting."""

    def __init__(
        self,
        *,
        starting_player: str,
        draws: Sequence[str],
    ) -> None:
        self.starting_player = starting_player
        self._draws = list(draws)
        self._index = 0
        self.starter_calls = 0
        self.draw_calls = 0

    @property
    def position(self) -> int:
        return self._index

    def clone_at(self, position: int) -> ScriptedDrawSource:
        clone = ScriptedDrawSource(starting_player=self.starting_player, draws=self._draws)
        clone._index = position
        return clone

    def choose_starting_player(self, players: tuple[str, str]) -> str:
        self.starter_calls += 1
        if self.starting_player not in players:
            raise ValueError(f"Scripted starter {self.starting_player!r} not in {players!r}")
        return self.starting_player

    def draw_character(
        self,
        eligible: tuple[CatalogEntry, ...],
        rarity_weights: Mapping[str, float],
    ) -> CatalogEntry:
        self.draw_calls += 1
        if self._index >= len(self._draws):
            raise IndexError("ScriptedDrawSource ran out of scripted draws")
        target_id = self._draws[self._index]
        self._index += 1
        for entry in eligible:
            if entry.character_id == target_id:
                return entry
        raise ValueError(
            f"Scripted character {target_id!r} is not in eligible set "
            f"({[e.character_id for e in eligible]})"
        )
