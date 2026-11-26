"""Dattebayo API provider for Naruto universe candidates."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from app.content.models import CandidateCharacter, CandidateImage, utc_now


BASE_URL = "https://dattebayo-api.onrender.com/characters"
PAGE_SIZE = 100
MAX_RETRIES = 3
RETRY_DELAY = 1.0


def _fetch_json(url: str, timeout: float = 30.0) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            request = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))
    raise RuntimeError(f"Failed to fetch {url}: {last_error}")


def _slug(name: str) -> str:
    return name.strip().replace(" ", "_")


def _universe(item: dict[str, Any]) -> str:
    debut = item.get("debut") or {}
    anime = str(debut.get("anime") or "")
    manga = str(debut.get("manga") or "")
    if anime.lower().startswith("boruto") or "boruto" in manga.lower():
        return "Boruto"
    return "Naruto"


def _filler_exclusive(item: dict[str, Any]) -> bool:
    debut = item.get("debut") or {}
    anime = str(debut.get("anime") or "")
    manga = str(debut.get("manga") or "")
    appears = str(debut.get("appearsIn") or "")
    if not manga and "anime" in appears.lower():
        return True
    if "anime only" in anime.lower() or "anime only" in manga.lower():
        return True
    return False


def _personal(item: dict[str, Any]) -> dict[str, Any]:
    value = item.get("personal")
    if isinstance(value, dict):
        return value
    return {}


def _species(item: dict[str, Any]) -> str | None:
    personal = _personal(item)
    species = personal.get("species")
    if species is None:
        return None
    return str(species).strip() or None


def _classification(item: dict[str, Any]) -> list[str]:
    personal = _personal(item)
    value = personal.get("classification")
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str) and value:
        return [value]
    return []


def _titles(item: dict[str, Any]) -> list[str]:
    personal = _personal(item)
    titles = personal.get("titles")
    if isinstance(titles, list):
        return [str(t) for t in titles]
    if isinstance(titles, str) and titles:
        return [titles]
    return []


def _eligibility(item: dict[str, Any]) -> tuple[str, str]:
    species = _species(item)
    if species and species.lower() not in {"human", "none"}:
        return "uncertain", f"non-human or special species reported by source: {species}"
    if _filler_exclusive(item):
        return "uncertain", "debut appears to be anime/filler-only"
    debut = item.get("debut") or {}
    appears = str(debut.get("appearsIn") or "")
    if "manga" not in appears.lower():
        return "uncertain", "no manga debut recorded by source"
    return "eligible", "manga debut recorded by source"


class DattebayoProvider:
    name = "dattebayo"
    universe = "Naruto"

    def __init__(self, *, page_size: int = PAGE_SIZE, max_pages: int | None = None) -> None:
        self.page_size = page_size
        self.max_pages = max_pages

    def collect(self) -> list[CandidateCharacter]:
        candidates: list[CandidateCharacter] = []
        page = 1
        total = None
        while True:
            if self.max_pages is not None and page > self.max_pages:
                break
            data = _fetch_json(f"{BASE_URL}?page={page}&limit={self.page_size}")
            if total is None:
                total = int(data.get("total", 0))
            items = data.get("characters") or []
            if not items:
                break
            for item in items:
                candidates.append(self._map(item))
            if len(candidates) >= total:
                break
            page += 1
        return candidates

    def _map(self, item: dict[str, Any]) -> CandidateCharacter:
        raw_id = item.get("id")
        name = str(item.get("name") or "").strip()
        universe = _universe(item)
        images = [str(u) for u in (item.get("images") or []) if u]
        eligibility, reason = _eligibility(item)
        review_status = "pending"
        notes: list[str] = []
        if universe == "Boruto":
            notes.append("Boruto-era character; separated for review.")
            review_status = "pending"
        if _filler_exclusive(item):
            notes.append("Possible filler-exclusive or anime-only debut.")
        species = _species(item)
        if species and species.lower() not in {"human", "none"}:
            notes.append(f"Non-human/special species: {species}.")
        titles = _titles(item)
        source_metadata = {
            "dattebayo_id": raw_id,
            "debut": item.get("debut") or {},
            "classification": _classification(item),
            "species": species,
            "titles": titles,
            "personal": _personal(item),
            "rank": item.get("rank") or {},
            "affiliation": _personal(item).get("affiliation"),
            "clan": _personal(item).get("clan"),
            "collected_at": utc_now(),
        }
        return CandidateCharacter(
            candidate_id=f"dattebayo:{raw_id}",
            name=name,
            universe=universe,
            source=self.name,
            source_url=f"https://naruto.fandom.com/wiki/{_slug(name)}",
            aliases=[],
            image_urls=images,
            images=[CandidateImage(url=u, source=self.name) for u in images],
            debut=item.get("debut") or {},
            classification=_classification(item),
            species=species,
            canonical_eligibility=eligibility,
            eligibility_reason=reason,
            source_metadata=source_metadata,
            review_status=review_status,
            notes=notes,
        )
