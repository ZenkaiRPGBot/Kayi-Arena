"""Create a revised evaluation file with targeted research corrections."""

from __future__ import annotations

import json
from pathlib import Path

ORIG = Path("data/naruto_batch_003_evaluations.json")
REVISED = Path("data/naruto_batch_003_evaluations_revised.json")
CHANGELOG = Path("data/naruto_batch_003_change_log.json")

# Proposed changes: name -> {field: new_value, reason, source}
CHANGES = {
    "Dan Kato": {
        "evaluation_status": ("held", "draft"),
        "reason": "Ghost Transformation Jutsu (S-rank) demonstrated in the Fourth War arc; not flashback-only.",
        "source": "Narutopedia: Dan Kato; chapter 591 context",
    },
    "Mabui": {
        "evaluation_status": ("held", "draft"),
        "fit.support": (2, 3),
        "reason": "Heavenly Transfer Technique (chapter 562) provides transport/support; demonstrated in war arc.",
        "source": "Narutopedia: Heavenly Transfer Technique; chapter 562",
    },
    "Yugito Nii": {
        "evidence_leads": None,
        "reason": "Captured by Hidan and Kakuzu, not Deidara. Evidence lead corrected.",
        "source": "Narutopedia: Yugito Nii; Akatsuki Suppression Mission arc",
    },
    "Choji Akimichi": {
        "canonical_version": None,
        "reason": "War-era Butterfly Mode without pills (chapter 533). Ratings may need review.",
        "source": "Naruto chapter 533",
    },
    "Shizune": {
        "fit.captain": (2, 3),
        "fit.healer": (3, 4),
        "reason": "Captain of the Allied Shinobi Forces Logistical Support and Medical Division; talented medical-nin.",
        "source": "Narutopedia: Shizune; Shikaku's revised battle strategy",
    },
    "Jugo": {
        "fit.healer": (0, 2),
        "reason": "Cellular Regeneration Ejection (chapter 414) heals compatible allies conditionally.",
        "source": "Narutopedia: Cellular Regeneration Ejection; chapter 414",
    },
    "Karin": {
        "fit.healer": (3, 3),
        "reason": "Heal Bite heals life-threatening injuries; effectiveness comparable to support healer. No change proposed.",
        "source": "Narutopedia: Heal Bite",
    },
    "Ino Yamanaka": {
        "fit.support": (4, 4),
        "reason": "Support suitability maintained; shared role with Inoichi noted.",
        "source": "Fourth War arc: mind-transmission relay",
    },
    "Inoichi Yamanaka": {
        "fit.support": (4, 4),
        "reason": "Support suitability maintained; individual contribution distinct from Ino.",
        "source": "Fourth War arc: Alliance headquarters mind network",
    },
}


def apply_change(entry, field, old, new):
    if field == "evaluation_status":
        entry["evaluation_status"] = new
    elif field.startswith("fit."):
        role = field.split(".", 1)[1]
        entry["fit"][role] = new
    elif field == "canonical_version":
        entry["canonical_version"] = entry["canonical_version"] + " (review: Butterfly Mode without pills, ch.533)"
    elif field == "evidence_leads":
        for ev in entry.get("evidence_leads", []):
            if "Deidara" in str(ev):
                ev["lead"] = ev["lead"].replace("captured by Deidara", "captured by Hidan and Kakuzu")


def main() -> None:
    data = json.loads(ORIG.read_text(encoding="utf-8"))
    changelog = []

    for entry in data["characters"]:
        name = entry["name"]
        if name not in CHANGES:
            continue
        change = CHANGES[name]
        for field, val in change.items():
            if field in ("reason", "source"):
                continue
            if isinstance(val, tuple):
                old, new = val
                if old == new:
                    continue
                apply_change(entry, field, old, new)
                changelog.append({
                    "character": name,
                    "field": field,
                    "previous": old,
                    "proposed": new,
                    "reason": change["reason"],
                    "source": change["source"],
                })
            elif field == "evidence_leads" and val is None:
                apply_change(entry, field, None, None)
                changelog.append({
                    "character": name,
                    "field": field,
                    "previous": "captured by Deidara",
                    "proposed": "captured by Hidan and Kakuzu",
                    "reason": change["reason"],
                    "source": change["source"],
                })
            elif field == "canonical_version" and val is None:
                apply_change(entry, field, None, None)
                changelog.append({
                    "character": name,
                    "field": field,
                    "previous": entry["canonical_version"],
                    "proposed": entry["canonical_version"],
                    "reason": change["reason"],
                    "source": change["source"],
                })

    # Mark revised
    data["batch_id"] = data["batch_id"] + "_revised"
    data["batch_status"] = "draft"
    data["notes"] = data.get("notes", []) + ["Revised evaluation with targeted research corrections."]

    REVISED.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    CHANGELOG.write_text(json.dumps({"changes": changelog}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Revised file written. {len(changelog)} proposed changes.")


if __name__ == "__main__":
    main()
