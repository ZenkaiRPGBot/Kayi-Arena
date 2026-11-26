"""Generate a local HTML review gallery for Naruto character images."""

from __future__ import annotations

import json
from pathlib import Path

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Naruto Image Review Gallery</title>
<style>
body { font-family: sans-serif; background: #111; color: #eee; margin: 0; padding: 16px; }
h1 { text-align: center; }
.filters { text-align: center; margin-bottom: 16px; }
.filters button { margin: 0 4px; padding: 6px 12px; cursor: pointer; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; }
.card { background: #1e1e1e; border-radius: 8px; padding: 8px; }
.card img { width: 100%; height: 140px; object-fit: cover; border-radius: 4px; }
.card .name { font-weight: bold; margin-top: 6px; }
.card .meta { font-size: 12px; color: #aaa; }
.card .status { font-size: 12px; margin-top: 4px; }
.badge { display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 11px; }
.missing { background: #8b0000; }
.pending { background: #8b6914; }
.valid { background: #1b5e20; }
</style>
</head>
<body>
<h1>Naruto Image Review Gallery</h1>
<div class="filters">
  <button onclick="filter('all')">All</button>
  <button onclick="filter('missing')">Missing</button>
  <button onclick="filter('pending')">Pending</button>
  <button onclick="filter('valid')">Valid</button>
</div>
<div class="grid" id="grid">
{cards}
</div>
<script>
function filter(mode) {
  document.querySelectorAll('.card').forEach(card => {
    if (mode === 'all' || card.dataset.status === mode) card.style.display = '';
    else card.style.display = 'none';
  });
}
</script>
</body>
</html>
"""


def main() -> None:
    catalogue = json.loads(Path("data/naruto_candidates.json").read_text(encoding="utf-8"))
    evaluated = {}
    if Path("data/naruto_evaluated_60_dataset.json").exists():
        ed = json.loads(Path("data/naruto_evaluated_60_dataset.json").read_text(encoding="utf-8"))
        for r in ed["characters"]:
            evaluated[r["character_id"]] = r

    by_id = {c["candidate_id"]: c for c in catalogue["candidates"]}
    cards = []
    for cid, rec in evaluated.items():
        c = by_id.get(cid, {})
        images = c.get("images", [])
        if images:
            img = images[0]
            url = img.get("url", "")
            status = img.get("status", "pending")
            w = img.get("width")
            h = img.get("height")
            dims = f"{w}x{h}" if w and h else ""
        else:
            url = ""
            status = "missing"
            dims = ""
        rarity = rec.get("rarity", "unrated")
        canonical = rec.get("canonical_version", "")
        if isinstance(canonical, dict):
            canonical = canonical.get("manga") or canonical.get("anime") or "unknown"
        source = images[0].get("source", "") if images else "none"
        concern = ", ".join(rec.get("review_flags", [])) or "none"
        img_tag = f'<img src="{url}" alt="{rec["name"]}" loading="lazy">' if url else '<div style="height:140px;background:#333;display:flex;align-items:center;justify-content:center;">No image</div>'
        cards.append(
            f'<div class="card" data-status="{status}">'
            f'{img_tag}'
            f'<div class="name">{rec["name"]}</div>'
            f'<div class="meta">{canonical} | {rarity} | {dims}</div>'
            f'<div class="meta">Source: {source}</div>'
            f'<div class="status"><span class="badge {status}">{status}</span> {concern}</div>'
            f'</div>'
        )

    html = TEMPLATE.replace("{cards}", "\n".join(cards))
    out = Path("data/naruto_image_review.html")
    out.write_text(html, encoding="utf-8")
    print(f"Wrote {out} with {len(cards)} cards")


if __name__ == "__main__":
    main()
