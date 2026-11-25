"""T6 negative validation tests (V01-V08), config validation, and batch atomicity."""

from __future__ import annotations

import pytest

from app.scoring import (
    BatchValidationError,
    InternalScoreRangeError,
    RoleWeight,
    SCORE_1_0_CONFIG,
    SCORE_1_0_PERCENT_WEIGHTS,
    SCORE_1_0_VERSION,
    SCORING_ROLES,
    ScoringConfig,
    ScoringConfigError,
    ScoringValidationErrorCode,
    score_batch,
    score_record,
    verify_internal_score_range,
)


def _valid_record(cid: str = "valid_1") -> dict:
    return {
        "character_id": cid,
        "power": 3,
        "fit": {role: 2 for role in SCORING_ROLES},
    }


def test_t6_v01_missing_or_unknown_fields() -> None:
    r1 = {"character_id": "a", "power": 3}  # missing fit
    r2 = {**_valid_record("b"), "extra": 123}  # unknown field
    res = score_batch([r1, r2])
    assert not res.accepted
    assert res.results == ()
    assert [e.code for e in res.errors] == [ScoringValidationErrorCode.V01, ScoringValidationErrorCode.V01]


@pytest.mark.parametrize("bad_power", [3.0, True, False, "3", None])
def test_t6_v02_non_integer_power_rejected(bad_power) -> None:
    rec = _valid_record("p_bad")
    rec["power"] = bad_power
    res = score_batch([rec])
    assert not res.accepted
    assert res.results == ()
    assert any(e.code is ScoringValidationErrorCode.V02 for e in res.errors)


@pytest.mark.parametrize("bad_fit", [2.0, True, "2", None])
def test_t6_v02_non_integer_fit_rejected(bad_fit) -> None:
    rec = _valid_record("f_bad")
    rec["fit"]["healer"] = bad_fit
    with pytest.raises(BatchValidationError) as exc_info:
        score_record(rec)
    assert exc_info.value.issues[0].code is ScoringValidationErrorCode.V02


@pytest.mark.parametrize("bad_power", [0, 6, -1])
def test_t6_v03_power_out_of_range(bad_power: int) -> None:
    rec = _valid_record("p_range")
    rec["power"] = bad_power
    res = score_batch([rec])
    assert not res.accepted
    assert res.errors[0].code is ScoringValidationErrorCode.V03


def test_t6_v04_fit_keys_mismatch() -> None:
    rec_missing = _valid_record("m_key")
    del rec_missing["fit"]["healer"]

    rec_extra = _valid_record("e_key")
    rec_extra["fit"]["wizard"] = 3

    res = score_batch([rec_missing, rec_extra])
    assert not res.accepted
    assert [e.code for e in res.errors] == [ScoringValidationErrorCode.V04, ScoringValidationErrorCode.V04]


@pytest.mark.parametrize("bad_fit", [-1, 6, 99])
def test_t6_v05_fit_out_of_range(bad_fit: int) -> None:
    rec = _valid_record("f_range")
    rec["fit"]["tank"] = bad_fit
    res = score_batch([rec])
    assert not res.accepted
    assert res.errors[0].code is ScoringValidationErrorCode.V05


def test_t6_v06_empty_and_duplicate_character_ids_and_batch_atomicity() -> None:
    # Empty / whitespace IDs + duplicate ID alongside a valid record -> all-or-nothing
    r_valid = _valid_record("hero_1")
    r_dup = _valid_record("hero_1")
    r_empty = _valid_record("   ")

    res = score_batch([r_valid, r_dup, r_empty])
    assert not res.accepted
    assert res.results == ()
    assert [e.code for e in res.errors] == [
        ScoringValidationErrorCode.V06,
        ScoringValidationErrorCode.V06,
    ]


def test_t6_v07_invalid_scoring_configurations() -> None:
    # 1. Negative weight
    with pytest.raises(ScoringConfigError) as exc1:
        RoleWeight(-5, 105)
    assert exc1.value.code is ScoringValidationErrorCode.V07

    # 2. Sum != 100
    with pytest.raises(ScoringConfigError) as exc2:
        RoleWeight(50, 40)
    assert exc2.value.code is ScoringValidationErrorCode.V07

    # 3. Not a multiple of 5
    with pytest.raises(ScoringConfigError) as exc3:
        RoleWeight(52, 48)
    assert exc3.value.code is ScoringValidationErrorCode.V07

    # 4. Non-integer / bool weight
    with pytest.raises(ScoringConfigError):
        RoleWeight(50.0, 50)  # type: ignore[arg-type]
    with pytest.raises(ScoringConfigError):
        RoleWeight(True, 99)  # type: ignore[arg-type]

    # 5. Unknown / missing roles in ScoringConfig
    weights = {role: RoleWeight(50, 50) for role in SCORING_ROLES}
    weights_bad = dict(weights)
    del weights_bad["healer"]
    weights_bad["mage"] = RoleWeight(50, 50)
    with pytest.raises(ScoringConfigError):
        ScoringConfig(version="SCORE-CUSTOM-1", weights=weights_bad)

    # 6. Invalid version string
    with pytest.raises(ScoringConfigError):
        ScoringConfig(version="  ", weights=weights)

    # 7. SCORE-1.0 cannot be paired with altered scoring constants
    altered = {
        role: RoleWeight(fp, pp)
        for role, (fp, pp) in SCORE_1_0_PERCENT_WEIGHTS.items()
    }
    altered["attacker"] = RoleWeight(55, 45)
    with pytest.raises(ScoringConfigError) as exc_alt:
        ScoringConfig(version=SCORE_1_0_VERSION, weights=altered)
    assert exc_alt.value.code is ScoringValidationErrorCode.V07


def test_v08_internal_score_range_guard_tested_separately() -> None:
    """V08 is an unreachable internal guard for valid inputs; tested directly."""
    w = SCORE_1_0_CONFIG.weights["captain"]
    assert verify_internal_score_range(8, role="captain", weight=w) == 8
    assert verify_internal_score_range(100, role="captain", weight=w) == 100
    with pytest.raises(InternalScoreRangeError) as exc_low:
        verify_internal_score_range(7, role="captain", weight=w)
    assert exc_low.value.code is ScoringValidationErrorCode.V08
    with pytest.raises(InternalScoreRangeError) as exc_high:
        verify_internal_score_range(101, role="captain", weight=w)
    assert exc_high.value.code is ScoringValidationErrorCode.V08


def test_t6_no_false_rejections_for_valid_boundary_records() -> None:
    res = score_batch(
        [
            {"character_id": "min_boundary", "power": 1, "fit": {r: 0 for r in SCORING_ROLES}},
            {"character_id": "max_boundary", "power": 5, "fit": {r: 5 for r in SCORING_ROLES}},
        ]
    )
    assert res.accepted is True
    assert res.errors == ()
    assert len(res.results) == 2
