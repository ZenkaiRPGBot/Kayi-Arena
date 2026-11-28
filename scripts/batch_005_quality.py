"""Quality gates for the Naruto Batch 005 staged workflow.

The module deliberately keeps five completion concepts separate:

* catalogue completeness — identities were selected and mapped;
* artwork completeness — mapped identities have validated images;
* research completeness — records carry substantive capability evidence;
* evaluation completeness — an actual Claude evaluation exists and is not a
  placeholder floor evaluation;
* publication readiness — explicit approval has been recorded.

A record whose fields are merely populated with catalogue metadata, placeholders
or boilerplate does not count as substantive research.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PLACEHOLDERS = {
    "",
    "-",
    "n/a",
    "na",
    "none",
    "none recorded",
    "null",
    "pending",
    "unknown",
    "not recorded",
    "not documented",
    "no evidence",
}

GENERIC_MARKERS = (
    "unknown:",
    "no demonstrated",
    "no offensive",
    "no defensive",
    "not shown",
    "no named",
    "no individual jutsu",
    "no speed or reaction feats",
    "no stealth or infiltration feats",
    "no support or battlefield-control feats",
    "no medical classification recorded",
    "no conditional abilities or transformations are recorded",
    "limitations are not documented",
    "not independently verified",
    "must be verified",
    "claude should",
    "claude must",
    "rank:",
    "affiliation:",
    "clan:",
    "debut:",
    "titles:",
    "occupation:",
    "team:",
    "source:",
    "verification level:",
    "metadata only",
)

VALID_STATUSES = {"RESEARCH_READY", "PARTIAL_RESEARCH", "INSUFFICIENT_EVIDENCE"}


def _flatten(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        result: list[str] = []
        for item in value:
            result.extend(_flatten(item))
        return result
    if isinstance(value, dict):
        result: list[str] = []
        for item in value.values():
            result.extend(_flatten(item))
        return result
    return [str(value)]


def is_placeholder(value: Any) -> bool:
    """Return True for empty, boilerplate or catalogue-only values."""
    texts = [text.strip().lower() for text in _flatten(value)]
    if not texts:
        return True
    if any(text in PLACEHOLDERS for text in texts):
        return True
    return all(any(marker in text for marker in GENERIC_MARKERS) for text in texts)


def is_substantive_text(value: Any) -> bool:
    """Return True when a field contains more than a placeholder or metadata."""
    return bool(_flatten(value)) and not is_placeholder(value)


def is_substantive_ability(ability: Any) -> bool:
    """Return True for a concrete, evidenced ability or demonstration."""
    if not isinstance(ability, dict):
        return False
    name = ability.get("name") or ability.get("ability")
    description = ability.get("description") or ability.get("evidence")
    if is_placeholder(name) or is_placeholder(description):
        return False
    # A named technique plus a concrete demonstration is required. Generic
    # labels such as "abilities" or "skilled ninja" are not enough.
    if str(name).strip().lower() in {"ability", "abilities", "skill", "skills", "jutsu"}:
        return False
    return True


def research_ready_valid(record: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate that a RESEARCH_READY record meets the substantive gate."""
    errors: list[str] = []
    if record.get("status") != "RESEARCH_READY":
        return False, ["status is not RESEARCH_READY"]

    abilities = record.get("demonstrated_abilities") or []
    substantive = [item for item in abilities if is_substantive_ability(item)]
    if not substantive:
        errors.append("no substantive demonstrated ability")

    evidence = record.get("supporting_evidence") or []
    usable_evidence = [
        item
        for item in evidence
        if isinstance(item, dict)
        and str(item.get("url") or "").startswith("http")
        and str(item.get("verification_level") or "").strip()
    ]
    if not usable_evidence:
        errors.append("no traceable supporting evidence")

    summary = record.get("capability_summary") or {}
    substantive_fields = [
        key for key, value in summary.items() if is_substantive_text(value)
    ]
    if len(substantive_fields) < 2:
        errors.append("fewer than two substantive capability-summary fields")

    for key in ("power", "fit", "rarity", "role_score", "approved", "approval"):
        if key in record:
            errors.append(f"rating field present: {key}")

    return not errors, errors


def assess_catalogue(catalogue: dict[str, Any]) -> dict[str, Any]:
    candidates = catalogue.get("candidates") or []
    ids = [str(item.get("candidate_id") or "") for item in candidates]
    duplicates = sorted({item for item in ids if ids.count(item) > 1})
    target = (catalogue.get("stats") or {}).get("targets")
    expected = target if isinstance(target, int) else len(ids)
    return {
        "expected_candidates": expected,
        "actual_candidates": len(ids),
        "unique_candidate_ids": len(set(ids)),
        "duplicate_ids": duplicates,
        "complete": bool(ids) and len(ids) == expected and not duplicates,
    }


def assess_artwork(
    catalogue: dict[str, Any], manifest: dict[str, Any]
) -> dict[str, Any]:
    catalogue_ids = {
        str(item.get("candidate_id") or "")
        for item in catalogue.get("candidates") or []
    }
    summary = manifest.get("summary") or {}
    covered = summary.get("candidates_with_valid_artwork")
    if covered is None:
        covered = len(
            {
                str(item.get("candidate_id") or "")
                for item in manifest.get("images") or []
                if item.get("status") == "valid"
            }
        )
    return {
        "catalogue_candidates": len(catalogue_ids),
        "candidates_with_valid_artwork": int(covered),
        "missing_artwork_candidates": max(0, len(catalogue_ids) - int(covered)),
        "complete": bool(catalogue_ids) and int(covered) >= len(catalogue_ids),
    }


def assess_research(
    research: dict[str, Any], catalogue: dict[str, Any] | None = None
) -> dict[str, Any]:
    records = research.get("candidates") or []
    statuses = {status: 0 for status in sorted(VALID_STATUSES)}
    invalid_ready: list[dict[str, Any]] = []
    unknown_statuses: list[str] = []

    for record in records:
        status = record.get("research_gate")
        if status not in VALID_STATUSES:
            unknown_statuses.append(str(record.get("candidate_id") or record.get("name") or ""))
            continue
        statuses[status] += 1
        if status == "RESEARCH_READY":
            valid, errors = research_ready_valid(record)
            if not valid:
                invalid_ready.append(
                    {
                        "candidate_id": record.get("candidate_id"),
                        "name": record.get("name"),
                        "errors": errors,
                    }
                )

    expected_ids = {
        str(item.get("candidate_id") or "")
        for item in (catalogue or {}).get("candidates") or []
    }
    actual_ids = {str(item.get("candidate_id") or "") for item in records}
    missing_ids = sorted(expected_ids - actual_ids) if expected_ids else []

    classification_complete = (
        bool(records) and not unknown_statuses and not missing_ids
    )
    not_ready = statuses["PARTIAL_RESEARCH"] + statuses["INSUFFICIENT_EVIDENCE"]
    return {
        "total_records": len(records),
        "status_counts": statuses,
        "research_ready": statuses["RESEARCH_READY"],
        "not_ready": not_ready,
        "unknown_status_ids": unknown_statuses,
        "invalid_research_ready_records": invalid_ready,
        "missing_from_catalogue": missing_ids,
        "classification_complete": classification_complete,
        "complete": classification_complete and not invalid_ready and not_ready == 0,
    }


def assess_evaluation(evaluation: dict[str, Any] | None) -> dict[str, Any]:
    if not evaluation:
        return {
            "status": "not_started",
            "evaluations": 0,
            "draft": 0,
            "held": 0,
            "placeholder_power_floor": False,
            "complete": False,
        }
    evaluations = evaluation.get("evaluations") or []
    draft = sum(1 for item in evaluations if item.get("submit_for_review") is True)
    held = len(evaluations) - draft
    powers = [item.get("power") for item in evaluations]
    placeholder_floor = bool(evaluations) and all(power == 1 for power in powers)
    notes = " ".join(str(note) for note in evaluation.get("global_notes") or []).lower()
    if "schema floor" in notes or "placeholder" in notes:
        placeholder_floor = True
    return {
        "status": "draft_with_held_records" if held else "draft",
        "evaluations": len(evaluations),
        "draft": draft,
        "held": held,
        "placeholder_power_floor": placeholder_floor,
        "complete": bool(evaluations) and held == 0 and not placeholder_floor,
    }


def assess_publication(
    evaluation_assessment: dict[str, Any], explicit_approval: bool = False
) -> dict[str, Any]:
    ready = bool(explicit_approval and evaluation_assessment.get("complete"))
    return {
        "status": "ready" if ready else "not_ready",
        "explicit_approval": bool(explicit_approval),
        "evaluation_complete": bool(evaluation_assessment.get("complete")),
        "ready": ready,
    }


def build_report(
    catalogue: dict[str, Any],
    manifest: dict[str, Any],
    research: dict[str, Any],
    evaluation: dict[str, Any] | None = None,
    *,
    explicit_approval: bool = False,
) -> dict[str, Any]:
    catalogue_assessment = assess_catalogue(catalogue)
    artwork_assessment = assess_artwork(catalogue, manifest)
    research_assessment = assess_research(research, catalogue)
    evaluation_assessment = assess_evaluation(evaluation)
    publication_assessment = assess_publication(evaluation_assessment, explicit_approval)
    return {
        "batch_id": "naruto-batch-005",
        "stages": {
            "catalogue": catalogue_assessment,
            "artwork": artwork_assessment,
            "research": research_assessment,
            "evaluation": evaluation_assessment,
            "publication": publication_assessment,
        },
        "policy": {
            "catalogue_and_artwork_do_not_imply_research_quality": True,
            "metadata_only_fields_do_not_count_as_substantive_research": True,
            "research_complete_requires_every_candidate_research_ready": True,
            "power_and_fit_are_not_present_in_research": True,
            "no_approval_or_rarity_is_allocated": True,
        },
    }


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
