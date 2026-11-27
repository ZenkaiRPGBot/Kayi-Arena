"""Run 10,000+ full Naruto balance simulations using the 53 non-held preliminary ratings."""

from __future__ import annotations

import json
import random
from collections import Counter
from pathlib import Path

from app.database import CharacterDatabase, DEFAULT_RARITY_WEIGHTS, load_naruto_60_into_db
from app.engine import MatchStatus, SeededDrawSource, assign_role, shuffle, start_draft
from app.resolution import MatchOutcome, MatchupWinner, resolve_completed_draft
from app.scoring import DatasetKind


def run_simulation(num_matches: int = 10_000, *, seed: int = 20261126) -> dict[str, object]:
    db = CharacterDatabase(":memory:")
    load_naruto_60_into_db(db, publish_testing_dataset=True)
    dver = db.get_latest_published_version("naruto", kind=DatasetKind.TEST)
    assert dver is not None
    catalog, _, _ = db.export_draft_catalog(dver)
    manifest = db.load_manifest(dver)
    rec_by_id = {r.character_id: r for r in manifest.records}

    class _CachedReader:
        def load_manifest(self, _ver: str) -> object:
            return manifest

        def get_character(self, _ver: str, cid: str) -> object:
            return rec_by_id[cid]

    cached_reader = _CachedReader()
    fit_by_id = {r.character_id: r.fit for r in manifest.records}
    rarity_by_id = {c.character_id: c.rarity_id for c in catalog}

    draw_source = SeededDrawSource(seed=seed)
    rng = random.Random(seed)

    starter_wins = 0
    non_starter_wins = 0
    match_draws = 0
    decided_by_counts: Counter[str] = Counter()
    rarity_draws: Counter[str] = Counter()
    role_scores_sum: Counter[str] = Counter()
    role_counts: Counter[str] = Counter()
    matchup_draws = 0
    total_matchups = 0
    healer_fit_ge_3 = 0
    healer_fit_ge_4 = 0
    total_teams = 0

    for i in range(num_matches):
        snap = start_draft(
            match_id=f"naruto-bal-{i}",
            players=("p1", "p2"),
            universe_id="naruto",
            mode="ranked",
            catalog=catalog,
            rarity_weights=DEFAULT_RARITY_WEIGHTS,
            dataset_version=dver,
            draw_source=draw_source,
        ).snapshot

        while snap.status is MatchStatus.ACTIVE:
            actor = snap.active_player_id
            assert actor is not None
            snap = shuffle(
                snap, player_id=actor, expected_revision=snap.revision, draw_source=draw_source
            ).snapshot
            assert snap.held_character is not None
            rarity_draws[snap.held_character.rarity_id] += 1
            roles = snap.remaining_roles()[actor]
            chosen_role = rng.choice(roles)
            snap = assign_role(
                snap, player_id=actor, role=chosen_role, expected_revision=snap.revision
            ).snapshot

        res = resolve_completed_draft(snap, cached_reader)  # type: ignore[arg-type]
        decided_by_counts[res.decided_by.value] += 1

        if res.outcome is MatchOutcome.DRAW:
            match_draws += 1
        else:
            winner_slot = "player_1" if res.outcome is MatchOutcome.PLAYER_1_WIN else "player_2"
            if winner_slot == res.starting_player:
                starter_wins += 1
            else:
                non_starter_wins += 1

        for m in res.matchups:
            total_matchups += 1
            if m.winner is MatchupWinner.DRAW:
                matchup_draws += 1
            role_scores_sum[m.role] += m.player_1.score + m.player_2.score
            role_counts[m.role] += 2

        for slot_team in snap.teams.values():
            total_teams += 1
            h_cid = slot_team["Healer"]
            h_fit = fit_by_id[h_cid]["healer"]
            if h_fit >= 3:
                healer_fit_ge_3 += 1
            if h_fit >= 4:
                healer_fit_ge_4 += 1

    total_draws = sum(rarity_draws.values())
    report = {
        "matches_simulated": num_matches,
        "pool_size": len(catalog),
        "rarity_distribution_pct": {
            r: round(100.0 * rarity_draws[r] / total_draws, 2)
            for r in ("Common", "Uncommon", "Rare", "Epic", "Legendary")
        },
        "role_avg_score": {
            r: round(role_scores_sum[r] / role_counts[r], 2)
            for r in sorted(role_scores_sum)
        },
        "healer_availability": {
            "teams_with_healer_fit_ge_3_pct": round(100.0 * healer_fit_ge_3 / total_teams, 2),
            "teams_with_healer_fit_ge_4_pct": round(100.0 * healer_fit_ge_4 / total_teams, 2),
        },
        "first_player_advantage": {
            "starter_win_pct": round(100.0 * starter_wins / num_matches, 2),
            "second_player_win_pct": round(100.0 * non_starter_wins / num_matches, 2),
            "match_draw_pct": round(100.0 * match_draws / num_matches, 2),
        },
        "matchup_draw_rate_pct": round(100.0 * matchup_draws / total_matchups, 2),
        "decided_by_pct": {
            k: round(100.0 * v / num_matches, 2) for k, v in decided_by_counts.items()
        },
    }
    db.close()
    return report


if __name__ == "__main__":
    rep = run_simulation(10_000)
    print(json.dumps(rep, indent=2))
