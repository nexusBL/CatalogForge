from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from scraper.swiggy.safe_fetch import fetch_public_http_bytes

LOGGER = logging.getLogger("hectobaba.assets")

IMAGE_KEYS = {"image_url", "hero_image", "location_map_image", "map_image", "image"}
SKIP_KEYS = {
    "maps_url",
    "directions_url",
    "source_url",
    "source_image_url",
    "cta",
    "link",
    "url",
}
LIST_KEYS = {"photos", "images"}
HTTP_RE = re.compile(r"^https?://", re.I)


def assets_root() -> Path:
    return Path(os.getenv("CATALOGFORGE_ASSETS_DIR", "data/catalogue-assets"))


def remove_owned_catalogue_assets(catalogue_id: str) -> None:
    """Delete files stored exclusively under this catalogue id. Does not touch other catalogues."""
    if not catalogue_id or any(part in catalogue_id for part in ("/", "\\", "..")):
        return
    root = assets_root().resolve()
    dest = (root / catalogue_id).resolve()
    if dest == root or root not in dest.parents:
        return
    if dest.is_dir():
        shutil.rmtree(dest, ignore_errors=True)


def download_images_enabled() -> bool:
    return os.getenv("CATALOGFORGE_DOWNLOAD_IMAGES", "1").strip().lower() not in {"0", "false", "no", "off"}


def materialize_catalogue_images(
    payload: dict[str, Any],
    catalogue_id: str,
    *,
    fetch: Callable[[str], bytes | None] | None = None,
) -> dict[str, Any]:
    if not download_images_enabled() or not catalogue_id:
        return payload
    dest = assets_root() / catalogue_id
    try:
        dest.mkdir(parents=True, exist_ok=True)
    except OSError:
        LOGGER.warning("catalogue asset directory could not be created for %s", catalogue_id)
        return payload
    cache: dict[str, str] = {}
    getter = fetch or _fetch_bytes
    prefix = f"/catalogue-assets/{catalogue_id}"
    _rewrite(payload, dest, prefix, cache, getter)
    return payload


def _fetch_bytes(url: str) -> bytes | None:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) HectoBaba/1.0",
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    }
    lowered = url.lower()
    if "zmtcdn.com" in lowered or "zomato.com" in lowered:
        headers["Referer"] = "https://www.zomato.com/"
    elif "googleusercontent.com" in lowered or "magicpin" in lowered:
        headers["Referer"] = "https://magicpin.in/"
    data = fetch_public_http_bytes(url, headers=headers, timeout=15)
    if not data:
        LOGGER.warning("image download skipped or failed: %s", url)
        return None
    return data


def _local_name(url: str) -> str:
    path = urlparse(url).path
    suffix = Path(path).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}:
        suffix = ".img"
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return f"{digest}{suffix}"


def _store(url: str, dest: Path, prefix: str, cache: dict[str, str], fetch: Callable[[str], bytes | None]) -> str:
    if url in cache:
        return cache[url]
    if url.startswith("/catalogue-assets/"):
        cache[url] = url
        return url
    name = _local_name(url)
    path = dest / name
    try:
        if not path.exists():
            data = fetch(url)
            if not data:
                cache[url] = url
                return url
            path.write_bytes(data)
    except OSError:
        LOGGER.warning("image store failed; keeping source URL")
        cache[url] = url
        return url
    local = f"{prefix}/{name}"
    cache[url] = local
    return local

def _rewrite(
    value: Any,
    dest: Path,
    prefix: str,
    cache: dict[str, str],
    fetch: Callable[[str], bytes | None],
    parent_key: str | None = None,
) -> None:
    if isinstance(value, list):
        if parent_key in LIST_KEYS:
            for index, item in enumerate(value):
                if isinstance(item, str) and HTTP_RE.match(item):
                    value[index] = _store(item, dest, prefix, cache, fetch)
                else:
                    _rewrite(item, dest, prefix, cache, fetch)
            return
        for item in value:
            _rewrite(item, dest, prefix, cache, fetch)
        return
    if not isinstance(value, dict):
        return
    if _is_gallery_entry(value) and isinstance(value.get("url"), str) and HTTP_RE.match(value["url"]):
        original = value["url"]
        local = _store(original, dest, prefix, cache, fetch)
        if local != original:
            value["source_url"] = value.get("source_url") or original
            value["url"] = local
    for key, child in list(value.items()):
        if key in SKIP_KEYS and key != "url":
            continue
        if key in IMAGE_KEYS and isinstance(child, str) and HTTP_RE.match(child):
            local = _store(child, dest, prefix, cache, fetch)
            if local != child:
                if key in {"image", "image_url"} and not value.get("source_image_url"):
                    value["source_image_url"] = child
                value[key] = local
            continue
        _rewrite(child, dest, prefix, cache, fetch, parent_key=key)


def _is_gallery_entry(value: dict[str, Any]) -> bool:
    return "url" in value and ("category" in value or set(value.keys()) <= {"url", "category", "source_url"})
