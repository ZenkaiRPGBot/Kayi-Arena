"""Image discovery, download, and validation helpers."""

from __future__ import annotations

import hashlib
import os
import struct
import threading
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.content.models import CandidateImage

USER_AGENT = "KayiArenaContentTool/1.0 (+https://github.com/ZenkaiRPGBot/Kayi-Arena)"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def detect_format(data: bytes) -> str | None:
    if len(data) < 12:
        return None
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data.startswith(b"BM"):
        return "bmp"
    return None


def _parse_png(data: bytes) -> tuple[int, int] | None:
    # IHDR is the first chunk after the 8-byte signature.
    if len(data) < 24:
        return None
    if data[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def _parse_gif(data: bytes) -> tuple[int, int] | None:
    if len(data) < 10:
        return None
    width, height = struct.unpack("<HH", data[6:10])
    return width, height


def _parse_bmp(data: bytes) -> tuple[int, int] | None:
    if len(data) < 26:
        return None
    width, height = struct.unpack("<ii", data[18:26])
    return abs(width), abs(height)


def _parse_webp(data: bytes) -> tuple[int, int] | None:
    if len(data) < 30:
        return None
    chunk = data[12:16]
    if chunk == b"VP8 ":
        # Lossy
        if len(data) < 30:
            return None
        width = struct.unpack("<H", data[26:28])[0] & 0x3fff
        height = struct.unpack("<H", data[28:30])[0] & 0x3fff
        return width, height
    if chunk == b"VP8L":
        if len(data) < 25:
            return None
        bits = struct.unpack("<I", data[21:25])[0]
        width = (bits & 0x3fff) + 1
        height = ((bits >> 14) & 0x3fff) + 1
        return width, height
    if chunk == b"VP8X":
        if len(data) < 30:
            return None
        width = int.from_bytes(data[24:27], "little") + 1
        height = int.from_bytes(data[27:30], "little") + 1
        return width, height
    return None


def _parse_jpeg(data: bytes) -> tuple[int, int] | None:
    i = 2
    n = len(data)
    while i < n:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1] if i + 1 < n else 0
        if marker in (0xD8, 0xD9):
            i += 2
            continue
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            if i + 9 >= n:
                return None
            height, width = struct.unpack(">HH", data[i + 5 : i + 9])
            return width, height
        if i + 3 >= n:
            return None
        segment_length = struct.unpack(">H", data[i + 2 : i + 4])[0]
        i += 2 + segment_length
    return None


def parse_dimensions(data: bytes, fmt: str | None = None) -> tuple[int, int] | None:
    fmt = fmt or detect_format(data)
    if fmt == "png":
        return _parse_png(data)
    if fmt == "jpeg":
        return _parse_jpeg(data)
    if fmt == "gif":
        return _parse_gif(data)
    if fmt == "webp":
        return _parse_webp(data)
    if fmt == "bmp":
        return _parse_bmp(data)
    return None


def validate_image_bytes(data: bytes) -> dict[str, Any]:
    fmt = detect_format(data)
    if fmt is None:
        return {"ok": False, "error": "unrecognized image format", "format": None}
    dimensions = parse_dimensions(data, fmt)
    if dimensions is None:
        return {"ok": False, "error": "could not parse dimensions", "format": fmt}
    width, height = dimensions
    if width <= 0 or height <= 0:
        return {"ok": False, "error": "invalid dimensions", "format": fmt, "width": width, "height": height}
    # Basic corruption checks: trailing markers.
    if fmt == "png" and not data.endswith(b"IEND\xaeB`\x82"):
        return {"ok": False, "error": "png missing IEND trailer", "format": fmt, "width": width, "height": height}
    if fmt == "jpeg" and not data.endswith(b"\xff\xd9"):
        return {"ok": False, "error": "jpeg missing EOI marker", "format": fmt, "width": width, "height": height}
    return {
        "ok": True,
        "error": None,
        "format": fmt,
        "width": width,
        "height": height,
        "bytes": len(data),
        "sha256": sha256_bytes(data),
    }


def download_url(url: str, timeout: float = 30.0) -> tuple[int | None, bytes, str | None, str | None]:
    try:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "image/*"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read()
            content_type = response.headers.get("Content-Type")
            return getattr(response, "status", 200), data, content_type, None
    except urllib.error.HTTPError as exc:
        try:
            data = exc.read()
        except Exception:
            data = b""
        return exc.code, data, exc.headers.get("Content-Type") if exc.headers else None, f"http {exc.code}"
    except Exception as exc:  # network/timeout/decode
        return None, b"", None, f"{type(exc).__name__}: {exc}"


def process_image(
    image: CandidateImage,
    *,
    output_dir: Path,
    candidate_id: str,
    index: int,
    seen_hashes: set[str],
    download: bool = True,
    timeout: float = 30.0,
    min_width: int = 64,
    min_height: int = 64,
    _lock: threading.Lock | None = None,
) -> CandidateImage:
    if not download:
        image.status = "pending"
        return image

    status_code, data, content_type, error = download_url(image.url, timeout=timeout)
    if error is not None or not data:
        image.status = "missing" if status_code == 404 else "invalid"
        image.error = error or "empty response"
        return image

    result = validate_image_bytes(data)
    if not result["ok"]:
        image.status = "invalid"
        image.error = result["error"]
        return image

    image.format = result["format"]
    image.width = result["width"]
    image.height = result["height"]
    image.bytes = result["bytes"]
    image.sha256 = result["sha256"]

    if image.width < min_width or image.height < min_height:
        image.status = "invalid"
        image.error = f"image too small: {image.width}x{image.height}"
        return image

    if _lock is not None:
        with _lock:
            is_duplicate = image.sha256 in seen_hashes
            if not is_duplicate:
                seen_hashes.add(image.sha256)
    else:
        is_duplicate = image.sha256 in seen_hashes
        if not is_duplicate:
            seen_hashes.add(image.sha256)

    if is_duplicate:
        image.status = "duplicate"
        image.error = "exact duplicate of an already accepted image"
        return image
    # Persist the validated image.
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_id = candidate_id.replace(":", "_").replace("/", "_")
    filename = f"{safe_id}_{index}_{image.sha256[:12]}.{image.format}"
    destination = output_dir / filename
    destination.write_bytes(data)
    image.status = "valid"
    image.error = None
    return image


def process_catalogue_images(
    catalogue,
    *,
    output_dir: Path,
    download: bool = True,
    timeout: float = 30.0,
    concurrency: int = 1,
) -> dict[str, Any]:
    seen_hashes: set[str] = set()
    lock = threading.Lock()
    total = 0
    tasks: list[tuple] = []
    for candidate in catalogue.candidates:
        for index, image in enumerate(candidate.images):
            total += 1
            tasks.append((candidate, index, image))

    downloaded = 0
    valid = 0
    invalid = 0
    missing = 0
    duplicates = 0

    def _run(task):
        candidate, index, image = task
        process_image(
            image,
            output_dir=output_dir,
            candidate_id=candidate.candidate_id,
            index=index,
            seen_hashes=seen_hashes,
            download=download,
            timeout=timeout,
            _lock=lock,
        )
        return image

    if concurrency <= 1:
        for task in tasks:
            image = _run(task)
            if image.status == "valid":
                valid += 1
                downloaded += 1
            elif image.status == "duplicate":
                duplicates += 1
            elif image.status == "missing":
                missing += 1
            else:
                invalid += 1
    else:
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [executor.submit(_run, task) for task in tasks]
            for future in as_completed(futures):
                image = future.result()
                if image.status == "valid":
                    valid += 1
                    downloaded += 1
                elif image.status == "duplicate":
                    duplicates += 1
                elif image.status == "missing":
                    missing += 1
                else:
                    invalid += 1

    return {
        "total_images": total,
        "downloaded": downloaded,
        "valid": valid,
        "invalid": invalid,
        "missing": missing,
        "duplicates": duplicates,
    }
