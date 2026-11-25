"""Optional customer-feedback photo storage. Not Phase 7 generation."""

from __future__ import annotations

import os
from pathlib import Path

from backend.media.source import MediaSourceError, confined_generated_path

MAX_PHOTO_BYTES = 2_000_000
ALLOWED_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


class PhotoRejected(ValueError):
    pass


def evidence_root() -> Path:
    return Path(os.getenv("CATALOGFORGE_REVIEW_EVIDENCE_DIR", "data/review-evidence"))


def evidence_path(*, user_id: str, organization_id: str, catalogue_id: str, photo_id: str, suffix: str) -> Path:
    root = evidence_root()
    root.mkdir(parents=True, exist_ok=True)
    return confined_generated_path(
        root,
        [user_id, organization_id, catalogue_id, f"{photo_id}.{suffix}"],
    )


def detect_image_type(data: bytes) -> tuple[str, str]:
    if len(data) > MAX_PHOTO_BYTES:
        raise PhotoRejected("Photo exceeds the Phase 8 size limit.")
    if len(data) < 12:
        raise PhotoRejected("Photo is not a supported image.")
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg", "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png", "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    raise PhotoRejected("Photo is not a supported image.")


def write_photo(
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
    photo_id: str,
    data: bytes,
) -> str:
    content_type, suffix = detect_image_type(data)
    dest = evidence_path(
        user_id=user_id,
        organization_id=organization_id,
        catalogue_id=catalogue_id,
        photo_id=photo_id,
        suffix=suffix,
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return content_type


def read_photo(
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
    photo_id: str,
) -> tuple[bytes, str]:
    for content_type, suffix in ALLOWED_TYPES.items():
        try:
            dest = evidence_path(
                user_id=user_id,
                organization_id=organization_id,
                catalogue_id=catalogue_id,
                photo_id=photo_id,
                suffix=suffix,
            )
        except MediaSourceError as exc:
            raise KeyError("Photo not found.") from exc
        if dest.is_file():
            data = dest.read_bytes()
            if len(data) > MAX_PHOTO_BYTES:
                raise PhotoRejected("Photo exceeds the Phase 8 size limit.")
            return data, content_type
    raise KeyError("Photo not found.")


def remove_catalogue_evidence(*, user_id: str, organization_id: str, catalogue_id: str) -> None:
    root = evidence_root()
    try:
        dest = confined_generated_path(root, [user_id, organization_id, catalogue_id])
    except MediaSourceError:
        return
    if dest.is_dir():
        for child in dest.iterdir():
            if child.is_file():
                child.unlink(missing_ok=True)
        try:
            dest.rmdir()
        except OSError:
            pass
