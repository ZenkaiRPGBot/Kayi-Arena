"""Integration ports for deferred Module 8 (Profile, History, Leaderboard)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class PlayerProfileView:
    """Authoritative profile summary returned by Module 8 when available."""

    player_id: str
    display_name: str
    rank_name: str
    rating: int
    matches_played: int
    wins: int
    losses: int
    draws: int
    win_rate_pct: float
    current_streak: str
    recent_form: str
    friendly_matches: int = 0
    friendly_wins: int = 0


@dataclass(frozen=True, slots=True)
class LeaderboardEntryView:
    """Authoritative leaderboard row returned by Module 8 when available."""

    position: int
    player_id: str
    display_name: str
    rating: int
    rank_name: str = ""


@dataclass(frozen=True, slots=True)
class MatchHistoryEntryView:
    """Authoritative match history item returned by Module 8/7 when available."""

    match_id: str
    universe_name: str
    game_mode: str
    opponent_name: str
    outcome_label: str


class ProfileStatsProvider(Protocol):
    """Port for Module 8 competitive stats, leaderboards, and match history."""

    def is_available(self) -> bool:
        ...

    async def get_profile(self, player_id: str) -> PlayerProfileView | None:
        ...

    async def get_leaderboard(
        self,
        *,
        scope: str,
        chat_id: str | None,
        page: int,
        per_page: int,
        requester_id: str,
    ) -> tuple[list[LeaderboardEntryView], int | None, int]:
        """Returns (entries, requester_position, total_pages)."""
        ...

    async def get_history(
        self, player_id: str, *, page: int = 0, per_page: int = 10
    ) -> tuple[list[MatchHistoryEntryView], int]:
        ...


class UnavailableStatsProvider:
    """Default Module 6 stub returning unavailable states until Module 8 exists."""

    def is_available(self) -> bool:
        return False

    async def get_profile(self, player_id: str) -> PlayerProfileView | None:
        return None

    async def get_leaderboard(
        self,
        *,
        scope: str,
        chat_id: str | None,
        page: int,
        per_page: int,
        requester_id: str,
    ) -> tuple[list[LeaderboardEntryView], int | None, int]:
        return [], None, 1

    async def get_history(
        self, player_id: str, *, page: int = 0, per_page: int = 10
    ) -> tuple[list[MatchHistoryEntryView], int]:
        return [], 1
