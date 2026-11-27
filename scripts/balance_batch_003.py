"""Run balance simulations using the batch 003 Naruto dataset."""

from __future__ import annotations

import json
import random
from collections import Counter
from pathlib import Path

from app.engine import (
    MatchStatus,
    SeededDrawSource,
    CatalogEntry,
    start_draft,
    shuffle,
    assign_role,
)

dataset = json.loads(Path("data/naruto_batch_003_evaluated_dataset.json").read_text(encoding="utf-8"))
weights = {"Common": 30.0, "Uncommon": 30.0, "Rare": 22.0, "Epic": 13.0, "Legendary": 5.0}
catalog = tuple(CatalogEntry(character_id=r["character_id"], rarity_id=r["rarity"]) for r in dataset["characters"])

draw_source = SeededDrawSource(seed=42)
rng = random.Random(20261127)

total_drafts = 0
failed = 0
actions_list = []
first_player_wins = 0
role_counts = Counter()
rarity_counts = Counter()
healer_picks = 0

for i in range(5000):
    snap = start_draft(
        match_id=f"batch003-sim-{i}",
        players=("p1", "p2"),
        universe_id="naruto",
        mode="ranked",
        catalog=catalog,
        rarity_weights=weights,
        dataset_version="naruto-batch-003",
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
        chosen = rng.choice(roles)
        res = assign_role(snap, player_id=actor, role=chosen, expected_revision=snap.revision)
        if not res.accepted:
            ok = False
            break
        snap = res.snapshot
        actions += 1
        if actions > 500:
            ok = False
            break
    if not ok or snap.status is MatchStatus.ACTIVE:
        failed += 1
        continue
    total_drafts += 1
    actions_list.append(actions)
    for pid in ("p1", "p2"):
        for role, cid in snap.teams[pid].items():
            role_counts[role] += 1
            for r in dataset["characters"]:
                if r["character_id"] == cid:
                    rarity_counts[r["rarity"]] += 1
                    if r["fit"].get("healer", 0) >= 4:
                        healer_picks += 1
                    break
    def ts(pid):
        s = 0
        for role, cid in snap.teams[pid].items():
            for r in dataset["characters"]:
                if r["character_id"] == cid:
                    s += r["scores"].get(role.lower(), 0)
        return s
    if ts("p1") > ts("p2"):
        first_player_wins += 1

report = {
    "total_drafts": total_drafts,
    "failed": failed,
    "avg_actions": round(sum(actions_list) / max(1, len(actions_list)), 2),
    "first_player_win_rate": round(first_player_wins / max(1, total_drafts), 4),
    "role_distribution": dict(role_counts),
    "rarity_distribution": dict(rarity_counts),
    "healer_high_fit_picks": healer_picks,
}
Path("data/naruto_batch_003_balance_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))