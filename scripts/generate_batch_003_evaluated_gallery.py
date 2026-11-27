"""Generate an HTML review gallery for batch 003 with ratings and rarity."""

from __future__ import annotations

import json
from pathlib import Path

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Naruto Batch 003 Evaluated Review Gallery</title>
<style>
body { font-family: sans-serif; background: #111; color: #eee; margin: 0; padding: 16px; }
h1 { text-align: center; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px; }
.card { background: #1e1e1e; border-radius: 8px; padding: 8px; }
.card img { width: 100%; height: 130px; object-fit: cover; border-radius: 4px; }
.card .name { font-weight: bold; margin-top: 6px; }
.card .meta { font-size: 11px; color: #aaa; }
.card .ratings { font-size: 11px; margin-top: 4px; }
.badge { display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 10px; }
.missing { background: #8b0000; }
.pending { background: #8b6914; }
.valid { background: #1b5e20; }
.held { background: #4a148c; }
</style>
</head>
<body>
<h1>Naruto Batch 003 Evaluated Review Gallery</h1>
<div class="grid">
{cards}
</div>
</body>
</html>
"""


def main() -> None:
    dataset = json.loads(Path("data/naruto_batch_003_evaluated_dataset.json").read_text(encoding="utf-8"))
    catalogue = json.loads(Path("data/naruto_batch_003_catalogue.json").read_text(encoding="utf-8"))
    by_id = {c["candidate_id"]: c for c in catalogue["candidates"]}

    cards = []
    for rec in dataset["characters"]:
        c = by_id.get(rec["character_id"], {})
        images = c.get("images", [])
        if images:
            img = images[0]
            url = img.get("url", "")
            status = img.get("status", "pending")
            dims = f'{img.get("width")}x{img.get("height")}' if img.get("width") else ""
        else:
            url = ""
            status = "missing"
            dims = ""
        img_tag = f'<img src="{url}" alt="{rec["name"]}" loading="lazy">' if url else '<div style="height:130px;background:#333;display:flex;align-items:center;justify-content:center;">No image</div>'
        fit = rec.get("fit", {})
        fit_str = " ".join(f"{k[0].upper()}:{v}" for k, v in fit.items())
        flags = ", ".join(rec.get("review_flags", [])) or "none"
        badge_class = "held" if rec.get("held") else status
        cards.append(
            f'<div class="card">'
            f'{img_tag}'
            f'<div class="name">{rec["name"]} (P{rec["power"]})</div>'
            f'<div class="meta">{rec.get("canonical_version","")} | {rec["rarity"]} | {dims}</div>'
            f'<div class="ratings">{fit_str}</div>'
            f'<div class="meta"><span class="badge {badge_class}">{badge_class}</span> {flags}</div>'
            f'</div>'
        )

    html = TEMPLATE.replace("{cards}", "\n".join(cards))
    out = Path("data/naruto_batch_003_review_gallery_evaluated.html")
    out.write_text(html, encoding="utf-8")
    print(f"Wrote {out} with {len(cards)} cards")


if __name__ == "__main__":
    main()
