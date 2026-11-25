"""Temporary local CLI demonstration for Kayi Arena Module 1 (Core Drafting Engine).

Run with:
    python -m scripts.demo_draft
    python -m scripts.demo_draft --seed 42
"""

from __future__ import annotations

import argparse

from app.engine import (
    CatalogEntry,
    DraftPhase,
    MatchStatus,
    ROLES,
    SeededDrawSource,
    SystemDrawSource,
    assign_role,
    shuffle,
    skip_character,
    start_draft,
)

FICTIONAL_POOL: tuple[CatalogEntry, ...] = (
    CatalogEntry("kuro_blade", "Mythic"),
    CatalogEntry("azure_sage", "Mythic"),
    CatalogEntry("crimson_nova", "Mythic"),
    CatalogEntry("iron_titan", "Legendary"),
    CatalogEntry("shadow_fox", "Legendary"),
    CatalogEntry("lunar_warden", "Legendary"),
    CatalogEntry("storm_archer", "Epic"),
    CatalogEntry("frost_weaver", "Epic"),
    CatalogEntry("flame_monk", "Epic"),
    CatalogEntry("mist_dancer", "Epic"),
    CatalogEntry("stone_sentinel", "Rare"),
    CatalogEntry("wind_courier", "Rare"),
    CatalogEntry("dawn_cleric", "Rare"),
    CatalogEntry("ember_scout", "Rare"),
    CatalogEntry("moss_alchemist", "Common"),
    CatalogEntry("iron_recruit", "Common"),
    CatalogEntry("spark_apprentice", "Common"),
    CatalogEntry("river_herbalist", "Common"),
)

RARITY_WEIGHTS: dict[str, float] = {
    "Mythic": 5.0,
    "Legendary": 15.0,
    "Epic": 25.0,
    "Rare": 30.0,
    "Common": 25.0,
}


def _print_state(view) -> None:
    print("\n" + "=" * 64)
    print(
        f"Match: {view.match_id} | Status: {view.status.value} | "
        f"Progress: {view.progress}/14 | Rev: {view.revision}"
    )
    if view.status is MatchStatus.ACTIVE:
        print(f"Turn {view.turn_number}/14 -> Active Player: {view.active_player_id}")
    print("-" * 64)
    for pid in view.players:
        team_str = ", ".join(
            f"{role}: {view.teams[pid].get(role, '---')}" for role in ROLES
        )
        print(f"{pid} (Skips left: {view.skips_remaining[pid]}): {team_str}")
        print(f"   Remaining roles: {', '.join(view.remaining_roles[pid]) or 'None'}")
    if view.held_character is not None:
        print("-" * 64)
        print(
            f"Held Character: {view.held_character.character_id} "
            f"[{view.held_character.rarity_id}] | Can Skip: {view.can_skip}"
        )
    print("=" * 64)


def run_cli(seed: int | None = None) -> None:
    draw_source = SeededDrawSource(seed) if seed is not None else SystemDrawSource()
    result = start_draft(
        match_id="local-demo-001",
        players=("Player_A", "Player_B"),
        universe_id="fictional_verse",
        mode="friendly",
        catalog=FICTIONAL_POOL,
        rarity_weights=RARITY_WEIGHTS,
        dataset_version="demo-v1",
        draw_source=draw_source,
    )
    snap = result.snapshot
    print(f"Draft started! Starting player: {snap.starting_player_id}")

    while snap.status is MatchStatus.ACTIVE:
        view = result.public_view
        _print_state(view)
        actor = view.active_player_id
        assert actor is not None

        if view.phase is DraftPhase.AWAITING_SHUFFLE:
            cmd = input(f"[{actor}] Press Enter to Shuffle (or 'q' to quit): ").strip().lower()
            if cmd == "q":
                print("Exited demo.")
                return
            result = shuffle(
                snap,
                player_id=actor,
                expected_revision=snap.revision,
                draw_source=draw_source,
            )
            if not result.accepted:
                print(f"Rejected: {result.error_code}")
                continue
            snap = result.snapshot
            print(
                f"-> Revealed: {snap.held_character.character_id} "
                f"({snap.held_character.rarity_id})"
            )
        else:
            rem = view.remaining_roles[actor]
            options = ", ".join(f"{idx + 1}:{role}" for idx, role in enumerate(rem))
            skip_hint = " or 's' to Skip" if view.can_skip else " (Skip unavailable)"
            raw = input(f"[{actor}] Choose role [{options}]{skip_hint}: ").strip()
            if raw.lower() == "q":
                print("Exited demo.")
                return
            if raw.lower() == "s":
                result = skip_character(
                    snap,
                    player_id=actor,
                    expected_revision=snap.revision,
                )
            else:
                role = rem[int(raw) - 1] if raw.isdigit() and 1 <= int(raw) <= len(rem) else raw
                result = assign_role(
                    snap,
                    player_id=actor,
                    role=role,
                    expected_revision=snap.revision,
                )
            if not result.accepted:
                print(f"Rejected: {result.error_code}")
                continue
            snap = result.snapshot

    _print_state(result.public_view)
    print("\nDraft COMPLETED! Handoff to Match Resolution:")
    print(f"  Starter: {result.completed_output.starting_player_id}")
    print(f"  Dataset version: {result.completed_output.dataset_version}")
    for pid, team in result.completed_output.teams.items():
        print(f"  {pid}: {team}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Kayi Arena Module 1 local CLI demo")
    parser.add_argument("--seed", type=int, default=None, help="Optional RNG seed")
    args = parser.parse_args()
    run_cli(seed=args.seed)


if __name__ == "__main__":
    main()
