"""Refresh stale Dattebayo image URLs from the live API."""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

API = "https://dattebayo-api.onrender.com/characters"
NAMES = [
    "Zaku Abumi",
    "Kin Tsuchi",
    "Taiseki",
    "Shigure",
    "Baiu",
    "Midare",
    "Oboro",
    "Mubi",
    "Kagari",
    "Yashamaru",
]

catalogue_path = Path("data/naruto_expansion_003_004_catalogue.json")
catalogue = json.loads(catalogue_path.read_text(encoding="utf-8"))
by_name = {c["name"]: c for c in catalogue["candidates"]}

with httpx.Client(timeout=60.0) as client:
    for name in NAMES:
        try:
            response = client.get(API, params={"name": name, "limit": 10})
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            print(f"{name}: API error {exc}")
            continue
        matches = payload.get("characters", [])
        match = next((m for m in matches if m.get("name", "").lower() == name.lower()), None)
        if match is None:
            print(f"{name}: no exact API match; candidates={[m.get('name') for m in matches]}")
            continue
        images = match.get("images") or []
        if not images:
            print(f"{name}: API has no images")
            continue
        record = by_name.get(name)
        if record is None:
            print(f"{name}: not in expansion catalogue")
            continue
        record["image_urls"] = images
        record["images"] = [
            {
                "url": url,
                "source": "dattebayo",
                "status": "pending",
                "rights": "source-dependent; review before publication",
            }
            for url in images
        ]
        print(f"{name}: refreshed {len(images)} image URL(s) -> {images[0]}")
        time.sleep(0.2)

catalogue_path.write_text(json.dumps(catalogue, indent=2, ensure_ascii=False), encoding="utf-8")
print("saved", catalogue_path)
