"""Deterministic image validation tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.content.images import (
    detect_format,
    parse_dimensions,
    sha256_bytes,
    validate_image_bytes,
)
from app.content.models import CandidateImage


def _png_bytes(width: int = 2, height: int = 3) -> bytes:
    import struct

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    # Minimal valid-ish PNG: signature + IHDR chunk + IEND
    def chunk(typ: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + typ + data + struct.pack(">I", 0)

    ihdr_chunk = chunk(b"IHDR", ihdr)
    iend_chunk = b"\x00\x00\x00\x00IEND\xaeB`\x82"
    return signature + ihdr_chunk + iend_chunk


def test_detect_and_parse_png() -> None:
    data = _png_bytes(10, 20)
    assert detect_format(data) == "png"
    assert parse_dimensions(data, "png") == (10, 20)


def test_validate_image_bytes_rejects_truncated_png() -> None:
    data = _png_bytes(4, 4)[:-4]
    result = validate_image_bytes(data)
    assert result["ok"] is False


def test_sha256_is_stable() -> None:
    assert sha256_bytes(b"abc") == sha256_bytes(b"abc")
    assert sha256_bytes(b"abc") != sha256_bytes(b"def")


def test_validate_rejects_unknown_bytes() -> None:
    result = validate_image_bytes(b"not an image")
    assert result["ok"] is False
    assert result["format"] is None


def test_process_image_marks_missing_on_404(monkeypatch, tmp_path: Path) -> None:
    from app.content import images

    monkeypatch.setattr(
        images, "download_url", lambda url, timeout=30.0: (404, b"", None, "http 404")
    )
    image = CandidateImage(url="https://example.com/x.png")
    result = images.process_image(
        image,
        output_dir=tmp_path,
        candidate_id="c:1",
        index=0,
        seen_hashes=set(),
        download=True,
    )
    assert result.status == "missing"


def test_process_image_writes_valid_image(monkeypatch, tmp_path: Path) -> None:
    from app.content import images

    data = _png_bytes(64, 64)
    monkeypatch.setattr(
        images, "download_url", lambda url, timeout=30.0: (200, data, "image/png", None)
    )
    image = CandidateImage(url="https://example.com/x.png")
    result = images.process_image(
        image,
        output_dir=tmp_path,
        candidate_id="c:1",
        index=0,
        seen_hashes=set(),
        download=True,
    )
    assert result.status == "valid"
    assert result.sha256 is not None
    assert (tmp_path).exists()
    assert any(tmp_path.iterdir())


def test_process_image_detects_exact_duplicate(monkeypatch, tmp_path: Path) -> None:
    from app.content import images

    data = _png_bytes(64, 64)
    monkeypatch.setattr(
        images, "download_url", lambda url, timeout=30.0: (200, data, "image/png", None)
    )
    seen: set[str] = set()
    first = CandidateImage(url="https://example.com/a.png")
    second = CandidateImage(url="https://example.com/b.png")
    images.process_image(first, output_dir=tmp_path, candidate_id="c:1", index=0, seen_hashes=seen, download=True)
    images.process_image(second, output_dir=tmp_path, candidate_id="c:1", index=1, seen_hashes=seen, download=True)
    assert first.status == "valid"
    assert second.status == "duplicate"
