"""Local vision grader.

Approved Phase 3 implementation: on-host image analysis (decode, format,
dimensions, size, missing/invalid/unreadable/low-quality). Remote URLs use
existing SSRF-safe fetch with duplicate-URL caching, remote-count bound, byte
limit, and timeout. Local `/catalogue-assets/` paths are confined. Supported
decodes: PNG, JPEG, GIF, WebP, and AVIF (ISO-BMFF `ispe` dimensions; CDNs
often serve AVIF under a `.jpg` name). No external vision provider. No neural
CV model is required for Phase 3.
"""

from __future__ import annotations

import os
import struct
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from backend.canonical.models import CanonicalDocument
from backend.grading.contract import StageSignals
from backend.grading.document import iter_menu_items
from backend.grading.evidence import evidence
from scraper.swiggy.assets import assets_root
from scraper.swiggy.safe_fetch import (
    DEFAULT_TIMEOUT,
    MAX_BYTES,
    UnsafeURLError,
    assert_public_http_url,
    fetch_public_http_bytes,
)

MIN_EDGE_PX = 64
MIN_PIXELS = 80 * 80
# Engineering safety limit (not a product catalogue-size rule). Override with
# CATALOGFORGE_GRADE_MAX_REMOTE_IMAGES. Unique URLs are fetched once.
MAX_REMOTE_IMAGES = int(os.getenv("CATALOGFORGE_GRADE_MAX_REMOTE_IMAGES", "500"))
FetchBytes = Callable[[str], bytes | None]
PROCESSING_STATUSES = {
    "ssrf",
    "fetch_failed",
    "processing_failed",
    "oversized",
    "timeout",
    "budget_exceeded",
}


class OversizedImageError(ValueError):
    pass


class VisionGrader:
    def __init__(
        self,
        *,
        fetch: FetchBytes | None = None,
        max_remote_images: int | None = None,
        max_bytes: int = MAX_BYTES,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._fetch = fetch
        self._max_remote_images = MAX_REMOTE_IMAGES if max_remote_images is None else max_remote_images
        self._max_bytes = max_bytes
        self._timeout = timeout

    def grade(self, document: CanonicalDocument, *, catalogue_id: str | None = None) -> StageSignals:
        refs = _collect_image_refs(document)
        findings = []
        if not refs:
            findings.append(
                evidence(
                    category="vision",
                    check_id="no_images_present",
                    severity="ordinary",
                    result="fail",
                    explanation="No catalogue images were present to evaluate.",
                )
            )
            return StageSignals(score=0.0, evidence=findings, status="completed")

        cache: dict[str, tuple[str, dict]] = {}
        usable = 0
        remote_unique = 0
        processing_failed = False
        for path, url in refs:
            key = url
            if key not in cache:
                if _is_remote_url(url) and url.strip():
                    remote_unique += 1
                    if remote_unique > self._max_remote_images:
                        cache[key] = (
                            "budget_exceeded",
                            {"limit": self._max_remote_images, "unique_remote": remote_unique},
                        )
                    else:
                        cache[key] = self._inspect(url, catalogue_id=catalogue_id)
                else:
                    cache[key] = self._inspect(url, catalogue_id=catalogue_id)
            status, details = cache[key]
            if status in PROCESSING_STATUSES:
                processing_failed = True
            check_id, result, explanation = _evidence_for_status(status)
            if status == "ok":
                usable += 1
            findings.append(
                evidence(
                    category="vision",
                    check_id=check_id,
                    severity="ordinary" if result != "pass" else "info",
                    result=result,
                    explanation=explanation,
                    path=path,
                    details=details,
                )
            )

        quality_refs = [url for _path, url in refs]
        score = round(100.0 * usable / max(len(quality_refs), 1), 4)
        if processing_failed:
            return StageSignals(
                score=0.0,
                evidence=findings,
                status="failed",
                error="Vision processing failed; catalogue quality was not fully evaluated.",
            )
        return StageSignals(score=score, evidence=findings, status="completed")

    def _inspect(self, url: str, *, catalogue_id: str | None) -> tuple[str, dict]:
        if not (url or "").strip():
            return "missing", {}
        try:
            data = self._load_bytes(url.strip(), catalogue_id=catalogue_id)
        except UnsafeURLError:
            return "ssrf", {"reason": "blocked"}
        except TimeoutError:
            return "timeout", {"reason": "timeout"}
        except OversizedImageError:
            return "oversized", {"reason": "oversized"}
        except OSError:
            return "fetch_failed", {"reason": "io_error"}
        except Exception:
            return "processing_failed", {"reason": "unexpected"}
        if data is None:
            return "fetch_failed", {"url_scheme": urlparse(url).scheme, "reason": "fetch_failed"}
        if not data:
            return "invalid", {"reason": "empty"}
        if len(data) > self._max_bytes:
            return "oversized", {"reason": "oversized", "max_bytes": self._max_bytes}
        parsed = inspect_image_bytes(data)
        status = str(parsed.pop("status", "unreadable"))
        return status, parsed

    def _load_bytes(self, url: str, *, catalogue_id: str | None) -> bytes | None:
        local = _local_asset_path(url, catalogue_id)
        if local is not None:
            if not local.is_file():
                return None
            size = local.stat().st_size
            if size > self._max_bytes:
                raise OversizedImageError("image exceeds size limit")
            return local.read_bytes()
        parsed = urlparse(url)
        if parsed.scheme in {"http", "https"}:
            if self._fetch is not None:
                return self._fetch(url)
            assert_public_http_url(url)
            return fetch_public_http_bytes(url, timeout=self._timeout, max_bytes=self._max_bytes)
        return None


def _is_remote_url(url: str) -> bool:
    parsed = urlparse((url or "").strip())
    return parsed.scheme in {"http", "https"}


def _evidence_for_status(status: str) -> tuple[str, str, str]:
    mapping = {
        "ok": ("image_ok", "pass", "Image decoded with acceptable dimensions."),
        "missing": ("image_missing", "fail", "Image reference is empty."),
        "invalid": ("image_invalid", "fail", "Image bytes are not a recognized image format."),
        "unreadable": ("image_unreadable", "fail", "Image bytes could not be parsed."),
        "low_quality": ("image_low_quality", "fail", "Image is too small to be a useful catalogue photo."),
        "ssrf": ("image_fetch_blocked", "error", "Image URL was blocked by SSRF protections."),
        "fetch_failed": ("image_fetch_failed", "error", "Image could not be fetched."),
        "timeout": ("image_fetch_timeout", "error", "Image fetch timed out."),
        "oversized": ("image_oversized", "error", "Image exceeds the grading size limit."),
        "budget_exceeded": (
            "image_fetch_budget_exceeded",
            "error",
            "Too many unique remote images for a synchronous grade.",
        ),
        "processing_failed": ("image_processing_failed", "error", "Image processing failed."),
    }
    return mapping.get(status, ("image_processing_failed", "error", "Image processing failed."))


def _collect_image_refs(document: CanonicalDocument) -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    if document.venue.image_url:
        refs.append(("venue.image_url", document.venue.image_url))
    for path, _category, item in iter_menu_items(document):
        url = item.image_url or item.source_image_url or ""
        refs.append((f"{path}.image_url", url))
    dineout = document.dineout or {}
    gallery = dineout.get("gallery_images") if isinstance(dineout, dict) else None
    if isinstance(gallery, list):
        for index, entry in enumerate(gallery):
            if isinstance(entry, str) and entry.strip():
                refs.append((f"dineout.gallery_images[{index}]", entry.strip()))
            elif isinstance(entry, dict):
                image = entry.get("source_url") or entry.get("image_url") or entry.get("url")
                if isinstance(image, str) and image.strip():
                    refs.append((f"dineout.gallery_images[{index}]", image.strip()))
    return refs


def _local_asset_path(url: str, catalogue_id: str | None) -> Path | None:
    marker = "/catalogue-assets/"
    if marker not in url.replace("\\", "/"):
        return None
    relative = url.split(marker, 1)[1]
    parts = [part for part in relative.split("/") if part and part != ".."]
    if not parts:
        return None
    root = assets_root().resolve()
    dest = (root.joinpath(*parts)).resolve()
    if root not in dest.parents and dest != root:
        return None
    if catalogue_id and parts[0] != catalogue_id:
        return None
    return dest


def inspect_image_bytes(data: bytes) -> dict:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        if len(data) < 24:
            return {"status": "unreadable", "format": "png"}
        width, height = struct.unpack(">II", data[16:24])
        return _dimension_status("png", width, height)
    if data[:2] == b"\xff\xd8":
        size = _jpeg_size(data)
        if size is None:
            return {"status": "unreadable", "format": "jpeg"}
        return _dimension_status("jpeg", size[0], size[1])
    if data[:6] in (b"GIF87a", b"GIF89a") and len(data) >= 10:
        width, height = struct.unpack("<HH", data[6:10])
        return _dimension_status("gif", width, height)
    if len(data) >= 30 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        size = _webp_size(data)
        if size is None:
            return {"status": "unreadable", "format": "webp"}
        return _dimension_status("webp", size[0], size[1])
    if _looks_like_avif(data):
        size = _avif_size(data)
        if size is None:
            return {"status": "unreadable", "format": "avif"}
        return _dimension_status("avif", size[0], size[1])
    return {"status": "invalid", "reason": "unrecognized_format"}


def _dimension_status(fmt: str, width: int, height: int) -> dict:
    details = {"format": fmt, "width": width, "height": height, "pixels": width * height}
    if width <= 0 or height <= 0:
        details["status"] = "unreadable"
        return details
    if min(width, height) < MIN_EDGE_PX or width * height < MIN_PIXELS:
        details["status"] = "low_quality"
        return details
    details["status"] = "ok"
    return details


def _looks_like_avif(data: bytes) -> bool:
    if len(data) < 12 or data[4:8] != b"ftyp":
        return False
    brands = data[8 : min(len(data), 64)]
    return b"avif" in brands or b"avis" in brands


def _iter_bmff_boxes(data: bytes, start: int, end: int):
    index = start
    while index + 8 <= end:
        size = int.from_bytes(data[index : index + 4], "big")
        box_type = data[index + 4 : index + 8]
        if size == 1:
            if index + 16 > end:
                return
            size = int.from_bytes(data[index + 8 : index + 16], "big")
            header = 16
        elif size == 0:
            size = end - index
            header = 8
        else:
            header = 8
        if size < header or index + size > end:
            return
        yield box_type, index + header, index + size
        index += size


def _avif_size(data: bytes) -> tuple[int, int] | None:
    def walk(start: int, end: int, *, full_box: bool = False) -> tuple[int, int] | None:
        payload_start = start + 4 if full_box else start
        if payload_start > end:
            return None
        for box_type, inner_start, inner_end in _iter_bmff_boxes(data, payload_start, end):
            if box_type == b"ispe" and inner_end - inner_start >= 12:
                width = int.from_bytes(data[inner_start + 4 : inner_start + 8], "big")
                height = int.from_bytes(data[inner_start + 8 : inner_start + 12], "big")
                if width > 0 and height > 0:
                    return width, height
            nested_full = box_type == b"meta"
            if box_type in {b"meta", b"iprp", b"ipco", b"moov", b"trak", b"mdia", b"minf", b"stbl"}:
                found = walk(inner_start, inner_end, full_box=nested_full)
                if found is not None:
                    return found
        return None

    return walk(0, len(data))


def _jpeg_size(data: bytes) -> tuple[int, int] | None:
    index = 2
    length = len(data)
    while index + 9 < length:
        if data[index] != 0xFF:
            return None
        marker = data[index + 1]
        if marker in {0xD8, 0xD9}:
            index += 2
            continue
        if marker == 0xFF:
            index += 1
            continue
        block = struct.unpack(">H", data[index + 2 : index + 4])[0]
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            height = struct.unpack(">H", data[index + 5 : index + 7])[0]
            width = struct.unpack(">H", data[index + 8 : index + 10])[0]
            return width, height
        if block < 2:
            return None
        index += 2 + block
    return None


def _webp_size(data: bytes) -> tuple[int, int] | None:
    kind = data[12:16]
    if kind == b"VP8X" and len(data) >= 30:
        width = 1 + int.from_bytes(data[24:27], "little")
        height = 1 + int.from_bytes(data[27:30], "little")
        return width, height
    if kind == b"VP8 " and len(data) >= 30:
        width = struct.unpack("<H", data[26:28])[0] & 0x3FFF
        height = struct.unpack("<H", data[28:30])[0] & 0x3FFF
        return width, height
    if kind == b"VP8L" and len(data) >= 25:
        bits = struct.unpack("<I", data[21:25])[0]
        width = (bits & 0x3FFF) + 1
        height = ((bits >> 14) & 0x3FFF) + 1
        return width, height
    return None
