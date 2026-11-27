"""Deterministic research helpers for the One Piece content expansion.

The module separates *source inspection* from *evaluation*: it fetches and
normalises One Piece Wiki pages, extracts cited capability sections, and
records only factual material. It never assigns Power, Role Fit, rarity,
scores, approval or publication status.

Large raw-page caches live outside Git. Only derived JSON/report artefacts are
committed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Iterable

import requests

API_URL = "https://onepiece.fandom.com/api.php"
WIKI_BASE = "https://onepiece.fandom.com/wiki/"
USER_AGENT = "KayiArenaContentResearch/1.0 (+https://github.com/ZenkaiRPGBot/Kayi-Arena)"
CACHE_DIR = Path(
    os.environ.get(
        "KAYI_ONEPIECE_CACHE",
        r"C:\Users\2024\AppData\Local\Temp\opencode\onepiece_cache",
    )
)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

UNIVERSE_ID = "one_piece"
CANON_POLICY = "ONE-PIECE-CANON-0.1"
MANGA_CUTOFF_CHAPTER = 1100
FRAMEWORK = "EVAL-FRAMEWORK-1.0"
SCORING_VERSION = "SCORE-1.0"

CAPABILITY_KEYS = [
    "combat_effectiveness",
    "offense",
    "defense_durability",
    "speed_mobility",
    "leadership",
    "tactics",
    "stealth_infiltration_assassination",
    "support_control",
    "medical_healing",
    "significant_achievements",
    "limitations",
    "conditional_abilities",
]

SECTION_EXCLUDE = {
    "overview",
    "references",
    "site navigation",
    "navigation",
    "gallery",
    "trivia",
    "history",
    "personality",
    "appearance",
    "relationships",
    "main series",
    "movies",
    "video games",
    "video game only techniques",
    "other",
    "anime only",
    "anime differences",
    "manga differences",
    "other media",
    "non canon",
    "non-canon",
    "merchandise",
    "soundtrack",
    "reception",
    "notes",
    "external links",
    "see also",
    "quotes",
    "abilities and powers",
}

PATH_EXCLUDE = {
    "appearance",
    "gallery",
    "main series",
    "movies",
    "video games",
    "other",
    "personality",
    "relationships",
    "history",
    "trivia",
    "references",
    "anime differences",
    "manga differences",
    "other media",
}

NON_ABILITY_HEADINGS = {
    "gluttony",
    "artistic skill",
    "lack of orientation",
    "luck",
    "sleepiness",
    "snoring",
    "dancing",
    "singing",
    "cooking",
    "financial expertise",
    "gambling",
}

EQUIPMENT_HEADINGS = {
    "weapons",
    "current swords",
    "former swords",
    "situational weapons",
    "equipment",
    "weapon",
    "swords",
}

GENERIC_ABILITY_NAMES = {
    "techniques",
    "other techniques",
    "abilities",
    "other capabilities",
    "fighting style",
}

MEDICAL_MARKERS = (
    "medical",
    "doctor",
    "heal",
    "healing",
    "cure",
    "surgery",
    "surgeon",
    "medicine",
    "treatment",
    "first aid",
    "transfusion",
    "phage",
)

STEALTH_MARKERS = (
    "stealth",
    "assassin",
    "espionage",
    "infiltration",
    "infiltrat",
    "spy",
    "spying",
    "covert",
    "silent",
    "sneak",
    "pickpocket",
    "thief",
    "steal",
    "disguise",
    "escape artist",
)

SPEED_MARKERS = (
    "speed",
    "agility",
    "mobility",
    "soru",
    "teleport",
    "flight",
    "fly",
    "dash",
    "movement",
    "shave",
    "geppo",
    "reflex",
    "escape artist",
    "physical abilities",
)

DEFENSE_MARKERS = (
    "durability",
    "durable",
    "endurance",
    "defense",
    "defence",
    "resilien",
    "tough",
    "armament haki",
    "shield",
    "barrier",
    "withstand",
    "tank",
    "regeneration",
    "stamina",
    "physical abilities",
)

LEADERSHIP_MARKERS = (
    "leadership",
    "captain",
    "command",
    "commander",
    "charisma",
    "inspire",
    "crew",
    "fleet",
    "authority",
    "loyalty",
    "negotiation",
    "supreme king haki",
    "conqueror",
)

TACTICS_MARKERS = (
    "tactic",
    "strateg",
    "intelligence",
    "intelligent",
    "plan",
    "analysis",
    "analy",
    "predict",
    "observation haki",
    "kenbunshoku",
    "judgment",
    "judgement",
    "escape artist",
    "spying",
    "weather",
)

SUPPORT_MARKERS = (
    "support",
    "control",
    "restrain",
    "bind",
    "trap",
    "barrier",
    "weather",
    "navigat",
    "protect",
    "rescue",
    "transport",
    "communication",
    "information",
    "heal",
    "medical",
    "soul",
    "shadow",
    "ice",
    "gravity",
    "time",
    "space",
    "illusion",
    "poison",
    "science",
    "engineering",
    "archaeology",
    "poneglyph",
    "voice of all things",
    "zoolingualism",
    "sailing",
    "clima tact",
    "weather",
)

OFFENSE_MARKERS = (
    "attack",
    "offens",
    "strike",
    "slash",
    "punch",
    "kick",
    "blast",
    "flame",
    "fire",
    "lightning",
    "sword",
    "swordsman",
    "combat",
    "fight",
    "damage",
    "destroy",
    "cut",
    "shoot",
    "cannon",
    "armament haki",
    "supreme king haki",
    "conqueror",
    "devil fruit",
    "gear",
    "strength",
    "technique",
    "karate",
    "rokushiki",
    "clima tact",
    "rumble ball",
    "awakening",
    "weapon",
    "fish man karate",
    "electro",
    "diable jambe",
    "raid suit",
    "weather",
    "physical abilities",
)

COMBAT_TEXT_MARKERS = (
    "attack",
    "fight",
    "defeat",
    "strike",
    "slash",
    "punch",
    "kick",
    "blast",
    "sword",
    "haki",
    "devil fruit",
    "damage",
    "combat",
    "battle",
)

LIMITATION_MARKERS = (
    "weakness",
    "limitation",
    "drawback",
    "vulnerab",
    "cannot",
    "can't",
    "unable to",
    "fatal flaw",
    "side effect",
    "side-effect",
    "time limit",
    "only lasts",
    "only works",
    "requires",
    "must be",
    "at the cost",
)

UNCERTAIN_ABILITY_MARKERS = (
    "it is unclear whether",
    "it is unknown whether",
    "it is unclear if",
    "it is unknown if",
    "whether or not he",
    "whether or not she",
    "not confirmed",
    "unconfirmed",
    "has not been confirmed",
)

CONDITIONAL_MARKERS = (
    "only when",
    "requires",
    "required",
    "condition",
    "temporary",
    "time limit",
    "as long as",
    "if he",
    "if she",
    "while using",
    "drawback",
    "side effect",
    "stamina",
)

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})


def slugify(value: str) -> str:
    text = value.lower().replace("'", "")
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text


def chart_id(name: str) -> str:
    return f"one_piece_{slugify(name)}"


def wiki_url(page_title: str) -> str:
    return WIKI_BASE + page_title.replace(" ", "_")


def _cache_path(key: str) -> Path:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
    return CACHE_DIR / f"{digest}.json"


def api_get(params: dict[str, Any]) -> dict[str, Any]:
    payload = dict(params)
    payload.setdefault("format", "json")
    delay = 0.15
    for attempt in range(4):
        try:
            response = SESSION.get(API_URL, params=payload, timeout=45)
            if response.status_code == 429:
                time.sleep(2 + attempt * 2)
                continue
            response.raise_for_status()
            return response.json()
        except Exception:
            if attempt == 3:
                raise
            time.sleep(1 + attempt * 2)
    raise RuntimeError("unreachable")


def fetch_page(title: str) -> dict[str, Any]:
    """Fetch a page's wikitext, with a local cache."""
    cache = _cache_path(f"page:{title}")
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    data = api_get(
        {
            "action": "parse",
            "page": title,
            "prop": "wikitext",
            "redirects": 1,
            "formatversion": 2,
        }
    )
    if "error" in data:
        result = {
            "error": data["error"].get("info", "missing page"),
            "requested_title": title,
        }
    else:
        parse = data["parse"]
        result = {
            "requested_title": title,
            "title": parse.get("title", title),
            "pageid": parse.get("pageid"),
            "revid": parse.get("revid"),
            "wikitext": parse.get("wikitext", ""),
        }
    cache.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return result


def fetch_abilities_page(title: str) -> dict[str, Any]:
    """Return the abilities subpage when it exists, else the main page."""
    subpage = fetch_page(f"{title}/Abilities and Powers")
    if not subpage.get("error"):
        subpage["page_kind"] = "abilities_subpage"
        return subpage
    main = fetch_page(title)
    main["page_kind"] = "main_page"
    return main


def fetch_pageimages(
    titles: Iterable[str], *, thumb_size: int = 1000
) -> dict[str, dict[str, Any]]:
    title_list = list(dict.fromkeys(titles))
    result: dict[str, dict[str, Any]] = {}
    for start in range(0, len(title_list), 40):
        chunk = title_list[start : start + 40]
        data = api_get(
            {
                "action": "query",
                "titles": "|".join(chunk),
                "prop": "pageimages",
                "piprop": "original|thumbnail",
                "pithumbsize": thumb_size,
                "redirects": 1,
            }
        )
        pages = (data.get("query") or {}).get("pages") or {}
        for page in pages.values():
            if page.get("missing"):
                continue
            title = page.get("title", "")
            result[title] = {
                "title": title,
                "pageid": page.get("pageid"),
                "original": page.get("original"),
                "thumbnail": page.get("thumbnail"),
            }
    return result


def fetch_categories(titles: Iterable[str]) -> dict[str, list[str]]:
    """Return page categories keyed by resolved page title."""
    title_list = list(dict.fromkeys(titles))
    result: dict[str, list[str]] = {}
    for start in range(0, len(title_list), 40):
        chunk = title_list[start : start + 40]
        params: dict[str, Any] = {
            "action": "query",
            "titles": "|".join(chunk),
            "prop": "categories",
            "cllimit": "max",
            "redirects": 1,
        }
        while True:
            data = api_get(params)
            pages = (data.get("query") or {}).get("pages") or {}
            if isinstance(pages, dict):
                page_iter = pages.values()
            else:
                page_iter = pages
            for page in page_iter:
                if page.get("missing"):
                    continue
                title = page.get("title", "")
                result.setdefault(title, [])
                for category in page.get("categories") or []:
                    name = str(category.get("title") or "").removeprefix("Category:")
                    if name:
                        result[title].append(name)
            cont = data.get("continue")
            if not cont:
                break
            params.update(cont)
    return result


def _qref_chapters(raw: str) -> list[int]:
    chapters: set[int] = set()
    for match in re.finditer(r"\{\{\s*[Qq]ref\s*\|([^{}]*)\}\}", raw):
        args = match.group(1)
        for key in ("chap", "chapter"):
            hit = re.search(rf"(?:^|\|)\s*{key}\s*=\s*(\d+)", args)
            if hit:
                chapters.add(int(hit.group(1)))
    for match in re.finditer(r"chapter\s*(\d+)", raw, flags=re.I):
        chapters.add(int(match.group(1)))
    return sorted(chapters)


def canonical_refs(chapters: Iterable[int]) -> list[str]:
    return [
        f"One Piece chapter {number}"
        for number in sorted(set(chapters))
        if number <= MANGA_CUTOFF_CHAPTER
    ]


def _replace_qrefs(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        args = match.group(1)
        hit = re.search(r"(?:^|\|)\s*(?:chap|chapter)\s*=\s*(\d+)", args)
        return f" [Chapter {hit.group(1)}]" if hit else ""

    return re.sub(r"\{\{\s*[Qq]ref\s*\|([^{}]*)\}\}", repl, text)


def _replace_simple_templates(text: str) -> str:
    # Preserve the display text of common link/name templates before the
    # generic template stripper runs.
    def nihongo(match: re.Match[str]) -> str:
        parts = [part.strip() for part in match.group(1).split("|")]
        return parts[0] if parts else ""

    def wlink(match: re.Match[str]) -> str:
        parts = [part.strip() for part in match.group(1).split("|")]
        return parts[-1] if parts else ""

    text = re.sub(r"\{\{\s*Nihongo\s*\|([^{}]*)\}\}", nihongo, text, flags=re.I)
    text = re.sub(r"\{\{\s*W\s*\|([^{}]*)\}\}", wlink, text, flags=re.I)
    text = re.sub(r"\{\{\s*Ruby\s*\|([^{}]*)\}\}", nihongo, text, flags=re.I)
    text = re.sub(r"\{\{\s*B\s*\}\}", "", text, flags=re.I)
    return text


def _strip_templates(text: str) -> str:
    for _ in range(10):
        updated = re.sub(r"\{\{[^{}]*\}\}", "", text)
        if updated == text:
            break
        text = updated
    return text


def wikitext_to_text(raw: str) -> str:
    """Convert the prose parts of wikitext to readable text.

    Citations are preserved as ``[Chapter N]`` so derived records retain
    traceable manga references. Tables, galleries, files and templates are
    removed rather than interpreted.
    """
    text = re.sub(r"<!--.*?-->", "", raw, flags=re.S)
    text = _replace_qrefs(text)
    text = _replace_simple_templates(text)
    text = re.sub(r"<ref[^>]*/>", "", text, flags=re.I)
    text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.I | re.S)
    text = re.sub(r"<gallery.*?</gallery>", "", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\[\[(?:File|Image):[^\]]+\]\]", "", text, flags=re.I)
    text = re.sub(r"\[\[Category:[^\]]+\]\]", "", text, flags=re.I)
    text = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    text = _strip_templates(text)
    text = re.sub(r"'''?", "", text)

    lines: list[str] = []
    in_table = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("{|"):
            in_table = True
            continue
        if in_table:
            if stripped.startswith("|}"):
                in_table = False
            continue
        if stripped.startswith(("|-", "|", "!", "[[Category:", "Category:")):
            continue
        lines.append(line)
    text = "\n".join(lines)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _paragraphs(text: str) -> list[str]:
    paragraphs: list[str] = []
    for block in re.split(r"\n\s*\n", text):
        block = " ".join(block.split())
        if len(block) >= 80:
            paragraphs.append(block)
    return paragraphs


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])", text)
    return [part.strip() for part in parts if part.strip()]


def summarize(text: str, *, sentence_limit: int = 3, char_limit: int = 900) -> str:
    text = " ".join(text.split())
    sentences = _sentences(text)
    result = " ".join(sentences[:sentence_limit]) if sentences else text
    if len(result) > char_limit:
        result = result[: char_limit - 1].rsplit(" ", 1)[0] + "…"
    return result.strip()


def _norm_heading(value: str) -> str:
    value = value.replace("–", "-").replace("—", "-").replace("’", "'")
    value = re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
    return value


def parse_sections(raw: str) -> list[dict[str, Any]]:
    lines = raw.splitlines()
    heading_re = re.compile(r"^(={2,6})\s*(.+?)\s*\1\s*$")
    headings: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines):
        match = heading_re.match(line.strip())
        if match:
            headings.append((index, len(match.group(1)), match.group(2).strip()))
    sections: list[dict[str, Any]] = []
    parent_by_level: dict[int, str] = {}
    for position, (index, level, heading) in enumerate(headings):
        end = headings[position + 1][0] if position + 1 < len(headings) else len(lines)
        body = "\n".join(lines[index + 1 : end])
        parent_by_level = {
            key: value for key, value in parent_by_level.items() if key < level
        }
        parent_by_level[level] = heading
        path = [parent_by_level[key] for key in sorted(parent_by_level) if key <= level]
        sections.append(
            {
                "heading": heading,
                "level": level,
                "path": path,
                "raw": body,
                "text": wikitext_to_text(body),
                "chapters": _qref_chapters(body),
                "has_children": bool(
                    position + 1 < len(headings) and headings[position + 1][1] > level
                ),
            }
        )
    return sections


def _section_excluded(section: dict[str, Any]) -> bool:
    for part in section["path"]:
        normalized = _norm_heading(part)
        if normalized in PATH_EXCLUDE:
            return True
        if any(
            marker in normalized
            for marker in (
                "video game",
                "non canon",
                "anime only",
                "anime differences",
                "manga differences",
                "other media",
                "movies",
                "merchandise",
                "site navigation",
                "references",
                "gallery",
                "trivia",
            )
        ):
            return True
    heading = _norm_heading(section["heading"])
    if heading in SECTION_EXCLUDE:
        return True
    if any(
        marker in heading
        for marker in (
            "video game",
            "non canon",
            "anime only",
            "anime differences",
            "manga differences",
            "other media",
            "movies",
            "merchandise",
            "site navigation",
            "references",
            "gallery",
            "trivia",
            "external links",
            "see also",
            "quotes",
            "soundtrack",
            "reception",
        )
    ):
        return True
    return False


def _ability_category(name: str, path: list[str], description: str) -> list[str]:
    heading = _norm_heading(" ".join([*path, name]))
    text = description.lower()
    categories: list[str] = []

    def add(category: str) -> None:
        if category not in categories:
            categories.append(category)

    if any(marker in heading for marker in MEDICAL_MARKERS) or any(
        marker in text for marker in ("medical expertise", "surgery", "healing technique")
    ):
        add("medical_healing")
    if any(marker in heading for marker in STEALTH_MARKERS):
        add("stealth_infiltration_assassination")
    if any(marker in heading for marker in SPEED_MARKERS):
        add("speed_mobility")
    if any(marker in heading for marker in DEFENSE_MARKERS):
        add("defense_durability")
    if any(marker in heading for marker in LEADERSHIP_MARKERS):
        add("leadership")
    if any(marker in heading for marker in TACTICS_MARKERS):
        add("tactics")
    if any(marker in heading for marker in SUPPORT_MARKERS):
        add("support_control")
    if any(marker in heading for marker in OFFENSE_MARKERS):
        add("offense")
    if not categories:
        if any(marker in text for marker in COMBAT_TEXT_MARKERS):
            add("offense")
        else:
            add("other")
    return categories


def _is_equipment_heading(heading: str) -> bool:
    normalized = _norm_heading(heading)
    if normalized in EQUIPMENT_HEADINGS:
        return True
    return normalized.startswith(
        ("current sword", "former sword", "situational weapon", "weapon ")
    )


def _ability_name(section: dict[str, Any]) -> str:
    heading = section["heading"].strip()
    if _norm_heading(heading) in GENERIC_ABILITY_NAMES and len(section["path"]) > 1:
        return f"{section['path'][-2]} — {heading}"
    return heading


def extract_lead(page: dict[str, Any]) -> str:
    raw = page.get("wikitext", "")
    lead_raw = re.split(r"\n==", raw, maxsplit=1)[0]
    text = wikitext_to_text(lead_raw)
    paragraphs = _paragraphs(text)
    return summarize(" ".join(paragraphs[:2]), sentence_limit=3, char_limit=900)


def extract_aliases(page: dict[str, Any], name: str) -> list[str]:
    raw = page.get("wikitext", "")[:4000]
    aliases: list[str] = []
    # Quoted epithets are the cleanest form, e.g. '''"Pirate Hunter" Zoro'''.
    for match in re.finditer(r"'''\"([^\"]{2,80})\"", raw):
        aliases.append(match.group(1).strip())
    for match in re.finditer(r"'''([^']{2,90})'''", raw):
        value = match.group(1).strip().strip('"').strip()
        value = re.sub(r"^\[\[[^\]]+\|", "", value).strip("]")
        if '"' in value:
            value = value.split('"', 1)[0].strip()
        if value and value.lower() != name.lower() and not value.lower().startswith("the "):
            aliases.append(value)
    cleaned: list[str] = []
    for alias in aliases:
        alias = re.sub(r"\s+", " ", alias).strip(" ,;:")
        if not alias or alias.lower() == name.lower() or alias in cleaned:
            continue
        if re.search(r"\b(Point|Form|Mode|Gear \d+|Awakening)\b", alias, flags=re.I):
            continue
        cleaned.append(alias)
    return cleaned[:8]


def extract_equipment(page: dict[str, Any]) -> list[dict[str, Any]]:
    raw = page.get("wikitext", "")
    sections = parse_sections(raw)
    equipment: list[dict[str, Any]] = []
    seen: set[str] = set()
    for section in sections:
        if _section_excluded(section):
            continue
        if not _is_equipment_heading(section["heading"]):
            continue
        paragraphs = _paragraphs(section["text"])
        if not paragraphs:
            continue
        description = summarize(" ".join(paragraphs[:2]))
        if len(description) < 60:
            continue
        key = f"{section['heading']}|{description[:80]}"
        if key in seen:
            continue
        seen.add(key)
        equipment.append(
            {
                "name": section["heading"].strip(),
                "description": description,
                "canonical_refs": canonical_refs(section["chapters"]),
                "source_section": " / ".join(section["path"]),
            }
        )
    return equipment[:8]


def extract_abilities(page: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    raw = page.get("wikitext", "")
    sections = parse_sections(raw)
    overview = ""
    for section in sections:
        if _norm_heading(section["heading"]) == "overview":
            paragraphs = _paragraphs(section["text"])
            if paragraphs:
                overview = summarize(" ".join(paragraphs[:2]))
                break

    abilities: list[dict[str, Any]] = []
    seen: set[str] = set()
    for section in sections:
        if _section_excluded(section):
            continue
        heading = _norm_heading(section["heading"])
        if heading in NON_ABILITY_HEADINGS:
            continue
        if _is_equipment_heading(section["heading"]):
            continue
        if heading == "abilities and powers":
            continue
        if heading == "overview":
            continue
        if section["has_children"] and len(section["text"]) < 160:
            continue
        paragraphs = _paragraphs(section["text"])
        if not paragraphs:
            continue
        description = summarize(" ".join(paragraphs[:2]))
        if len(description) < 120:
            continue
        lower_description = description.lower()
        if any(marker in lower_description for marker in UNCERTAIN_ABILITY_MARKERS):
            continue
        name = _ability_name(section)
        categories = _ability_category(name, section["path"], description)
        if categories == ["other"]:
            continue
        key = f"{_norm_heading(name)}|{description[:80]}"
        if key in seen:
            continue
        seen.add(key)
        abilities.append(
            {
                "name": name,
                "description": description,
                "categories": categories,
                "canonical_refs": canonical_refs(section["chapters"]),
                "source_section": " / ".join(section["path"]),
                "evidence": (
                    f"Deterministic extract from section '{' / '.join(section['path'])}' "
                    "of the inspected ability profile."
                ),
                "_chapters": section["chapters"],
            }
        )

    # Prefer sections with explicit citations, then richer descriptions.
    abilities.sort(
        key=lambda item: (bool(item["canonical_refs"]), len(item["description"])),
        reverse=True,
    )
    selected = abilities[:14]
    selected.sort(key=lambda item: item["source_section"])
    return selected, overview


def _find_sentences(
    sections: list[dict[str, Any]], markers: tuple[str, ...], *, limit: int = 2
) -> str:
    hits: list[str] = []
    for section in sections:
        if _section_excluded(section):
            continue
        for sentence in _sentences(section["text"]):
            lower = sentence.lower()
            if any(marker in lower for marker in markers):
                cleaned = " ".join(sentence.split())
                if len(cleaned) >= 50:
                    hits.append(cleaned)
            if len(hits) >= limit:
                break
        if len(hits) >= limit:
            break
    if not hits:
        return ""
    return summarize(" ".join(hits), sentence_limit=2, char_limit=700)


def extract_limitations(page: dict[str, Any], character_name: str = "") -> str:
    sections = parse_sections(page.get("wikitext", ""))
    explicit: list[str] = []
    for section in sections:
        if _section_excluded(section):
            continue
        heading = _norm_heading(section["heading"])
        if any(marker in heading for marker in ("weakness", "limitation", "drawback")):
            paragraphs = _paragraphs(section["text"])
            if paragraphs:
                explicit.append(summarize(" ".join(paragraphs[:2])))
    if explicit:
        return summarize(" ".join(explicit), sentence_limit=3, char_limit=800)

    # A Devil Fruit's universal swimming weakness is the one non-section
    # limitation that can be attributed safely when the inspected text states it.
    full_text = wikitext_to_text(page.get("wikitext", ""))
    name = character_name.lower()
    for sentence in _sentences(full_text):
        lower = sentence.lower()
        if any(
            phrase in lower
            for phrase in (
                "cannot swim",
                "unable to swim",
                "weakness to water",
                "sea prism",
                "sea stone",
            )
        ) and (not name or name in lower or "the user" in lower):
            return summarize(sentence, sentence_limit=1, char_limit=500)
    return "unknown: no explicit limitation recorded in the inspected ability profile."


def extract_conditional(page: dict[str, Any], abilities: list[dict[str, Any]]) -> str:
    pieces: list[str] = []
    specific_markers = (
        "gear",
        "rumble",
        "awakening",
        "mode",
        "form",
        "transformation",
    )
    transformations = [
        ability
        for ability in abilities
        if any(marker in _norm_heading(ability["name"]) for marker in specific_markers)
    ]
    if not transformations:
        transformations = [
            ability
            for ability in abilities
            if "devil fruit" in _norm_heading(ability["name"])
        ]
    for ability in transformations[:2]:
        pieces.append(f"{ability['name']}: {ability['description']}")
    if not pieces:
        return (
            "unknown: no conditional ability or transformation was clearly "
            "documented in the inspected ability profile."
        )
    return summarize(" ".join(pieces), sentence_limit=4, char_limit=900)


def _best_ability(
    abilities: list[dict[str, Any]], category: str, preferred: tuple[str, ...] = ()
) -> dict[str, Any] | None:
    candidates = [
        ability
        for ability in abilities
        if category in (ability.get("categories") or [])
        and ability.get("name", "").lower() not in NON_ABILITY_HEADINGS
    ]
    if not candidates:
        return None

    def score(ability: dict[str, Any]) -> tuple[int, int, int]:
        name = ability.get("name", "").lower()
        preference = sum(1 for marker in preferred if marker in name)
        return (
            preference,
            len(ability.get("canonical_refs") or []),
            len(ability.get("description") or ""),
        )

    return max(candidates, key=score)


def build_capability_summary(
    abilities: list[dict[str, Any]], overview: str, all_text: str, character_name: str = ""
) -> dict[str, str]:
    summary: dict[str, str] = {}
    summary["combat_effectiveness"] = overview or "unknown: no overview recorded."
    summary["significant_achievements"] = overview or "unknown: no overview recorded."

    preferred = {
        "offense": (
            "gear",
            "swordsmanship",
            "devil fruit",
            "strength",
            "fighting style",
            "fish man karate",
            "rokushiki",
            "clima tact",
            "rumble ball",
            "awakening",
            "haki",
        ),
        "defense_durability": (
            "durability",
            "endurance",
            "armament haki",
            "devil fruit",
            "physical",
        ),
        "speed_mobility": ("speed", "agility", "soru", "geppo", "physical"),
        "leadership": ("charisma", "leadership", "command"),
        "tactics": ("tactical", "intelligence", "strategy", "observation haki"),
        "stealth_infiltration_assassination": (
            "spying",
            "espionage",
            "stealth",
            "thief",
            "pickpocket",
        ),
        "support_control": (
            "medical",
            "weather",
            "navigation",
            "support",
            "control",
            "zoolingualism",
            "voice",
        ),
        "medical_healing": ("medical", "doctor", "healing"),
    }
    for key, markers in preferred.items():
        ability = _best_ability(abilities, key, markers)
        summary[key] = (
            ability["description"]
            if ability
            else f"unknown: no demonstrated {key.replace('_', ' ')} in the inspected source."
        )

    summary["limitations"] = (
        "unknown: no explicit limitation recorded in the inspected ability profile."
    )
    summary["conditional_abilities"] = extract_conditional(
        {"wikitext": all_text}, abilities
    )
    return summary


def species_from_lead(lead: str) -> str:
    lower = lead.lower()
    markers = (
        (r"\breindeer\b", "Reindeer"),
        (r"\bfish[- ]man\b", "Fish-man"),
        (r"\bfishman\b", "Fish-man"),
        (r"\bmink\b", "Mink"),
        (r"\blunarian\b", "Lunarian"),
        (r"\boni\b", "Oni"),
        (r"\bskeleton\b", "Skeleton"),
        (r"\bcyborg\b", "Cyborg"),
        (r"\bgiant\b", "Giant"),
        (r"\bdwarf\b", "Dwarf"),
        (r"\btontatta\b", "Dwarf"),
        (r"\bmerfolk\b", "Merfolk"),
        (r"\bhuman\b", "Human"),
    )
    for pattern, value in markers:
        if re.search(pattern, lower):
            return value
    return ""


def species_from_text(text: str) -> str:
    lower = text.lower()
    markers = (
        (r"\breindeer\b", "Reindeer"),
        (r"\bfish[- ]man\b", "Fish-man"),
        (r"\bfishman\b", "Fish-man"),
        (r"\bmink\b", "Mink"),
        (r"\blunarian\b", "Lunarian"),
        (r"\boni\b", "Oni"),
        (r"\bskeleton\b", "Skeleton"),
        (r"\bcyborg\b", "Cyborg"),
        (r"\bgiant\b", "Giant"),
        (r"\bdwarf\b", "Dwarf"),
        (r"\btontatta\b", "Dwarf"),
        (r"\bmerfolk\b", "Merfolk"),
        (r"\bhuman\b", "Human"),
    )
    for pattern, value in markers:
        if re.search(pattern, lower):
            return value
    return ""


def species_from_categories(categories: Iterable[str]) -> str:
    mapping = {
        "Fish-Men": "Fish-man",
        "Merfolk": "Merfolk",
        "Humans": "Human",
        "Oni": "Oni",
        "Lunarians": "Lunarian",
        "Cyborgs": "Cyborg",
        "Reindeer": "Reindeer",
        "Skeletons": "Skeleton",
        "Minks": "Mink",
        "Giants": "Giant",
        "Dwarves": "Dwarf",
        "Tontatta": "Dwarf",
        "Artificial Humans": "Artificial human",
        "Clones": "Clone",
        "Zombies": "Zombie",
    }
    found: list[str] = []
    for category in categories:
        for key, value in mapping.items():
            if category == key or category.endswith(f" {key}"):
                if value not in found:
                    found.append(value)
    return ", ".join(found) if found else "unknown"


def first_cited_chapter(page: dict[str, Any]) -> int | None:
    chapters = _qref_chapters(page.get("wikitext", "")[:5000])
    return chapters[0] if chapters else None


def build_research_record(
    *,
    name: str,
    canonical_name: str,
    main_page: dict[str, Any],
    abilities_page: dict[str, Any],
    categories: list[str],
    aliases: list[str],
    faction: str,
    species: str,
    era: str,
) -> dict[str, Any]:
    abilities, overview_from_abilities = extract_abilities(abilities_page)
    lead = extract_lead(main_page)
    overview = lead or overview_from_abilities
    if not species or species == "unknown":
        species = species_from_lead(lead) or species_from_text(
            wikitext_to_text(main_page.get("wikitext", ""))[:30000]
        ) or "unknown"
    all_text = wikitext_to_text(abilities_page.get("wikitext", ""))
    summary = build_capability_summary(abilities, overview, all_text, name)
    summary["limitations"] = extract_limitations(abilities_page, name)
    equipment = extract_equipment(abilities_page)

    substantive = [
        ability
        for ability in abilities
        if len(ability.get("description") or "") >= 120
        and ability.get("name", "").lower() not in GENERIC_ABILITY_NAMES
    ]
    cited = [ability for ability in substantive if ability.get("canonical_refs")]
    if len(substantive) >= 2 and cited:
        status = "RESEARCH_READY"
        gate_reason = (
            "At least two substantive demonstrated abilities were extracted, and "
            "at least one carries a chapter citation from the inspected profile."
        )
    elif substantive:
        status = "PARTIAL_RESEARCH"
        gate_reason = (
            "Substantive capability material was found, but the record does not "
            "meet the two-ability plus cited-evidence threshold."
        )
    else:
        status = "INSUFFICIENT_EVIDENCE"
        gate_reason = (
            "The inspected profile did not yield a substantive demonstrated "
            "ability with a traceable description."
        )

    chapters = sorted(
        {
            number
            for ability in abilities
            for number in ability.get("_chapters", [])
            if number <= MANGA_CUTOFF_CHAPTER
        }
    )
    cleaned_abilities: list[dict[str, Any]] = []
    for ability in abilities:
        cleaned = {key: value for key, value in ability.items() if not key.startswith("_")}
        cleaned["canonical_refs"] = canonical_refs(
            [int(re.search(r"\d+", ref).group()) for ref in cleaned.get("canonical_refs", [])]
        )
        cleaned_abilities.append(cleaned)

    evidence_url = wiki_url(abilities_page.get("title", canonical_name))
    main_url = wiki_url(main_page.get("title", canonical_name))
    supporting_evidence = [
        {
            "source": "One Piece Wiki (Fandom) ability profile",
            "url": evidence_url,
            "verification_level": "inspected_secondary",
            "page_kind": abilities_page.get("page_kind", "unknown"),
            "source_revision": abilities_page.get("revid"),
            "canonical_refs": canonical_refs(chapters),
            "notes": (
                "Profile text was fetched through the MediaWiki API and converted "
                "deterministically; primary manga chapters were not opened."
            ),
        }
    ]
    if main_url != evidence_url:
        supporting_evidence.append(
            {
                "source": "One Piece Wiki (Fandom) identity page",
                "url": main_url,
                "verification_level": "inspected_secondary",
                "source_revision": main_page.get("revid"),
                "canonical_refs": [],
                "notes": (
                    "Identity, lead summary and infobox image source; ability "
                    "evidence is taken from the linked ability profile above."
                ),
            }
        )

    first_chapter = first_cited_chapter(main_page)
    return {
        "candidate_id": chart_id(canonical_name),
        "name": name,
        "canonical_name": canonical_name,
        "aliases": aliases,
        "species": species,
        "faction": faction,
        "era": era,
        "source": "onepiece_fandom",
        "source_url": main_url,
        "ability_profile_url": evidence_url,
        "canonical_policy": CANON_POLICY,
        "manga_cutoff_chapter": MANGA_CUTOFF_CHAPTER,
        "canonical_version": (
            f"Manga canon through Chapter {MANGA_CUTOFF_CHAPTER}; sustainable "
            "demonstrated version documented in the inspected profile."
        ),
        "canonical_version_basis": (
            "The researched state is the character's demonstrated capabilities "
            f"within the manga cutoff of Chapter {MANGA_CUTOFF_CHAPTER}. "
            "Sections and chapter leads were extracted from the inspected One "
            "Piece Wiki profile; primary manga was not directly opened."
        ),
        "debut": {
            "first_cited_chapter_in_lead": first_chapter,
            "basis": "First chapter citation in the inspected main-page lead.",
            "verified_against_primary_manga": False,
        },
        "status": status,
        "research_gate": status,
        "research_status": status,
        "capability_summary": summary,
        "demonstrated_abilities": cleaned_abilities,
        "weapons_and_equipment": equipment,
        "supporting_evidence": supporting_evidence,
        "source_categories": sorted(set(categories)),
        "gate_reason": gate_reason,
        "continuity_note": (
            "No separate continuity split identified within the manga cutoff."
            if status != "INSUFFICIENT_EVIDENCE"
            else "Continuity review is incomplete because ability evidence was insufficient."
        ),
        "evidence_check": {
            "verification_level": "inspected_secondary",
            "canonical_refs_extracted_from_page_text": True,
            "primary_sources_directly_inspected": False,
            "manga_cutoff_chapter": MANGA_CUTOFF_CHAPTER,
            "ability_sections_considered": len(abilities),
            "chapter_refs_retained": len(chapters),
            "source_categories_considered": len(categories),
            "unsupported_refs_dropped": [],
        },
        "source_metadata": {
            "fandom_pageid": main_page.get("pageid"),
            "fandom_revision": main_page.get("revid"),
            "ability_profile_pageid": abilities_page.get("pageid"),
            "ability_profile_revision": abilities_page.get("revid"),
            "categories": sorted(set(categories)),
        },
        "notes": [
            "Stage 01 One Piece research. No Power, Role Fit, rarity, score, "
            "approval or publication status is allocated.",
            "Catalogue metadata, bounty and rank are context only; ratings must "
            "rest on demonstrated abilities above.",
            "Sources are inspected secondary profiles; primary manga chapters "
            "were not directly opened.",
        ],
    }
