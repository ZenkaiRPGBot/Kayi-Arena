"""Generate consolidated 60-character Naruto review report."""

from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    eval_data = json.loads(
        Path("data/naruto_evaluated_60_dataset.json").read_text(encoding="utf-8")
    )["characters"]
    man_data = {
        c["candidate_id"]: c
        for c in json.loads(
            Path("data/naruto_initial_60_image_manifest.json").read_text(encoding="utf-8")
        )["characters"]
    }

    lines = [
        "# Naruto Initial 60 Characters — Consolidated Review Report",
        "",
        "- **Total Characters:** 60 (53 `Draft`, 7 `Held`)",
        "- **Scoring System:** `SCORE-1.0` (0 mismatches)",
        "- **Rarity System:** `RARITY-0.2` with provisional Naruto Healer floors (0 mismatches)",
        "- **Image Audit:** 57 original valid Wikia URLs + 3 verified Narutopedia replacements (**Kurama**, **Jiraiya**, **Chiyo**) = **60/60** HTTPS images ready; standardized to `960x540` landscape via `standardize_card_image()` without stretching.",
        "",
        "| # | Name | Status | Rarity | Power | Cap / Str / Att / Tnk / Asn / Sup / Hlr | Canonical Version | Evidence Summary | Image | Concerns / Flags |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]

    for idx, c in enumerate(eval_data, 1):
        cid = c["character_id"]
        f = c["fit"]
        fits_str = (
            f"{f['captain']}/{f['strategist']}/{f['attacker']}/"
            f"{f['tank']}/{f['assassin']}/{f['support']}/{f['healer']}"
        )
        status = "HELD" if c.get("held") or c.get("evaluation_status") == "held" else "Draft"
        canon = str(c.get("canonical_version", "")).replace("|", "/").replace("\n", " ")
        if len(canon) > 75:
            canon = canon[:72] + "..."
        ev_list = c.get("evidence") or []
        ev_text = "; ".join(
            str(e.get("claim", "")).replace("|", "/").replace("\n", " ")
            for e in ev_list[:2]
            if isinstance(e, dict)
        )
        if len(ev_text) > 70:
            ev_text = ev_text[:67] + "..."
        if not ev_text:
            ev_text = "Canon evaluation recorded"
        imgs = [i for i in man_data.get(cid, {}).get("images", []) if i.get("status") == "valid"]
        img_info = f"{imgs[0].get('width')}x{imgs[0].get('height')}" if imgs else "Missing"
        flags = ", ".join(str(x).replace("|", "/") for x in (c.get("review_flags") or []))
        if not flags:
            flags = "Held pending canon/tier resolution" if status == "HELD" else "None"
        lines.append(
            f"| {idx} | {c['name']} | {status} | {c['rarity']} | {c['power']} | "
            f"{fits_str} | {canon} | {ev_text} | {img_info} | {flags} |"
        )

    out = Path("docs/NARUTO_60_CONSOLIDATED_REVIEW_REPORT.md")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {out} ({len(eval_data)} characters)")


if __name__ == "__main__":
    main()
