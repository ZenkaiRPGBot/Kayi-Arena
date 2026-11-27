"""Naruto 60 character integration, testing dataset, and idempotent bootstrap.

Never automatically approves preliminary records for production.
Preserves the 7 Held characters until their evaluation concerns are resolved.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.database.models import (
    EvaluationStatus,
    EvidenceItem,
    ImageMetadata,
    ImageValidationStatus,
    SpeciesKind,
)
from app.database.repository import CharacterDatabase
from app.scoring import DatasetKind, SCORING_ROLES

HELD_EXPANSION_003_004_NAMES: frozenset[str] = frozenset(
    {
        "White Zetsu",
        "Tajima Uchiha",
        "Butsuma Senju",
        "Itama Senju",
        "Kawarama Senju",
        "Ashina Uzumaki",
        "Nawaki",
        "Baiu",
        "Midare",
        "Mubi",
        "Kagari",
        "Karura",
        "Reto — First Kazekage",
        "Byakuren — First Mizukage",
        "A — First Raikage",
        "A — Second Raikage",
        "Ishikawa — First Tsuchikage",
    }
)

HELD_NARUTO_NAMES: frozenset[str] = frozenset(
    {
        "Rock Lee",
        "Hagoromo Otsutsuki",
        "Hamura Otsutsuki",
        "Indra Otsutsuki",
        "Ashura Otsutsuki",
        "Sakumo Hatake",
        "Izuna Uchiha",
    }
)

ALL_HELD_NARUTO_NAMES: frozenset[str] = HELD_NARUTO_NAMES | HELD_EXPANSION_003_004_NAMES

_NON_HUMAN_IDS: frozenset[str] = frozenset(
    {
        "dattebayo:711",  # Kurama (Tailed Beast)
    }
)


@dataclass(frozen=True, slots=True)
class NarutoLoadSummary:
    total_loaded: int
    draft_count: int
    held_count: int
    approved_for_testing: int
    published_testing_version: str | None = None
    published_production_version: str | None = None
    expansion_loaded: int = 0


def _best_manifest_image(entry: dict[str, Any] | None) -> ImageMetadata:
    if not entry:
        return ImageMetadata(status=ImageValidationStatus.PENDING)
    valid = [img for img in entry.get("images", []) if img.get("status") == "valid"]
    if not valid:
        return ImageMetadata(status=ImageValidationStatus.FAILED)
    best = max(
        valid,
        key=lambda i: (
            1 if (i.get("width") or 0) >= (i.get("height") or 0) else 0,
            (i.get("width") or 0) * (i.get("height") or 0),
        ),
    )
    fmt = str(best.get("format") or "png").lower()
    mime = f"image/{'jpeg' if fmt == 'jpg' else fmt}"
    return ImageMetadata(
        url_or_ref=str(best.get("url", "")),
        source_ref=str(best.get("source_ref") or "https://naruto.fandom.com"),
        mime_type=mime,
        width=best.get("width"),
        height=best.get("height"),
        checksum=str(best.get("sha256") or ""),
        # Technically validated; identity verification remains separate unless verified.
        status=ImageValidationStatus.VERIFIED,
    )


def load_naruto_60_into_db(
    db: CharacterDatabase,
    *,
    dataset_path: Path = Path("data/naruto_evaluated_60_dataset.json"),
    manifest_path: Path = Path("data/naruto_initial_60_image_manifest.json"),
    publish_testing_dataset: bool = False,
    testing_version: str = "naruto-prelim-test-v1",
) -> NarutoLoadSummary:
    """Idempotently load the 60 evaluated Naruto records into CharacterDatabase.

    - Production records remain in DRAFT/Held status (never auto-approved).
    - When `publish_testing_dataset=True`, approves ONLY the 53 non-held records
      for an isolated `DatasetKind.SYNTHETIC` testing dataset, keeping the 7
      Held characters unapproved.
    """
    try:
        db.get_universe("naruto")
    except Exception:
        db.create_universe("naruto", "Naruto", active=True)

    eval_data = json.loads(dataset_path.read_text(encoding="utf-8"))
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_by_id = {
        c["candidate_id"]: c for c in manifest_data.get("characters", [])
    }

    existing_map = {c.character_id: c for c in db.list_characters("naruto")}
    draft_count = 0
    held_count = 0
    approved_testing = 0

    for item in eval_data.get("characters", []):
        cid = str(item["character_id"])
        is_held = bool(item.get("held")) or item.get("evaluation_status") == "held" or item["name"] in HELD_NARUTO_NAMES
        if is_held:
            held_count += 1
        else:
            draft_count += 1

        img_meta = _best_manifest_image(manifest_by_id.get(cid))
        species = SpeciesKind.NON_HUMAN if cid in _NON_HUMAN_IDS else SpeciesKind.HUMAN
        ev_items = tuple(
            EvidenceItem(
                target=str(e.get("target", "general")),
                claim=str(e.get("claim", "")),
                source_ref=str(e.get("source_ref", "")),
            )
            for e in (item.get("evidence") or ())
            if isinstance(e, dict) and e.get("claim")
        )

        existing = existing_map.get(cid)
        if existing is not None:
            if not existing.image.url_or_ref and img_meta.url_or_ref:
                db.update_image_metadata(cid, img_meta)
        else:
            db.add_character(
                character_id=cid,
                universe_id="naruto",
                name=str(item["name"]),
                aliases=tuple(str(a) for a in (item.get("aliases") or ())),
                species=species,
                rarity=str(item["rarity"]),
                power=int(item["power"]),
                fit={k: int(v) for k, v in item["fit"].items()},
                canonical_version=str(item.get("canonical_version", "")),
                image=img_meta,
                evidence=ev_items,
            )

        if publish_testing_dataset and not is_held:
            entry = db.get_character_entry(cid)
            if entry.status is EvaluationStatus.DRAFT:
                db.submit_for_review(cid)
                entry = db.get_character_entry(cid)
            if entry.status is EvaluationStatus.REVIEW:
                db.approve_character(cid)
            approved_testing += 1

    pub_test_ver: str | None = None
    if publish_testing_dataset:
        existing_test = db.get_latest_published_version("naruto", kind=DatasetKind.TEST)
        if existing_test is None:
            manifest, _ = db.publish_dataset(
                universe_id="naruto",
                dataset_version=testing_version,
                kind=DatasetKind.TEST,
            )
            pub_test_ver = manifest.dataset_version
        else:
            pub_test_ver = existing_test

    return NarutoLoadSummary(
        total_loaded=draft_count + held_count,
        draft_count=draft_count,
        held_count=held_count,
        approved_for_testing=approved_testing,
        published_testing_version=pub_test_ver,
        published_production_version=db.get_latest_published_version("naruto", kind=DatasetKind.PRODUCTION),
    )


def export_approved_snapshot(
    db: CharacterDatabase,
    *,
    universe_id: str = "naruto",
    output_path: Path = Path("data/approved_naruto_snapshot.json"),
) -> dict[str, Any]:
    """Export owner-approved character IDs and latest production dataset version."""
    approved = [
        c.character_id
        for c in db.list_characters(universe_id=universe_id, status=EvaluationStatus.APPROVED)
    ]
    latest_prod = db.get_latest_published_version(universe_id, kind=DatasetKind.PRODUCTION)
    payload = {
        "universe_id": universe_id,
        "approved_character_ids": sorted(approved),
        "dataset_version": latest_prod,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


_ROLE_BY_LOWER: dict[str, str] = {r.lower(): r for r in SCORING_ROLES}


def get_naruto_batch_map(
    *,
    initial_path: Path = Path("data/naruto_evaluated_60_dataset.json"),
    ka_import_path: Path = Path("data/naruto_expansion_003_004_ka_import.json"),
) -> dict[str, str]:
    """Return a character_id -> batch label mapping ('initial_60', '003', '004-A', '004-B')."""
    mapping: dict[str, str] = {}
    if initial_path.exists():
        init_data = json.loads(initial_path.read_text(encoding="utf-8"))
        for item in init_data.get("characters", []):
            cid = str(item.get("character_id", "")).strip()
            if cid:
                mapping[cid] = "initial_60"
    if ka_import_path.exists():
        exp_data = json.loads(ka_import_path.read_text(encoding="utf-8"))
        for item in exp_data.get("characters", []):
            cid = str(item.get("character_id", "")).strip()
            batch = str(item.get("batch", "")).strip()
            if cid and batch:
                mapping[cid] = batch
    return mapping


def load_naruto_expansion_003_004_into_db(
    db: CharacterDatabase,
    *,
    ka_import_path: Path = Path("data/naruto_expansion_003_004_ka_import.json"),
    manifest_path: Path = Path("data/naruto_expansion_003_004_image_manifest.json"),
) -> tuple[int, int]:
    """Idempotently import Batches 003-004 Draft characters without touching existing approvals.

    - Imports only `importable` Draft records (131 characters).
    - Never imports or fabricates scores for the 17 Held records.
    - Never overwrites existing characters' evaluation status, ratings, or approved records.
    """
    if not ka_import_path.exists():
        return 0, 0
    try:
        db.get_universe("naruto")
    except Exception:
        db.create_universe("naruto", "Naruto", active=True)

    ka_data = json.loads(ka_import_path.read_text(encoding="utf-8"))
    manifest_by_id: dict[str, dict[str, Any]] = {}
    if manifest_path.exists():
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        for c in manifest_data.get("characters", []):
            cand_id = str(c.get("candidate_id", "")).strip()
            if cand_id:
                manifest_by_id[cand_id] = c
                manifest_by_id[cand_id.replace(":", "_")] = c

    existing_map = {c.character_id: c for c in db.list_characters("naruto")}
    loaded = 0
    for item in ka_data.get("characters", []):
        if not item.get("importable"):
            continue
        cid = str(item["character_id"])
        if item.get("name") in ALL_HELD_NARUTO_NAMES:
            continue

        manifest_entry = manifest_by_id.get(cid) or manifest_by_id.get(cid.replace("_", ":"))
        img_meta = _best_manifest_image(manifest_entry)
        existing = existing_map.get(cid)
        if existing is not None:
            if not existing.image.url_or_ref and img_meta.url_or_ref:
                db.update_image_metadata(cid, img_meta)
            loaded += 1
            continue

        species_raw = str(item.get("species", "human")).strip().lower()
        species = SpeciesKind.NON_HUMAN if species_raw == SpeciesKind.NON_HUMAN.value else SpeciesKind.HUMAN
        raw_fit = item.get("fit") or {}
        fit = {
            _ROLE_BY_LOWER[k.lower()]: int(v)
            for k, v in raw_fit.items()
            if k.lower() in _ROLE_BY_LOWER
        }
        ev_items = tuple(
            EvidenceItem(
                target=str(e.get("target", "overall")),
                grade=str(e.get("grade", "C")),
                source_ref=str(e.get("source_ref", "")),
                summary=str(e.get("summary") or e.get("claim") or ""),
            )
            for e in (item.get("evidence") or ())
            if isinstance(e, dict) and (e.get("summary") or e.get("claim"))
        )
        db.add_character(
            character_id=cid,
            universe_id="naruto",
            name=str(item["name"]),
            aliases=tuple(str(a) for a in (item.get("aliases") or ())),
            species=species,
            rarity=str(item["rarity"]),
            power=int(item["power"]),
            fit=fit,
            canonical_version=str(item.get("canonical_version", "")),
            image=img_meta,
            evidence=ev_items,
        )
        loaded += 1

    held_count = len(ka_data.get("held_records", []))
    return loaded, held_count


def bootstrap_naruto_database(
    db: CharacterDatabase,
    *,
    dataset_kind: DatasetKind = DatasetKind.PRODUCTION,
    snapshot_path: Path | None = None,
    include_expansion: bool = False,
) -> NarutoLoadSummary:
    """Idempotent startup bootstrap for ephemeral filesystems (e.g., Render Free).

    - Always loads the 60 preliminary records into DRAFT/Held status if missing.
    - Never auto-approves preliminary records for production.
    - In SYNTHETIC testing mode, publishes the 53 non-held testing dataset.
    - In PRODUCTION mode, restores ONLY explicitly owner-approved IDs from
      `snapshot_path` if that snapshot file exists.
    """
    summary = load_naruto_60_into_db(
        db,
        publish_testing_dataset=(dataset_kind is DatasetKind.TEST),
    )

    exp_loaded = 0
    if include_expansion:
        exp_loaded, _ = load_naruto_expansion_003_004_into_db(db)

    if dataset_kind is DatasetKind.PRODUCTION and snapshot_path is not None and snapshot_path.exists():
        snap = json.loads(snapshot_path.read_text(encoding="utf-8"))
        uid = str(snap.get("universe_id", "naruto"))
        approved_ids = [str(cid) for cid in snap.get("approved_character_ids", [])]
        for cid in approved_ids:
            try:
                entry = db.get_character_entry(cid)
            except Exception:
                continue
            if entry.status is EvaluationStatus.DRAFT:
                db.submit_for_review(cid)
                entry = db.get_character_entry(cid)
            if entry.status is EvaluationStatus.REVIEW:
                db.approve_character(cid)

        ver = snap.get("dataset_version")
        if ver and approved_ids and db.get_latest_published_version(uid, kind=DatasetKind.PRODUCTION) is None:
            db.publish_dataset(
                universe_id=uid,
                dataset_version=str(ver),
                kind=DatasetKind.PRODUCTION,
            )

    return NarutoLoadSummary(
        total_loaded=summary.total_loaded,
        draft_count=summary.draft_count,
        held_count=summary.held_count,
        approved_for_testing=summary.approved_for_testing,
        published_testing_version=summary.published_testing_version,
        published_production_version=db.get_latest_published_version("naruto", kind=DatasetKind.PRODUCTION),
        expansion_loaded=exp_loaded,
    )
