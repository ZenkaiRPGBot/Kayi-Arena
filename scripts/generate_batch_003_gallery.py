"""Generate a local HTML review gallery for Naruto batch 003."""

from __future__ import annotations

import json
from pathlib import Path

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Naruto Batch 003 Image Review Gallery</title>
<style>
body { font-family: sans-serif; background: #111; color: #eee; margin: 0; padding: 16px; }
h1 { text-align: center; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; }
.card { background: #1e1e1e; border-radius: 8px; padding: 8px; }
.card img { width: 100%; height: 120px; object-fit: cover; border-radius: 4px; }
.card .name { font-weight: bold; margin-top: 6px; }
.card .meta { font-size: 11px; color: #aaa; }
.badge { display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 10px; }
.missing { background: #8b0000; }
.pending { background: #8b6914; }
.valid { background: #1b5e20; }
</style>
</head>
<body>
<h1>Naruto Batch 003 Image Review Gallery</h1>
<div class="grid">
{cards}
</div>
</body>
</html>
"""


def main() -> None:
    cat = json.loads(Path("data/naruto_batch_003_catalogue.json").read_text(encoding="utf-8"))
    cards = []
    for c in cat["candidates"]:
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
        img_tag = f'<img src="{url}" alt="{c["name"]}" loading="lazy">' if url else '<div style="height:120px;background:#333;display:flex;align-items:center;justify-content:center;">No image</div>'
        cards.append(
            f'<div class="card">'
            f'{img_tag}'
            f'<div class="name">{c["name"]}</div>'
            f'<div class="meta">{c.get("canonical_eligibility","")} | {dims}</div>'
            f'<div class="meta"><span class="badge {status}">{status}</span> {c.get("species","")}</div>'
            f'</div>'
        )
    html = TEMPLATE.replace("{cards}", "\n".join(cards))
    out = Path("data/naruto_batch_003_review_gallery.html")
    out.write_text(html, encoding="utf-8")
    print(f"Wrote {out} with {len(cards)} cards")


if __name__ == "__main__":
    main()
