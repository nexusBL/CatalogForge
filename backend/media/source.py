"""Load catalogue media bytes with SSRF confinement. Does not mutate catalogues."""

from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import urlparse

from scraper.swiggy.assets import assets_root
from scraper.swiggy.safe_fetch import (
    MAX_BYTES,
    UnsafeURLError,
    assert_public_http_url,
    fetch_public_http_bytes,
)

ICON_RE = ("veg-icon", "non-veg-icon", "egg-icon", "star-filled", "star-empty", "web/assets", "web_assets")


class MediaSourceError(ValueError):
    pass


def is_usable_image_ref(url: str | None) -> bool:
    text = (url or "").strip()
    if not text:
        return False
    lowered = text.lower()
    if any(token in lowered for token in ICON_RE):
        return False
    parsed = urlparse(text)
    if parsed.scheme in {"http", "https"}:
        return True
    return "/catalogue-assets/" in text.replace("\\", "/")


def source_snapshot_hash(data: bytes | None, ref: str | None) -> str:
    payload = (ref or "").encode("utf-8") + b"\0" + (data or b"")
    return hashlib.sha256(payload).hexdigest()


def confined_generated_path(root: Path, parts: list[str]) -> Path:
    if any(part in {".", ".."} or "/" in part or "\\" in part or not part for part in parts):
        raise MediaSourceError("Invalid generated-media path.")
    dest = root.joinpath(*parts).resolve()
    base = root.resolve()
    if dest != base and base not in dest.parents:
        raise MediaSourceError("Generated media path escaped storage root.")
    return dest


def local_catalogue_asset_path(url: str, catalogue_id: str | None) -> Path | None:
    marker = "/catalogue-assets/"
    normalized = url.replace("\\", "/")
    if marker not in normalized:
        return None
    relative = normalized.split(marker, 1)[1]
    parts = [part for part in relative.split("/") if part and part != ".."]
    if not parts:
        return None
    root = assets_root().resolve()
    dest = root.joinpath(*parts).resolve()
    if root not in dest.parents and dest != root:
        return None
    if catalogue_id and parts[0] != catalogue_id:
        return None
    return dest


def load_image_bytes(url: str, *, catalogue_id: str | None) -> bytes:
    text = (url or "").strip()
    if not text:
        raise MediaSourceError("No source image is present.")
    if text.lower().endswith(".svg") or text.startswith("data:"):
        raise MediaSourceError("SVG and data URLs are not allowed as catalogue generation sources.")
    local = local_catalogue_asset_path(text, catalogue_id)
    if local is not None:
        if not local.is_file():
            raise MediaSourceError("Local catalogue asset was not found.")
        size = local.stat().st_size
        if size > MAX_BYTES:
            raise MediaSourceError("Source image exceeds the size limit.")
        data = local.read_bytes()
        if data.lstrip()[:1] == b"<" or data[:4] == b"<svg":
            raise MediaSourceError("SVG content is not allowed.")
        return data
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"}:
        raise MediaSourceError("Source image URL is not allowed.")
    try:
        assert_public_http_url(text)
    except UnsafeURLError as exc:
        raise MediaSourceError("Source image URL was blocked by SSRF protections.") from exc
    data = fetch_public_http_bytes(text, timeout=15, max_bytes=MAX_BYTES)
    if not data:
        raise MediaSourceError("Source image could not be fetched.")
    if data.lstrip()[:1] == b"<":
        raise MediaSourceError("Fetched content is not a safe image.")
    return data
