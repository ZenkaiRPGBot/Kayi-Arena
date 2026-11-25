"""Local CLI demonstration for Kayi Arena Module 2 (Evaluation & Scoring).

Run with:
    python -m scripts.demo_scoring
"""

from __future__ import annotations

from app.scoring import (
    BatchValidationError,
    SCORE_1_0_VERSION,
    SCORING_ROLES,
    score_record,
)


def main() -> None:
    print(f"Kayi Arena — Module 2 Scoring Demo ({SCORE_1_0_VERSION})")
    print("=" * 64)

    specialist = {
        "character_id": "tactical_scholar",
        "power": 2,
        "fit": {
            "captain": 3,
            "strategist": 5,
            "attacker": 1,
            "tank": 1,
            "assassin": 2,
            "support": 4,
            "healer": 0,
        },
    }
    powerhouse = {
        "character_id": "apex_berserker",
        "power": 5,
        "fit": {
            "captain": 2,
            "strategist": 0,
            "attacker": 5,
            "tank": 4,
            "assassin": 1,
            "support": 0,
            "healer": 0,
        },
    }

    spec_out = score_record(specialist)
    pow_out = score_record(powerhouse)

    for label, out in (("Specialist", spec_out), ("Powerhouse", pow_out)):
        print(f"\n[{label}] {out.character_id} (Power: {out.power}, Version: {out.scoring_version})")
        for role in SCORING_ROLES:
            print(f"  {role:11s} | Fit: {out.fit[role]} -> Score: {out.scores[role]}")

    print("\n" + "-" * 64)
    print("Specialist vs Unsuitable Powerhouse Comparison:")
    print(
        f"  Strategist: {spec_out.character_id} ({spec_out.scores['strategist']}) "
        f"vs {pow_out.character_id} ({pow_out.scores['strategist']})"
    )
    print(
        f"  Support:    {spec_out.character_id} ({spec_out.scores['support']}) "
        f"vs {pow_out.character_id} ({pow_out.scores['support']})"
    )
    print(
        f"  Attacker:   {pow_out.character_id} ({pow_out.scores['attacker']}) "
        f"vs {spec_out.character_id} ({spec_out.scores['attacker']})"
    )

    print("\n" + "-" * 64)
    print("Validation Error Examples:")
    invalid_samples = [
        ("Float power (3.0)", {"character_id": "bad_1", "power": 3.0, "fit": {r: 2 for r in SCORING_ROLES}}),
        ("Bool fit (True)", {"character_id": "bad_2", "power": 3, "fit": {**{r: 2 for r in SCORING_ROLES}, "healer": True}}),
        ("Power out of range (6)", {"character_id": "bad_3", "power": 6, "fit": {r: 2 for r in SCORING_ROLES}}),
    ]
    for desc, payload in invalid_samples:
        try:
            score_record(payload)
        except BatchValidationError as exc:
            codes = ", ".join(issue.code.value for issue in exc.issues)
            print(f"  {desc}: rejected [{codes}] -> {exc}")


if __name__ == "__main__":
    main()
