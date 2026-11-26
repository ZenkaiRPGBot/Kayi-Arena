"""Run 10,000 balance simulations using the preliminary Naruto dataset."""

from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from app.engine import (
    MatchStatus,
    SeededDrawSource,
    CatalogEntry,
    start_draft,
    shuffle,
    assign_role,
)

dataset = json.loads(Path("data/naruto_evaluated_60_dataset.json").read_text(encoding="utf-8"))
weights = {"Common": 30.0, "Uncommon": 30.0, "Rare": 22.0, "Epic": 13.0, "Legendary": 5.0}
catalog = tuple(CatalogEntry(character_id=r["character_id"], rarity_id=r["rarity"]) for r in dataset["characters"])

draw_source = SeededDrawSource(seed=42)
rng = random.Random(20261126)

first_player_wins = 0
total_drafts = 0
role_counts = Counter()
rarity_counts = Counter()
healer_picks = 0
actions_list = []
first_pick_counts = Counter()

for i in range(10000):
    snap = start_draft(
        match_id=f"naruto-balance-{i}",
        players=("p1", "p2"),
        universe_id="naruto",
        mode="ranked",
        catalog=catalog,
        rarity_weights=weights,
        dataset_version="naruto-preliminary",
        draw_source=draw_source,
    ).snapshot
    actions = 0
    ok = True
    while snap.status is MatchStatus.ACTIVE:
        actor = snap.active_player_id
        if actor is None:
            ok = False
            break
        snap = shuffle(snap, player_id=actor, expected_revision=snap.revision, draw_source=draw_source).snapshot
        actions += 1
        roles = snap.remaining_roles()[actor]
        chosen_role = rng.choice(roles)
        res = assign_role(snap, player_id=actor, role=chosen_role, expected_revision=snap.revision)
        if not res.accepted:
            ok = False
            break
        snap = res.snapshot
        actions += 1
        if actions > 500:
            ok = False
            break
    if not ok:
        continue
    total_drafts += 1
    actions_list.append(actions)
    # Count roles assigned: teams maps role -> character_id
    for pid in ("p1", "p2"):
        for role, cid in snap.teams[pid].items():
            role_counts[role] += 1
            for r in dataset["characters"]:
                if r["character_id"] == cid:
                    rarity_counts[r["rarity"]] += 1
                    if r["fit"].get("healer", 0) >= 4:
                        healer_picks += 1
                    break
    # first player advantage: compare team power? Use combined scores
    def team_score(pid):
        s = 0
        for role, cid in snap.teams[pid].items():
            for r in dataset["characters"]:
                if r["character_id"] == cid:
                    s += r["scores"].get(role.lower(), 0)
        return s
    if team_score("p1") > team_score("p2"):
        first_player_wins += 1

report = {
    "total_drafts": total_drafts,
    "avg_actions": round(sum(actions_list) / max(1, len(actions_list)), 2),
    "first_player_win_rate": round(first_player_wins / max(1, total_drafts), 4),
    "role_distribution": dict(role_counts),
    "rarity_distribution": dict(rarity_counts),
    "healer_high_fit_picks": healer_picks,
}
Path("data/naruto_balance_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))