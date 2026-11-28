"""Production 1900x600 esports Player Card renderer for Kayi Arena Profile 2.0.

Preserves the approved standalone prototype composition, neon accents, gradient
typography, and static artwork while adding cross-platform font resolution,
Unicode/emoji fallback, EXIF-safe avatar cropping, bounded caching, and
off-event-loop async rendering.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import unicodedata
from collections import OrderedDict
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from aiogram import Bot
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

logger = logging.getLogger(__name__)

CARD_WIDTH = 1900
CARD_HEIGHT = 600
RENDERER_VERSION = "2.0.0"

_ASSETS_ROOT = Path(__file__).resolve().parent / "assets"
_PROFILE_ASSETS = _ASSETS_ROOT / "profile"
_FONT_ASSETS = _ASSETS_ROOT / "fonts"

CYAN = (40, 235, 255)
PINK = (255, 51, 187)
WHITE = (243, 251, 255)

_PRIMARY_FONT_CANDIDATES = (
    _FONT_ASSETS / "InterDisplay-BlackItalic.otf",
    Path("/usr/share/fonts/opentype/inter/InterDisplay-BlackItalic.otf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf"),
    Path("C:/Windows/Fonts/seguibli.ttf"),
    Path("C:/Windows/Fonts/arialbi.ttf"),
)

_LABEL_FONT_CANDIDATES = (
    _FONT_ASSETS / "InterDisplay-BoldItalic.otf",
    Path("/usr/share/fonts/opentype/inter/InterDisplay-BoldItalic.otf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf"),
    Path("C:/Windows/Fonts/seguisbi.ttf"),
    Path("C:/Windows/Fonts/arialbi.ttf"),
)

_FALLBACK_FONT_CANDIDATES = (
    Path("/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    Path("C:/Windows/Fonts/ARIALUNI.TTF"),
    Path("C:/Windows/Fonts/seguisym.ttf"),
    Path("C:/Windows/Fonts/seguiemj.ttf"),
    Path("C:/Windows/Fonts/arialbd.ttf"),
    Path("C:/Windows/Fonts/tahoma.ttf"),
)

_STATIC_CACHE: dict[str, Any] = {}
_RENDER_SEMAPHORE = asyncio.Semaphore(2)


def _first_existing_font(candidates: tuple[Path, ...]) -> str | None:
    for p in candidates:
        if p.is_file():
            return str(p)
    return None


def resolve_font_paths() -> tuple[str | None, str | None, tuple[str, ...]]:
    primary = _first_existing_font(_PRIMARY_FONT_CANDIDATES)
    label = _first_existing_font(_LABEL_FONT_CANDIDATES) or primary
    fallbacks = tuple(str(p) for p in _FALLBACK_FONT_CANDIDATES if p.is_file())
    return primary, label, fallbacks


def _load_font(path: str | None, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if path:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _normalize_display_text(text: str) -> str:
    """Normalize mathematical bold/italic/sans decorative Unicode so Inter renders them cleanly."""
    out: list[str] = []
    for ch in text:
        cp = ord(ch)
        if 0x1D400 <= cp <= 0x1D7FF:
            out.append(unicodedata.normalize("NFKC", ch))
        else:
            out.append(ch)
    return "".join(out)


def _has_glyph(font: ImageFont.FreeTypeFont | ImageFont.ImageFont, ch: str) -> bool:
    if ch.isspace():
        return True
    try:
        mask = font.getmask(ch)
        return mask.getbbox() is not None
    except Exception:
        return False


def _choose_char_font(
    ch: str,
    primary: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    fallbacks: tuple[ImageFont.FreeTypeFont | ImageFont.ImageFont, ...],
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont | None:
    if ch.isspace():
        return primary
    if _has_glyph(primary, ch):
        return primary
    for fb in fallbacks:
        if _has_glyph(fb, ch):
            return fb
    return None


def _build_runs(
    s: str,
    primary_path: str | None,
    fallback_paths: tuple[str, ...],
    size: int,
) -> tuple[list[tuple[str, ImageFont.FreeTypeFont | ImageFont.ImageFont]], int, int, int]:
    """Split text into font runs with Unicode fallback, stripping unrenderable tofu boxes."""
    primary = _load_font(primary_path, size)
    fallbacks = tuple(_load_font(fp, size) for fp in fallback_paths)
    runs: list[tuple[str, ImageFont.FreeTypeFont | ImageFont.ImageFont]] = []
    for ch in s:
        chosen = _choose_char_font(ch, primary, fallbacks)
        if chosen is None:
            continue
        if runs and runs[-1][1] is chosen:
            runs[-1] = (runs[-1][0] + ch, chosen)
        else:
            runs.append((ch, chosen))
    if not runs:
        runs = [("Player", primary)]

    total_w = 0
    min_top = 0
    max_bottom = size
    first = True
    for seg, f in runs:
        try:
            adv = round(f.getlength(seg))
        except Exception:
            b = f.getbbox(seg)
            adv = (b[2] - b[0]) if b else len(seg) * (size // 2)
        b = f.getbbox(seg) or (0, 0, adv, size)
        if first:
            min_top = b[1]
            max_bottom = b[3]
            first = False
        else:
            min_top = min(min_top, b[1])
            max_bottom = max(max_bottom, b[3])
        total_w += max(adv, b[2] - b[0] if len(runs) == 1 else adv)
    return runs, max(1, total_w), max(1, max_bottom - min_top), min_top


def _fit_text_runs(
    s: str,
    box_w: int,
    box_h: int,
    primary_path: str | None,
    fallback_paths: tuple[str, ...],
    max_size: int,
    min_size: int = 22,
) -> tuple[list[tuple[str, ImageFont.FreeTypeFont | ImageFont.ImageFont]], int, int, int]:
    text_str = _normalize_display_text(str(s)).strip() or "Player"
    size = max_size
    while size >= min_size:
        runs, tw, th, min_top = _build_runs(text_str, primary_path, fallback_paths, size)
        if tw <= box_w - 12 and th <= box_h - 8:
            return runs, tw, th, min_top
        size -= 2

    # Truncate cleanly with ellipsis at min_size if still too wide
    trimmed = text_str
    while len(trimmed) > 1:
        trimmed = trimmed[:-1].rstrip()
        runs, tw, th, min_top = _build_runs(trimmed + "…", primary_path, fallback_paths, min_size)
        if tw <= box_w - 12:
            return runs, tw, th, min_top
    return _build_runs("…", primary_path, fallback_paths, min_size)


def _get_static_layers() -> tuple[Image.Image, Image.Image, Image.Image]:
    cached = _STATIC_CACHE.get("layers")
    if cached is not None:
        return cached
    bg_path = _PROFILE_ASSETS / "background.png"
    em_path = _PROFILE_ASSETS / "emblem.png"
    fr_path = _PROFILE_ASSETS / "avatar_frame.png"
    for p in (bg_path, em_path, fr_path):
        if not p.is_file():
            raise FileNotFoundError(f"Missing required profile card asset: {p}")
    bg = ImageOps.fit(
        Image.open(bg_path).convert("RGBA"),
        (CARD_WIDTH, CARD_HEIGHT),
        Image.Resampling.LANCZOS,
    )
    emblem = Image.open(em_path).convert("RGBA").resize((100, 100), Image.Resampling.LANCZOS)
    frame = Image.open(fr_path).convert("RGBA").resize((420, 420), Image.Resampling.LANCZOS)
    _STATIC_CACHE["layers"] = (bg, emblem, frame)
    return bg, emblem, frame


def _layer() -> Image.Image:
    return Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT))


def _neon_path(
    base: Image.Image,
    points: list[tuple[int, int]],
    color: tuple[int, int, int],
    width: int = 2,
    glow: int = 7,
) -> None:
    l1 = _layer()
    ImageDraw.Draw(l1).line(points, fill=(*color, 200), width=width + 2, joint="curve")
    base.alpha_composite(l1.filter(ImageFilter.GaussianBlur(glow)))
    l2 = _layer()
    ImageDraw.Draw(l2).line(points, fill=(*color, 255), width=width, joint="curve")
    base.alpha_composite(l2)


def _draw_gradient_text(
    base: Image.Image,
    s: str,
    box: tuple[int, int, int, int],
    primary_path: str | None,
    fallback_paths: tuple[str, ...],
    size: int,
    top: tuple[int, int, int] = WHITE,
    bottom: tuple[int, int, int] | None = None,
    glow: tuple[int, int, int] = CYAN,
    align: str = "center",
    min_size: int = 12,
) -> None:
    x, y, w, h = box
    bottom_col = bottom or top
    runs, tw, th, min_top = _fit_text_runs(
        s, w, h, primary_path, fallback_paths, size, min_size=min_size
    )
    pad = 12
    mask = Image.new("L", (tw + 2 * pad, th + 2 * pad))
    md = ImageDraw.Draw(mask)
    cur_x = pad
    for seg, f in runs:
        md.text((cur_x, pad - min_top), seg, font=f, fill=255)
        try:
            cur_x += round(f.getlength(seg))
        except Exception:
            b = f.getbbox(seg)
            cur_x += (b[2] - b[0]) if b else len(seg) * (size // 2)

    px = round(x + (w - tw) / 2 - pad if align == "center" else x - pad + 6)
    py = round(y + (h - th) / 2 - pad)

    shadow = Image.new("RGBA", mask.size, (0, 4, 24, 255))
    shadow.putalpha(mask.filter(ImageFilter.GaussianBlur(2)))
    base.alpha_composite(shadow, (px + 2, py + 3))

    aura = Image.new("RGBA", mask.size, (*glow, 255))
    aura.putalpha(mask.filter(ImageFilter.GaussianBlur(5)).point(lambda a: int(a * 0.8)))
    base.alpha_composite(aura, (px, py))

    grad = Image.new("RGBA", mask.size)
    gd = ImageDraw.Draw(grad)
    for j in range(mask.height):
        t = min(1.0, max(0.0, (j - pad) / max(1, th - 1)))
        col = tuple(round(a + (b - a) * t) for a, b in zip(top, bottom_col))
        gd.line((0, j, mask.width, j), fill=(*col, 255))
    grad.putalpha(mask)
    base.alpha_composite(grad, (px, py))


def _draw_icon(base: Image.Image, kind: str, cx: int, cy: int, color: tuple[int, int, int]) -> None:
    im = Image.new("RGBA", (100, 100))
    d = ImageDraw.Draw(im)
    c = (*color, 255)
    wd = 5

    def ln(pts: list[tuple[int, int]]) -> None:
        d.line(pts, fill=c, width=wd, joint="curve")

    if kind == "trophy":
        ln([(29, 18), (71, 18), (68, 43), (60, 56), (50, 60), (40, 56), (32, 43), (29, 18)])
        ln([(29, 23), (13, 23), (17, 43), (35, 48)])
        ln([(71, 23), (87, 23), (83, 43), (65, 48)])
        ln([(50, 60), (50, 77), (33, 77), (33, 84), (67, 84), (67, 77), (50, 77)])
    elif kind == "swords":
        for s in (-1, 1):
            ln([(50 + s * (px - 50), py) for px, py in [(16, 13), (32, 19), (78, 69), (70, 77), (19, 29), (16, 13)]])
            ln([(50 + s * (px - 50), py) for px, py in [(60, 78), (79, 59)]])
            ln([(50 + s * (px - 50), py) for px, py in [(73, 73), (88, 88)]])
    elif kind == "draw":
        ln([(9, 35), (24, 20), (40, 29), (51, 22), (68, 28), (80, 20), (93, 38), (76, 60), (61, 75), (51, 70), (41, 74), (29, 62), (18, 55), (9, 35)])
        ln([(40, 29), (30, 42), (39, 48), (51, 38), (76, 60)])
        ln([(43, 56), (59, 69)])
        ln([(52, 49), (68, 63)])
    elif kind == "chart":
        for bx, yt in [(15, 65), (37, 49), (59, 32)]:
            d.rectangle((bx, yt, bx + 13, 84), outline=c, width=4)
        ln([(10, 46), (33, 29), (48, 35), (82, 12), (65, 12)])
        ln([(82, 12), (82, 29)])

    resized = im.resize((65, 65), Image.Resampling.LANCZOS)
    base.alpha_composite(resized.filter(ImageFilter.GaussianBlur(3)), (cx - 32, cy - 32))
    base.alpha_composite(resized, (cx - 32, cy - 32))


def _format_card_count(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 100_000:
        return f"{value / 1_000:.1f}K"
    return str(value)


def _prepare_avatar_layer(avatar_bytes: bytes | None, diameter: int = 304) -> Image.Image:
    av: Image.Image | None = None
    if avatar_bytes:
        try:
            opened = Image.open(BytesIO(avatar_bytes))
            transposed = ImageOps.exif_transpose(opened).convert("RGBA")
            av = ImageOps.fit(transposed, (diameter, diameter), Image.Resampling.LANCZOS)
        except Exception:
            av = None

    if av is None:
        av = Image.new("RGBA", (diameter, diameter), (7, 27, 73, 255))
        ad = ImageDraw.Draw(av)
        ad.ellipse((108, 56, 196, 144), fill=(138, 205, 241, 255))
        ad.ellipse((60, 155, 244, 355), fill=(138, 205, 241, 255))

    mask = Image.new("L", (diameter, diameter))
    ImageDraw.Draw(mask).ellipse((0, 0, diameter - 1, diameter - 1), fill=255)
    # Preserve existing alpha channel while clipping cleanly to the circular aperture
    existing_alpha = av.getchannel("A")
    combined_alpha = Image.composite(existing_alpha, Image.new("L", (diameter, diameter), 0), mask)
    av.putalpha(combined_alpha)
    return av


def render_player_card_png(
    *,
    name: str,
    wins: int,
    losses: int,
    draws: int,
    avatar_bytes: bytes | None = None,
) -> bytes:
    """Synchronously render a 1900x600 PNG player card for authoritative Ranked stats."""
    if any(type(v) is not int or v < 0 for v in (wins, losses, draws)):
        raise ValueError("Counts must be nonnegative integers")

    total = wins + losses + draws
    rate = f"{100.0 * wins / total:.1f}%" if total else "—"
    primary_font, label_font, fallback_fonts = resolve_font_paths()
    bg_layer, emblem_layer, frame_layer = _get_static_layers()

    base = bg_layer.copy()
    shade = _layer()
    ImageDraw.Draw(shade).rounded_rectangle((430, 105, 1205, 480), radius=55, fill=(2, 14, 50, 150))
    base.alpha_composite(shade.filter(ImageFilter.GaussianBlur(35)))

    # Brand header
    base.alpha_composite(emblem_layer, (257, 10))
    _neon_path(base, [(371, 26), (371, 91)], CYAN, 2, 4)
    _draw_gradient_text(base, "KAYI", (389, 22, 128, 55), primary_font, fallback_fonts, 43, WHITE, (181, 223, 250), align="left")
    _draw_gradient_text(base, "ARENA", (519, 22, 200, 55), primary_font, fallback_fonts, 43, CYAN, (0, 179, 248), align="left")
    _neon_path(base, [(394, 85), (703, 85), (720, 78)], PINK, 3, 5)

    # Circular avatar + illuminated frame
    frame_size = 420
    fx, fy = 61, 111
    center = (fx + frame_size // 2, fy + frame_size // 2)
    diameter = 304
    av = _prepare_avatar_layer(avatar_bytes, diameter=diameter)
    base.alpha_composite(av, (center[0] - diameter // 2, center[1] - diameter // 2))
    base.alpha_composite(frame_layer, (fx, fy))

    # Identity & battle count strip
    panel = _layer()
    namepoly = [(530, 129), (1217, 129), (1201, 221), (1176, 239), (510, 239), (510, 150)]
    ImageDraw.Draw(panel).polygon(namepoly, fill=(4, 17, 54, 235))
    base.alpha_composite(panel)
    _neon_path(base, [(510, 239), (510, 150), (530, 129), (1217, 129), (1201, 221)], CYAN, 2, 5)
    _neon_path(base, [(510, 239), (1176, 239), (1201, 221)], PINK, 2, 5)

    _draw_gradient_text(
        base, name, (531, 139, 480, 59), primary_font, fallback_fonts, 68, WHITE, (159, 219, 255), align="left", min_size=22
    )
    _draw_gradient_text(
        base, "ARENA PLAYER", (532, 201, 330, 25), label_font, fallback_fonts, 22, (148, 234, 255), align="left"
    )
    _neon_path(base, [(1023, 148), (1023, 220)], (69, 152, 221), 1, 3)
    _draw_gradient_text(
        base, _format_card_count(total), (1037, 139, 151, 59), primary_font, fallback_fonts, 55, WHITE, (159, 219, 255), min_size=18
    )
    _draw_gradient_text(base, "BATTLES", (1037, 200, 151, 26), label_font, fallback_fonts, 23, WHITE)

    # Two-row stat board
    p = _layer()
    poly = [(532, 262), (1194, 262), (1217, 284), (1217, 452), (1195, 474), (532, 474), (510, 452), (510, 284)]
    ImageDraw.Draw(p).polygon(poly, fill=(4, 17, 54, 241))
    base.alpha_composite(p)
    _neon_path(base, poly + [poly[0]], CYAN, 2, 5)
    _neon_path(base, [(1149, 262), (1194, 262), (1217, 284), (1217, 307)], PINK, 5, 6)
    _neon_path(base, [(510, 430), (510, 452), (532, 474), (570, 474)], CYAN, 5, 6)
    _neon_path(base, [(1158, 474), (1195, 474), (1217, 452), (1217, 430)], PINK, 5, 6)
    _neon_path(base, [(521, 368), (1205, 368)], (57, 174, 255), 2, 4)
    _neon_path(base, [(860, 281), (860, 350)], PINK, 2, 4)
    _neon_path(base, [(860, 386), (860, 455)], CYAN, 2, 4)

    stats_rows = [
        (530, 265, "trophy", _format_card_count(wins), "VICTORIES", CYAN),
        (878, 265, "swords", _format_card_count(losses), "DEFEATS", (255, 91, 162)),
        (530, 370, "draw", _format_card_count(draws), "DRAWS", WHITE),
        (878, 370, "chart", rate, "WIN RATE", CYAN),
    ]
    for sx, sy, kind, val, lbl, col in stats_rows:
        _draw_icon(base, kind, sx + 49, sy + 52, col)
        _draw_gradient_text(
            base,
            val,
            (sx + 91, sy + 4, 220, 63),
            primary_font,
            fallback_fonts,
            58,
            col,
            (255, 255, 255) if kind == "draw" else col,
            glow=col,
            min_size=18,
        )
        _draw_gradient_text(
            base,
            lbl,
            (sx + 91, sy + 65, 220, 28),
            label_font,
            fallback_fonts,
            29,
            WHITE,
            glow=(83, 140, 220),
        )

    _draw_gradient_text(
        base,
        "RANKED  •  ALL UNIVERSES",
        (521, 482, 690, 32),
        label_font,
        fallback_fonts,
        19,
        (183, 233, 255),
        glow=(0, 91, 255),
    )

    out = BytesIO()
    base.convert("RGB").save(out, format="PNG")
    return out.getvalue()


@dataclass(slots=True)
class CachedPlayerCard:
    png_bytes: bytes
    telegram_file_id: str | None = None


class PlayerCardCache:
    """Bounded per-player LRU cache invalidated by name, avatar, or Ranked stat changes."""

    def __init__(self, max_entries: int = 64) -> None:
        self._max = max(1, int(max_entries))
        self._entries: OrderedDict[tuple[Any, ...], CachedPlayerCard] = OrderedDict()
        self._avatar_cache: OrderedDict[str, tuple[str, bytes | None]] = OrderedDict()

    @staticmethod
    def _avatar_hash(avatar_bytes: bytes | None) -> str:
        if not avatar_bytes:
            return "none"
        return hashlib.sha256(avatar_bytes).hexdigest()[:16]

    @staticmethod
    def build_key(
        *,
        player_id: str,
        name: str,
        wins: int,
        losses: int,
        draws: int,
        avatar_hash: str,
    ) -> tuple[Any, ...]:
        return (RENDERER_VERSION, player_id, name, wins, losses, draws, avatar_hash)

    def get(self, key: tuple[Any, ...]) -> CachedPlayerCard | None:
        item = self._entries.get(key)
        if item is not None:
            self._entries.move_to_end(key)
        return item

    def put(self, key: tuple[Any, ...], card: CachedPlayerCard) -> None:
        self._entries[key] = card
        self._entries.move_to_end(key)
        while len(self._entries) > self._max:
            self._entries.popitem(last=False)

    def set_file_id(self, key: tuple[Any, ...], file_id: str) -> None:
        item = self._entries.get(key)
        if item is not None and file_id:
            item.telegram_file_id = file_id


async def fetch_telegram_avatar_bytes(
    bot: Bot,
    user_id: str,
    *,
    timeout: float = 3.0,
) -> bytes | None:
    """Fetch the viewed profile owner's Telegram avatar bytes without blocking profile rendering."""
    if not str(user_id).strip().isdigit():
        return None
    uid = int(user_id)

    async def _fetch() -> bytes | None:
        photos = await bot.get_user_profile_photos(user_id=uid, limit=1)
        if not photos or not getattr(photos, "photos", None):
            return None
        sizes = photos.photos[0]
        if not sizes:
            return None
        # Choose a clean mid/high resolution (prefer ~320-640px, fallback to largest)
        chosen = next((s for s in sizes if (getattr(s, "width", 0) or 0) >= 300), sizes[-1])
        file_obj = await bot.get_file(chosen.file_id)
        file_path = getattr(file_obj, "file_path", None)
        if not file_path:
            return None
        buf = BytesIO()
        await bot.download_file(file_path, destination=buf)
        data = buf.getvalue()
        return data if data else None

    try:
        return await asyncio.wait_for(_fetch(), timeout=timeout)
    except asyncio.TimeoutError:
        logger.debug("Timed out fetching Telegram avatar for user %s", user_id)
        return None
    except Exception as exc:
        logger.debug("Could not fetch Telegram avatar for user %s: %s", user_id, type(exc).__name__)
        return None


async def render_player_card_async(
    *,
    cache: PlayerCardCache,
    player_id: str,
    name: str,
    wins: int,
    losses: int,
    draws: int,
    avatar_bytes: bytes | None,
) -> tuple[tuple[Any, ...], CachedPlayerCard]:
    """Render (or return cached) Player Card off the asyncio event loop."""
    av_hash = cache._avatar_hash(avatar_bytes)
    key = cache.build_key(
        player_id=player_id,
        name=name,
        wins=wins,
        losses=losses,
        draws=draws,
        avatar_hash=av_hash,
    )
    cached = cache.get(key)
    if cached is not None:
        return key, cached

    async with _RENDER_SEMAPHORE:
        cached = cache.get(key)
        if cached is not None:
            return key, cached
        png_bytes = await asyncio.to_thread(
            render_player_card_png,
            name=name,
            wins=wins,
            losses=losses,
            draws=draws,
            avatar_bytes=avatar_bytes,
        )
        card = CachedPlayerCard(png_bytes=png_bytes)
        cache.put(key, card)
        return key, card
