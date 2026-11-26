"""Run a balance simulation using the preliminary Naruto dataset."""

from __future__ import annotations

import json
import random
from pathlib import Path

from app.engine import (
    MatchStatus,
    SeededDrawSource,
    CatalogEntry,
    start_draft,
    shuffle,
)

dataset = json.loads(Path("data/naruto_evaluated_60_dataset.json").read_text(encoding="utf-8"))
weights = {
    "Common": 40.0,
    "Uncommon": 25.0,
    "Rare": 18.0,
    "Epic": 12.0,
    "Legendary": 5.0,
}
catalog = tuple(
    CatalogEntry(character_id=r["character_id"], rarity_id=r["rarity"])
    for r in dataset["characters"]
)

draw_source = SeededDrawSource(seed=42)
rng = random.Random(20261126)
from app.engine import assign_role, skip_character

results = {"completed": 0, "actions": 0, "failed": 0}
for i in range(200):
    snap = start_draft(
        match_id=f"naruto-sim-{i}",
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
        assert actor is not None
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
    if ok and snap.status is not MatchStatus.ACTIVE:
        results["completed"] += 1
        results["actions"] += actions
    else:
        results["failed"] += 1

print("drafts:", results["completed"], "failed:", results["failed"], "avg_actions:", round(results["actions"] / max(1, results["completed"]), 2))