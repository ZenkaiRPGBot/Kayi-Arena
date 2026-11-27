"""Generate the consolidated, self-contained expansion review gallery."""

from __future__ import annotations

import base64
import html
import io
import json
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image

ROOT = Path("data")
DATASET = ROOT / "naruto_expansion_003_004_evaluated_dataset.json"
CATALOGUE = ROOT / "naruto_expansion_003_004_catalogue.json"
CHANGE_LOG = ROOT / "naruto_expansion_003_004_change_log.json"
IMAGE_DIR = ROOT / "naruto_images"
OUT = ROOT / "naruto_expansion_003_004_review_gallery.html"

ROLE_LABELS = [
    ("captain", "Captain"),
    ("strategist", "Strategist"),
    ("attacker", "Attacker"),
    ("tank", "Tank"),
    ("assassin", "Assassin"),
    ("support", "Support"),
    ("healer", "Healer"),
]


def find_image(candidate_id: str, sha256: str | None) -> Path | None:
    if not sha256:
        return None
    safe_id = candidate_id.replace(":", "_").replace("/", "_")
    matches = list(IMAGE_DIR.glob(f"{safe_id}_*_{sha256[:12]}.*"))
    return matches[0] if matches else None


def thumbnail_data_uri(path: Path | None) -> str | None:
    if path is None or not path.exists():
        return None
    try:
        with Image.open(path) as image:
            image = image.convert("RGBA")
            background = Image.new("RGBA", image.size, (24, 24, 24, 255))
            background.alpha_composite(image)
            image = background.convert("RGB")
            image.thumbnail((360, 360))
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=74, optimize=True)
            return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
    except Exception:
        return None


def chip(label: str, value: object, css: str = "") -> str:
    return f'<span class="chip {css}"><b>{html.escape(label)}</b> {html.escape(str(value))}</span>'


def main() -> None:
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    change_log = json.loads(CHANGE_LOG.read_text(encoding="utf-8"))
    integration = json.loads((ROOT / "naruto_expansion_003_004_integration_report.json").read_text(encoding="utf-8"))

    catalogue_by_id = {c["candidate_id"]: c for c in catalogue["candidates"]}
    changes_by_record: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for change in change_log["changes"]:
        changes_by_record[(change.get("batch", ""), change["character"])].append(change)

    rarity_counts = Counter(r["rarity"] or "Unrated" for r in dataset["characters"])
    status_counts = Counter(r["evaluation_status"] for r in dataset["characters"])
    batch_counts = Counter(r["batch"] for r in dataset["characters"])

    cards: list[str] = []
    for record in sorted(dataset["characters"], key=lambda r: (r["batch"], r["name"].lower())):
        candidate = catalogue_by_id.get(record["character_id"], {})
        images = candidate.get("images", [])
        primary = next((i for i in images if i.get("status") == "valid"), None)
        local_path = find_image(record["character_id"], primary.get("sha256") if primary else None)
        data_uri = thumbnail_data_uri(local_path)
        if data_uri:
            image_html = f'<img class="art" src="{data_uri}" alt="{html.escape(record["name"])}">'
        elif primary:
            image_html = f'<img class="art" src="{html.escape(primary["url"])}" alt="{html.escape(record["name"])}" loading="lazy">'
        else:
            image_html = '<div class="art placeholder">No artwork</div>'

        power = record.get("power")
        fit = record.get("fit") or {}
        scores = record.get("scores") or {}
        rarity = record.get("rarity") or "Unrated"
        status = record.get("evaluation_status", "held").title()
        confidence = record.get("confidence") or "unknown"
        flags = record.get("review_flags") or []
        evidence = record.get("evidence") or []
        changes = changes_by_record.get((record["batch"], record["name"]), [])

        fit_chips = "".join(
            chip(label, fit.get(key, "—") if fit else "—") for key, label in ROLE_LABELS
        )
        score_chips = "".join(
            chip(label, scores.get(key, "—") if scores else "—", "score") for key, label in ROLE_LABELS
        )

        evidence_html = "".join(
            f'<li><span class="ev-level">{html.escape(str(item.get("verification_level", "unspecified")))}</span> '
            f'{html.escape(str(item.get("lead", "")))}'
            + (
                f' <a href="{html.escape(item["url"])}" target="_blank" rel="noopener">source</a>'
                if item.get("url")
                else ""
            )
            + "</li>"
            for item in evidence
        ) or "<li>No evidence leads recorded.</li>"

        if changes:
            change_rows = "".join(
                f"<tr><td>{html.escape(str(c.get('field')))}</td>"
                f"<td>{html.escape(str(c.get('previous')))}</td>"
                f"<td>{html.escape(str(c.get('proposed')))}</td>"
                f"<td>{html.escape(str(c.get('reason', '')))}</td></tr>"
                for c in changes
            )
            change_html = (
                "<details><summary>Previous → revised</summary>"
                "<table class='changes'><thead><tr><th>Field</th><th>Previous</th><th>Revised</th><th>Reason</th></tr></thead>"
                f"<tbody>{change_rows}</tbody></table></details>"
            )
        else:
            change_html = "<div class='muted'>No changes from Claude's original record.</div>"

        rarity_detail = record.get("rarity_detail") or {}
        points = rarity_detail.get("rarity_points", "—")
        highest = rarity_detail.get("highest_role_score", "—")

        cards.append(
            f"""
<article class="card"
  data-batch="{html.escape(record['batch'])}"
  data-rarity="{html.escape(rarity)}"
  data-status="{html.escape(status)}"
  data-confidence="{html.escape(confidence)}"
  data-identity="{html.escape(record.get('identity_check', 'unknown'))}"
  data-missing="{'1' if record.get('image_status') != 'valid' else '0'}"
  data-flagged="{'1' if flags else '0'}"
  data-revised="{'1' if changes else '0'}"
  data-search="{html.escape(' '.join([record['name'], record.get('catalogue_name',''), ' '.join(record.get('aliases') or []), record.get('canonical_version') or '', record.get('identity_check') or '', ' '.join(flags), ' '.join(str(e.get('lead','')) for e in evidence)]).lower())}">
  {image_html}
  <div class="card-body">
    <div class="title-row"><h2>{html.escape(record['name'])}</h2><span class="badge batch">{html.escape(record['batch'])}</span></div>
    <div class="muted">{html.escape(record.get('canonical_version') or 'Canonical version unresolved')}</div>
    <div class="badges">
      <span class="badge status {status.lower()}">{html.escape(status)}</span>
      <span class="badge rarity {html.escape(rarity.lower())}">{html.escape(rarity)}</span>
      <span class="badge conf">{html.escape(confidence)}</span>
      <span class="badge identity">identity: {html.escape(record.get('identity_check', 'unknown'))}</span>
      <span class="badge image {'ok' if record.get('image_status') == 'valid' else 'bad'}">image: {html.escape(record.get('image_status', 'unknown'))}</span>
    </div>
    <div class="statline"><b>Power {html.escape(str(power if power is not None else '—'))}</b> · Rarity points {html.escape(str(points))} · Highest role score {html.escape(str(highest))}</div>
    <div class="section-label">Role fits</div>
    <div class="chips">{fit_chips}</div>
    <div class="section-label">Role scores (SCORE-1.0)</div>
    <div class="chips">{score_chips}</div>
    <div class="section-label">Evidence</div>
    <ul class="evidence">{evidence_html}</ul>
    <div class="section-label">Review flags</div>
    <div class="flags">{''.join(f'<span class="flag">{html.escape(f)}</span>' for f in flags) or '<span class="muted">none</span>'}</div>
    {change_html}
  </div>
</article>"""
        )

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Naruto Expansion 003–004 Review Gallery</title>
<style>
:root {{ color-scheme: dark; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; padding: 20px; background: #0f1115; color: #e8e8ea; font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; }}
h1 {{ margin: 0 0 6px; font-size: 26px; }}
h2 {{ margin: 0; font-size: 17px; }}
.sub {{ color: #9aa0aa; margin-bottom: 16px; }}
.summary {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }}
.summary .pill {{ background: #1a1d24; border: 1px solid #2a2f3a; border-radius: 999px; padding: 6px 10px; font-size: 12px; }}
.controls {{ position: sticky; top: 0; z-index: 5; background: #0f1115ee; backdrop-filter: blur(6px); border: 1px solid #232833; border-radius: 10px; padding: 12px; display: grid; grid-template-columns: 2fr repeat(4, 1fr); gap: 8px; margin-bottom: 16px; }}
.controls input, .controls select {{ width: 100%; background: #151922; color: #e8e8ea; border: 1px solid #2a2f3a; border-radius: 7px; padding: 8px; font-size: 13px; }}
.toggles {{ grid-column: 1 / -1; display: flex; flex-wrap: wrap; gap: 14px; font-size: 13px; color: #c3c8d1; }}
.toggles label {{ display: flex; align-items: center; gap: 6px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(310px, 1fr)); gap: 14px; }}
.card {{ background: #171a21; border: 1px solid #252a35; border-radius: 12px; overflow: hidden; display: flex; flex-direction: column; }}
.card.hidden {{ display: none; }}
.art {{ width: 100%; height: 220px; object-fit: contain; background: #0b0d11; }}
.art.placeholder {{ display: flex; align-items: center; justify-content: center; color: #6b7280; }}
.card-body {{ padding: 12px; display: flex; flex-direction: column; gap: 8px; }}
.title-row {{ display: flex; justify-content: space-between; gap: 8px; align-items: start; }}
.muted {{ color: #9aa0aa; font-size: 12px; line-height: 1.35; }}
.badges {{ display: flex; flex-wrap: wrap; gap: 5px; }}
.badge {{ font-size: 10px; padding: 3px 7px; border-radius: 999px; border: 1px solid #2f3542; background: #1d2129; text-transform: uppercase; letter-spacing: .03em; }}
.badge.draft {{ background: #16324a; border-color: #24557c; }}
.badge.held {{ background: #3b1f4a; border-color: #6a3a86; }}
.badge.common {{ background: #2a2d33; }}
.badge.uncommon {{ background: #173a2a; border-color: #2b6b4c; }}
.badge.rare {{ background: #16324f; border-color: #2d6598; }}
.badge.epic {{ background: #3d2450; border-color: #74479a; }}
.badge.legendary {{ background: #4d3510; border-color: #9a6b1f; }}
.badge.unrated {{ background: #333; }}
.badge.ok {{ background: #14351f; border-color: #2b6b3c; }}
.badge.bad {{ background: #4a1a1a; border-color: #8a3030; }}
.statline {{ font-size: 12px; color: #c3c8d1; }}
.section-label {{ font-size: 10px; text-transform: uppercase; letter-spacing: .08em; color: #7f8794; margin-top: 2px; }}
.chips {{ display: flex; flex-wrap: wrap; gap: 4px; }}
.chip {{ font-size: 10px; background: #20242d; border: 1px solid #2c3140; border-radius: 6px; padding: 3px 6px; }}
.chip b {{ color: #9fb3d1; font-weight: 600; }}
.chip.score b {{ color: #d1b99f; }}
.evidence {{ margin: 0; padding-left: 18px; font-size: 11px; color: #b9c0cb; line-height: 1.4; }}
.evidence li {{ margin-bottom: 4px; }}
.ev-level {{ font-size: 9px; text-transform: uppercase; color: #7f8794; border: 1px solid #2c3140; border-radius: 4px; padding: 1px 4px; margin-right: 4px; }}
.flags {{ display: flex; flex-wrap: wrap; gap: 4px; }}
.flag {{ font-size: 9px; background: #3a2a12; border: 1px solid #6b4a1f; border-radius: 4px; padding: 2px 5px; color: #e0c08a; }}
details {{ font-size: 11px; color: #b9c0cb; }}
summary {{ cursor: pointer; color: #9fb3d1; }}
table.changes {{ width: 100%; border-collapse: collapse; margin-top: 6px; }}
table.changes th, table.changes td {{ border: 1px solid #2a2f3a; padding: 3px 4px; text-align: left; vertical-align: top; }}
table.changes th {{ color: #7f8794; font-weight: 500; }}
#count {{ font-size: 12px; color: #9aa0aa; }}
@media (max-width: 900px) {{ .controls {{ grid-template-columns: 1fr 1fr; }} }}
</style>
</head>
<body>
<h1>Naruto Expansion 003–004 Review Gallery</h1>
<div class="sub">Batches 003, 004-A and 004-B · SCORE-1.0 · RARITY-0.2 · draft review only — nothing is approved or published.</div>
<div class="summary">
  <span class="pill">Records: {len(dataset['characters'])}</span>
  <span class="pill">Draft: {status_counts.get('draft', 0)}</span>
  <span class="pill">Held: {status_counts.get('held', 0)}</span>
  <span class="pill">Unmatched: {integration.get('unmatched', 0)}</span>
  <span class="pill">Images valid: {sum(1 for r in dataset['characters'] if r.get('image_status') == 'valid')}</span>
  <span class="pill">Rarity: {', '.join(f'{k} {v}' for k, v in sorted(rarity_counts.items()))}</span>
</div>
<div class="controls">
  <input id="search" type="search" placeholder="Search name, alias, version, evidence, flag…">
  <select id="batch"><option value="">All batches</option>{''.join(f'<option>{b}</option>' for b in sorted(batch_counts))}</select>
  <select id="rarity"><option value="">All rarities</option>{''.join(f'<option>{r}</option>' for r in sorted(rarity_counts))}</select>
  <select id="status"><option value="">All statuses</option><option>Draft</option><option>Held</option></select>
  <select id="confidence"><option value="">All confidence</option><option>high</option><option>medium</option><option>low</option></select>
  <div class="toggles">
    <label><input type="checkbox" id="missing"> Missing artwork only</label>
    <label><input type="checkbox" id="flagged"> Disputed / flagged only</label>
    <label><input type="checkbox" id="revised"> Revised records only</label>
    <span id="count"></span>
  </div>
</div>
<div class="grid" id="grid">
{''.join(cards)}
</div>
<script>
const cards = Array.from(document.querySelectorAll('.card'));
const search = document.getElementById('search');
const batch = document.getElementById('batch');
const rarity = document.getElementById('rarity');
const status = document.getElementById('status');
const confidence = document.getElementById('confidence');
const missing = document.getElementById('missing');
const flagged = document.getElementById('flagged');
const revised = document.getElementById('revised');
const count = document.getElementById('count');
function apply() {{
  const q = search.value.trim().toLowerCase();
  let visible = 0;
  for (const card of cards) {{
    const ok =
      (!q || card.dataset.search.includes(q)) &&
      (!batch.value || card.dataset.batch === batch.value) &&
      (!rarity.value || card.dataset.rarity === rarity.value) &&
      (!status.value || card.dataset.status === status.value) &&
      (!confidence.value || card.dataset.confidence === confidence.value) &&
      (!missing.checked || card.dataset.missing === '1') &&
      (!flagged.checked || card.dataset.flagged === '1') &&
      (!revised.checked || card.dataset.revised === '1');
    card.classList.toggle('hidden', !ok);
    if (ok) visible++;
  }}
  count.textContent = `${{visible}} / ${{cards.length}} shown`;
}}
[search, batch, rarity, status, confidence, missing, flagged, revised].forEach(el => el.addEventListener('input', apply));
apply();
</script>
</body>
</html>"""

    OUT.write_text(html_doc, encoding="utf-8")
    print(f"wrote {OUT} with {len(cards)} cards, {len(html_doc) / 1024 / 1024:.2f} MB")


if __name__ == "__main__":
    main()
