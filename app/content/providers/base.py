"""Base contract for character catalogue providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, Protocol

from app.content.models import CandidateCharacter


class CharacterProvider(ABC):
    """A source of candidate characters for one universe."""

    name: str
    universe: str

    @abstractmethod
    def collect(self) -> list[CandidateCharacter]:
        """Return candidate characters. Network access belongs here."""


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, CharacterProvider] = {}

    def register(self, provider: CharacterProvider) -> None:
        self._providers[provider.name] = provider

    def get(self, name: str) -> CharacterProvider:
        return self._providers[name]

    def all(self) -> Iterable[CharacterProvider]:
        return list(self._providers.values())
