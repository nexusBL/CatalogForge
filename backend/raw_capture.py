"""Durable raw catalogue captures on the local filesystem. No database table."""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import os
import re
import uuid
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scraper.swiggy.models import RawSource

LOGGER = logging.getLogger("hectobaba.raw_capture")

DEFAULT_RAW_DIR = "data/catalogue-raw"
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9._-]+$")


def raw_root() -> Path:
    return Path(os.getenv("CATALOGFORGE_RAW_DIR", DEFAULT_RAW_DIR))


def _safe_segment(value: str, *, fallback: str) -> str:
    text = (value or "").strip()
    if text and _SAFE_SEGMENT.fullmatch(text) and ".." not in text and len(text) <= 128:
        return text
    digest = hashlib.sha256((text or fallback).encode("utf-8")).hexdigest()[:32]
    return digest


def _assert_under_root(path: Path) -> Path:
    root = raw_root().resolve()
    resolved = path.resolve()
    if resolved == root or root not in resolved.parents:
        raise ValueError("raw capture path is outside the raw directory")
    return resolved


def pending_dir(organization_id: str) -> Path:
    org = _safe_segment(organization_id, fallback="org")
    return raw_root() / "pending" / org


def bound_dir(organization_id: str, catalogue_id: str) -> Path:
    org = _safe_segment(organization_id, fallback="org")
    cat = _safe_segment(catalogue_id, fallback="catalogue")
    return raw_root() / org / cat


def write_pending_raw(
    *,
    organization_id: str,
    raw: RawSource,
    platform: str | None = None,
) -> str | None:
    """Write a pending capture. Never raises into the ingest path; returns scrape_token or None."""
    token = str(uuid.uuid4())
    try:
        dest_dir = pending_dir(organization_id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = _assert_under_root(dest_dir / f"{_safe_segment(token, fallback=token)}.json.gz")
        raw_dict = asdict(raw) if is_dataclass(raw) else {}
        envelope = {
            "scrape_token": token,
            "organization_id": organization_id,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "platform": platform,
            "source_url": raw.source_url,
            "raw": raw_dict,
        }
        data = json.dumps(envelope, ensure_ascii=False, default=str).encode("utf-8")
        dest.write_bytes(gzip.compress(data))
        return token
    except OSError:
        LOGGER.exception("raw pending write failed")
        return None


def bind_raw_capture(
    *,
    organization_id: str,
    scrape_token: str | None,
    catalogue_id: str,
    user_id: str | None = None,
) -> Path | None:
    """Move pending capture under the final catalogue id. Does not delete on failure."""
    if not scrape_token or not catalogue_id:
        return None
    token = _safe_segment(scrape_token, fallback=scrape_token)
    pending = pending_dir(organization_id) / f"{token}.json.gz"
    if not pending.is_file():
        return None
    try:
        pending = _assert_under_root(pending)
        dest_dir = bound_dir(organization_id, catalogue_id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = _assert_under_root(dest_dir / f"{token}.json.gz")
        payload = json.loads(gzip.decompress(pending.read_bytes()).decode("utf-8"))
        if isinstance(payload, dict):
            payload["catalogue_id"] = catalogue_id
            if user_id:
                payload["user_id"] = user_id
            dest.write_bytes(gzip.compress(json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")))
        else:
            dest.write_bytes(pending.read_bytes())
        pending.unlink()
        return dest
    except OSError:
        LOGGER.exception("raw bind failed; pending capture retained")
        return None


def pending_path(organization_id: str, scrape_token: str) -> Path:
    return pending_dir(organization_id) / f"{_safe_segment(scrape_token, fallback=scrape_token)}.json.gz"


def bound_path(organization_id: str, catalogue_id: str, scrape_token: str) -> Path:
    return bound_dir(organization_id, catalogue_id) / f"{_safe_segment(scrape_token, fallback=scrape_token)}.json.gz"


def read_capture(path: Path) -> dict[str, Any]:
    return json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))
