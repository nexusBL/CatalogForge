"""Phase 7 media jobs. Preview-only; never writes catalogues.payload."""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone
from typing import Callable

from backend.grading.document import canonical_document_from_result, graded_state_hash, iter_menu_items
from backend.grading.persist import head_revision
from backend.improvement.persist import get_proposal_by_id as get_improvement_proposal
from backend.media.contract import (
    MEDIA_ENGINE_VERSION,
    OPERATIONS_REQUIRING_SOURCE,
    PROVIDER_ID,
    WAIT_SECONDS,
    MediaApplyResult,
    MediaJob,
    MediaJobListResponse,
    MediaJobRequest,
    MediaStudioResponse,
    MediaWorkspaceItem,
    PromptAssistRequest,
    PromptAssistResponse,
)
from backend.media.persist import (
    RESERVATION_STATUS,
    begin_immediate,
    cancel_generating_for_path,
    cas_apply,
    cas_fail_or_cancel,
    cas_finish,
    connect,
    get_artifact,
    get_job_by_key,
    get_owned_job,
    get_workspace,
    insert_artifact,
    insert_job,
    list_job_rows,
    list_workspaces,
    new_id,
    read_artifact_file,
    request_cancel,
    request_key,
    row_to_job,
    store_artifact_bytes,
    upsert_workspace,
    utcnow,
)
from backend.media.prompts import PromptRejected, assist_prompt, classify_prompt, validate_user_prompt
from backend.media.providers import (
    MediaProvider,
    MediaProviderError,
    ProviderRequest,
    safe_job_error,
)
from backend.media.routing import default_media_provider
from backend.media.references import select_reference_images
from backend.media.source import MediaSourceError, is_usable_image_ref, load_image_bytes, source_snapshot_hash
from scraper.swiggy.safe_fetch import MAX_BYTES

_provider_factory: Callable[[], MediaProvider] = default_media_provider


def set_media_provider_factory(factory: Callable[[], MediaProvider] | None) -> None:
    global _provider_factory
    _provider_factory = factory or default_media_provider


class MediaUnsupported(ValueError):
    pass


def _snapshot(connection: sqlite3.Connection, *, user_id: str, organization_id: str, catalogue_id: str):
    row = connection.execute(
        """
        SELECT payload FROM catalogues
        WHERE id = ? AND user_id = ? AND organization_id = ?
        """,
        (catalogue_id, user_id, organization_id),
    ).fetchone()
    if row is None:
        raise KeyError("Catalogue not found for this restaurant organization.")
    from backend.schemas import CatalogCreateResponse

    result = CatalogCreateResponse.model_validate(json.loads(row["payload"]))
    return result, head_revision(connection, catalogue_id), graded_state_hash(result)


def _item_at(document, path: str):
    from backend.improvement.eligibility import CATALOGUE_IMAGES_RE, ITEM_PATH_RE, VENUE_IMAGE_RE

    if VENUE_IMAGE_RE.match(path):
        url = document.venue.image_url if document.venue else None
        return path, document.restaurant_name or "Restaurant Hero", None, "Hero Image", url, document.restaurant_name
    if CATALOGUE_IMAGES_RE.match(path):
        return path, document.restaurant_name or "", None, "", None, document.restaurant_name
    match = ITEM_PATH_RE.match(path)
    if match is None:
        raise MediaUnsupported(f"Unsupported media path: {path}")
    located = None
    for item_path, category, item in iter_menu_items(document):
        if item_path == f"menus[{match.group(1)}].categories[{match.group(2)}].items[{match.group(3)}]":
            located = (item_path, category, item)
            break
    if located is None:
        raise MediaUnsupported(f"Path does not resolve on this catalogue: {path}")
    item_path, category, item = located
    url = item.image_url or item.source_image_url
    field_path = f"{item_path}.image_url"
    return field_path, item.name, item.description, category.name, url, document.restaurant_name


def _sniff_image_type(data: bytes) -> tuple[str, str]:
    if data.startswith(b"\x89PNG"):
        return "image/png", ".png"
    if data[:2] == b"\xff\xd8":
        return "image/jpeg", ".jpg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif", ".gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", ".webp"
    return "application/octet-stream", ".bin"


def _suffix_for(content_type: str) -> str:
    return {
        "image/gif": ".gif",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
        "image/png": ".png",
        "video/mp4": ".mp4",
    }.get(content_type, ".bin")


def _write_artifact(
    connection: sqlite3.Connection,
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
    job_id: str | None,
    kind: str,
    content_type: str,
    data: bytes,
) -> str:
    if len(data) > MAX_BYTES:
        raise MediaUnsupported("Generated media exceeds the size limit.")
    artefact_id = new_id()
    rel = store_artifact_bytes(
        artefact_id=artefact_id,
        user_id=user_id,
        organization_id=organization_id,
        catalogue_id=catalogue_id,
        data=data,
        suffix=_suffix_for(content_type),
    )
    insert_artifact(
        connection,
        artefact_id=artefact_id,
        catalogue_id=catalogue_id,
        user_id=user_id,
        organization_id=organization_id,
        job_id=job_id,
        kind=kind,
        content_type=content_type,
        rel_path=rel,
        byte_size=len(data),
    )
    return artefact_id


def _handoff_from_proposal(
    connection: sqlite3.Connection,
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
    proposal_id: str,
    current_revision: int,
    current_hash: str,
) -> tuple[str | None, str | None]:
    proposal = get_improvement_proposal(
        connection,
        proposal_id=proposal_id,
        catalogue_id=catalogue_id,
        organization_id=organization_id,
        user_id=user_id,
        current_revision=current_revision,
        current_hash=current_hash,
    )
    if proposal is None:
        return None, None
    for line in proposal.lines:
        if line.kind == "media_handoff":
            return line.path, line.check_id
    return None, None


def _reservation_age_seconds(row) -> float:
    stamp = str(row["updated_at"] or row["created_at"] or "")
    try:
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds())
    except ValueError:
        return WAIT_SECONDS + 1


def get_media_studio(
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
    proposal_id: str | None = None,
    path: str | None = None,
) -> MediaStudioResponse:
    requested_path = path
    connection = connect()
    try:
        result, revision, state_hash = _snapshot(
            connection, user_id=user_id, organization_id=organization_id, catalogue_id=catalogue_id
        )
        document = canonical_document_from_result(result)
        workspaces = {
            row["path"]: row
            for row in list_workspaces(
                connection, catalogue_id=catalogue_id, user_id=user_id, organization_id=organization_id
            )
        }
        items: list[MediaWorkspaceItem] = []
        for item_path, category, item in iter_menu_items(document):
            item_field_path = f"{item_path}.image_url"
            url = item.image_url or item.source_image_url
            space = workspaces.get(item_field_path)
            items.append(
                MediaWorkspaceItem(
                    path=item_field_path,
                    name=item.name,
                    description=item.description,
                    category_name=category.name,
                    image_url=url,
                    has_usable_image=is_usable_image_ref(url),
                    active_job_id=None if space is None else space["active_job_id"],
                    active_candidate_id=None if space is None else space["active_candidate_id"],
                )
            )

        hero_url = document.venue.image_url if document.venue else None
        hero_path = "venue.image_url" if requested_path == "venue.image_url" else "restaurant.image_url"
        space = workspaces.get(hero_path) or workspaces.get("restaurant.image_url") or workspaces.get("venue.image_url")
        items.append(
            MediaWorkspaceItem(
                path=hero_path,
                name=document.restaurant_name or "Restaurant Hero",
                description=None,
                category_name="Hero Image",
                image_url=hero_url,
                has_usable_image=is_usable_image_ref(hero_url),
                active_job_id=None if space is None else space["active_job_id"],
                active_candidate_id=None if space is None else space["active_candidate_id"],
            )
        )

        jobs = [
            row_to_job(row, current_revision=revision, current_hash=state_hash)
            for row in list_job_rows(
                connection, catalogue_id=catalogue_id, organization_id=organization_id, user_id=user_id
            )
        ]
        handoff_path = None
        handoff_check = None
        if proposal_id:
            handoff_path, handoff_check = _handoff_from_proposal(
                connection,
                user_id=user_id,
                organization_id=organization_id,
                catalogue_id=catalogue_id,
                proposal_id=proposal_id,
                current_revision=revision,
                current_hash=state_hash,
            )
        target_category = ""
        target_path = requested_path or handoff_path or ""
        if target_path:
            for item in items:
                if item.path == target_path or (
                    target_path in ("restaurant.image_url", "venue.image_url")
                    and item.path in ("restaurant.image_url", "venue.image_url")
                ):
                    target_category = item.category_name
                    break
        if not target_path:
            for item in items:
                if not item.has_usable_image:
                    target_path = item.path
                    target_category = item.category_name
                    break
            if not target_path and items:
                target_path = items[0].path
                target_category = items[0].category_name
        refs = select_reference_images(document, target_path=target_path, target_category=target_category)
        return MediaStudioResponse(
            catalogue_id=catalogue_id,
            restaurant_name=document.restaurant_name,
            source_head_revision=revision,
            source_state_hash=state_hash,
            items=items,
            references=refs,
            jobs=jobs,
            handoff_path=handoff_path,
            handoff_check_id=handoff_check,
        )
    finally:
        connection.close()


def list_media_jobs(*, user_id: str, organization_id: str, catalogue_id: str) -> MediaJobListResponse:
    connection = connect()
    try:
        _result, revision, state_hash = _snapshot(
            connection, user_id=user_id, organization_id=organization_id, catalogue_id=catalogue_id
        )
        jobs = [
            row_to_job(row, current_revision=revision, current_hash=state_hash)
            for row in list_job_rows(
                connection, catalogue_id=catalogue_id, organization_id=organization_id, user_id=user_id
            )
        ]
        return MediaJobListResponse(jobs=jobs)
    finally:
        connection.close()


def get_media_job(*, user_id: str, organization_id: str, catalogue_id: str, job_id: str) -> MediaJob | None:
    connection = connect()
    try:
        _result, revision, state_hash = _snapshot(
            connection, user_id=user_id, organization_id=organization_id, catalogue_id=catalogue_id
        )
        row = get_owned_job(
            connection,
            job_id=job_id,
            catalogue_id=catalogue_id,
            organization_id=organization_id,
            user_id=user_id,
        )
        if row is None:
            return None
        return row_to_job(row, current_revision=revision, current_hash=state_hash)
    finally:
        connection.close()


def assist_media_prompt(
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
    request: PromptAssistRequest,
) -> PromptAssistResponse:
    connection = connect()
    try:
        result, _revision, _hash = _snapshot(
            connection, user_id=user_id, organization_id=organization_id, catalogue_id=catalogue_id
        )
        document = canonical_document_from_result(result)
        _path, name, description, _cat, _url, _rest = _item_at(document, request.path)
        prompt = validate_user_prompt(request.prompt, required=False)
        suggested = assist_prompt(kind=request.kind, name=name, description=description, current_prompt=prompt)
        return PromptAssistResponse(suggested_prompt=suggested, kind=request.kind)
    finally:
        connection.close()


def _mark_job_running(
    connection: sqlite3.Connection,
    *,
    catalogue_id: str,
    user_id: str,
    organization_id: str,
    path: str,
    job_id: str,
    original_artifact_id: str | None,
) -> None:
    space = get_workspace(
        connection,
        catalogue_id=catalogue_id,
        user_id=user_id,
        organization_id=organization_id,
        path=path,
    )
    upsert_workspace(
        connection,
        catalogue_id=catalogue_id,
        user_id=user_id,
        organization_id=organization_id,
        path=path,
        active_job_id=None if space is None else space["active_job_id"],
        active_candidate_id=None if space is None else space["active_candidate_id"],
        original_artifact_id=original_artifact_id,
        running_job_id=job_id,
    )


def _clear_running_if_owner(
    connection: sqlite3.Connection,
    *,
    catalogue_id: str,
    user_id: str,
    organization_id: str,
    path: str,
    job_id: str,
    original_artifact_id: str | None,
    clear_active: bool,
) -> None:
    space = get_workspace(
        connection,
        catalogue_id=catalogue_id,
        user_id=user_id,
        organization_id=organization_id,
        path=path,
    )
    if space is None or space["running_job_id"] != job_id:
        return
    upsert_workspace(
        connection,
        catalogue_id=catalogue_id,
        user_id=user_id,
        organization_id=organization_id,
        path=path,
        active_job_id=None if clear_active else space["active_job_id"],
        active_candidate_id=None if clear_active else space["active_candidate_id"],
        original_artifact_id=original_artifact_id,
        running_job_id=None,
    )


def _claim_job(
    connection: sqlite3.Connection,
    *,
    key: str,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
    revision: int,
    state_hash: str,
    path: str,
    operation: str,
    claim_token: str,
    payload: dict,
) -> tuple[str, str | None, dict | None]:
    begin_immediate(connection)
    try:
        existing = get_job_by_key(connection, key)
        if existing is None:
            job_id = new_id()
            insert_job(
                connection,
                job_id=job_id,
                request_key_value=key,
                user_id=user_id,
                organization_id=organization_id,
                catalogue_id=catalogue_id,
                source_head_revision=revision,
                source_state_hash=state_hash,
                path=path,
                operation=operation,
                claim_token=claim_token,
                payload=payload,
            )
            _mark_job_running(
                connection,
                catalogue_id=catalogue_id,
                user_id=user_id,
                organization_id=organization_id,
                path=path,
                job_id=job_id,
                original_artifact_id=payload.get("original_artifact_id"),
            )
            connection.execute("COMMIT")
            return "owner", job_id, payload
        if existing["organization_id"] != organization_id or existing["user_id"] != user_id:
            connection.execute("COMMIT")
            raise KeyError("Catalogue not found for this restaurant organization.")
        status = existing["status"]
        stealable = status in {"FAILED", "CANCELLED"} or (
            status == RESERVATION_STATUS and _reservation_age_seconds(existing) > WAIT_SECONDS
        )
        if stealable:
            cursor = connection.execute(
                """
                UPDATE catalogue_media_jobs
                SET status = ?, claim_token = ?, cancel_requested = 0, payload = ?, updated_at = ?
                WHERE id = ? AND status = ?
                """,
                (
                    RESERVATION_STATUS,
                    claim_token,
                    json.dumps(payload, ensure_ascii=False),
                    utcnow(),
                    existing["id"],
                    status,
                ),
            )
            if cursor.rowcount == 1:
                _mark_job_running(
                    connection,
                    catalogue_id=catalogue_id,
                    user_id=user_id,
                    organization_id=organization_id,
                    path=path,
                    job_id=existing["id"],
                    original_artifact_id=payload.get("original_artifact_id"),
                )
                connection.execute("COMMIT")
                return "owner", existing["id"], payload
            connection.execute("COMMIT")
            return "wait", existing["id"], None
        if status != RESERVATION_STATUS:
            connection.execute("COMMIT")
            return "existing", existing["id"], json.loads(existing["payload"])
        connection.execute("COMMIT")
        return "wait", existing["id"], None
    except sqlite3.IntegrityError:
        connection.execute("ROLLBACK")
        return "wait", None, None
    except Exception:
        connection.execute("ROLLBACK")
        raise


def create_media_job(
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
    request: MediaJobRequest,
    provider: MediaProvider | None = None,
) -> MediaJob:
    prompt = validate_user_prompt(request.prompt, required=request.operation == "edit")
    if request.operation == "edit" and not prompt:
        raise MediaUnsupported("A natural-language prompt is required for Edit.")
    connection = connect()
    try:
        result, revision, state_hash = _snapshot(
            connection, user_id=user_id, organization_id=organization_id, catalogue_id=catalogue_id
        )
        before_payload = json.loads(json.dumps(result.model_dump(mode="json")))
        document = canonical_document_from_result(result)
        path, name, description, category_name, source_ref, restaurant_name = _item_at(document, request.path)
        operation = classify_prompt(prompt, request.operation)
        usable = is_usable_image_ref(source_ref)
        if operation in OPERATIONS_REQUIRING_SOURCE and not usable:
            if operation == "edit":
                operation = "generate_image"
            else:
                raise MediaUnsupported("This operation requires an existing usable source image.")
        if operation == "generate_image" and usable:
            raise MediaUnsupported("Generate Image is for items without a usable photo.")
        if operation in {"generate_image", "image_to_video"} and not prompt:
            prompt = assist_prompt(
                kind="image_to_video" if operation == "image_to_video" else "edit",
                name=name,
                description=description,
                current_prompt=None,
            )
        source_bytes = None
        if usable and source_ref:
            source_bytes = load_image_bytes(source_ref, catalogue_id=catalogue_id)
        snapshot_hash = source_snapshot_hash(source_bytes, source_ref)
        refs_meta = select_reference_images(document, target_path=path, target_category=category_name)
        engine = provider or _provider_factory()
        provider_id = getattr(engine, "provider_id", PROVIDER_ID)
        key = request_key(
            {
                "catalogue_id": catalogue_id,
                "organization_id": organization_id,
                "user_id": user_id,
                "source_head_revision": revision,
                "source_state_hash": state_hash,
                "path": path,
                "operation": operation,
                "prompt": prompt,
                "source_snapshot_hash": snapshot_hash,
                "provider": provider_id,
                "engine": MEDIA_ENGINE_VERSION,
                "parent_candidate_id": request.parent_candidate_id,
                "revision_ordinal": request.revision_ordinal,
                "crop": None if request.crop is None else request.crop.model_dump(),
                "blur": None if request.blur is None else request.blur.model_dump(),
                "expand": None if request.expand is None else request.expand.model_dump(),
            }
        )
        claim_token = new_id()
        payload = {
            "prompt": prompt,
            "proposal_id": request.proposal_id,
            "source_ref": source_ref,
            "source_snapshot_hash": snapshot_hash,
            "original_artifact_id": None,
            "active_candidate_id": None,
            "candidates": [],
            "reference_paths": [item.path for item in refs_meta],
            "error": None,
            "item_name": name,
            "description": description,
            "restaurant_name": restaurant_name,
        }
        role, job_id, _existing_payload = _claim_job(
            connection,
            key=key,
            user_id=user_id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
            revision=revision,
            state_hash=state_hash,
            path=path,
            operation=operation,
            claim_token=claim_token,
            payload=payload,
        )
        if role == "existing" and job_id:
            row = get_owned_job(
                connection,
                job_id=job_id,
                catalogue_id=catalogue_id,
                organization_id=organization_id,
                user_id=user_id,
            )
            assert row is not None
            job = row_to_job(row, current_revision=revision, current_hash=state_hash, replay=True)
            after = json.loads(connection.execute("SELECT payload FROM catalogues WHERE id = ?", (catalogue_id,)).fetchone()["payload"])
            if after != before_payload:
                raise RuntimeError("Phase 7 mutated catalogues.payload")
            return job
        if role == "wait":
            deadline = time.monotonic() + WAIT_SECONDS
            while time.monotonic() < deadline:
                time.sleep(0.05)
                row = get_job_by_key(connection, key)
                if row is not None and row["status"] != RESERVATION_STATUS:
                    return row_to_job(row, current_revision=revision, current_hash=state_hash, replay=True)
            raise MediaUnsupported("Media generation is already in progress for this request.")
        assert job_id is not None
        try:
            original_id = None
            if source_bytes is not None:
                begin_immediate(connection)
                try:
                    original_type, _suffix = _sniff_image_type(source_bytes)
                    original_id = _write_artifact(
                        connection,
                        user_id=user_id,
                        organization_id=organization_id,
                        catalogue_id=catalogue_id,
                        job_id=job_id,
                        kind="original",
                        content_type=original_type,
                        data=source_bytes,
                    )
                    connection.execute("COMMIT")
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
            ref_bytes: list[bytes] = []
            if operation == "generate_image":
                for ref in refs_meta:
                    try:
                        ref_bytes.append(load_image_bytes(ref.image_url, catalogue_id=catalogue_id))
                    except MediaSourceError:
                        continue
            result_media = engine.transform(
                ProviderRequest(
                    operation=operation,
                    source=source_bytes,
                    prompt=prompt,
                    item_name=name,
                    description=description,
                    restaurant_name=restaurant_name,
                    references=ref_bytes,
                    crop=request.crop,
                    blur=request.blur,
                    expand=request.expand,
                )
            )
            begin_immediate(connection)
            try:
                current = get_owned_job(
                    connection,
                    job_id=job_id,
                    catalogue_id=catalogue_id,
                    organization_id=organization_id,
                    user_id=user_id,
                )
                if current is None or current["cancel_requested"]:
                    cas_fail_or_cancel(
                        connection,
                        job_id=job_id,
                        claim_token=claim_token,
                        status="CANCELLED",
                        payload={**payload, "error": "Cancelled", "original_artifact_id": original_id},
                    )
                    _clear_running_if_owner(
                        connection,
                        catalogue_id=catalogue_id,
                        user_id=user_id,
                        organization_id=organization_id,
                        path=path,
                        job_id=job_id,
                        original_artifact_id=original_id,
                        clear_active=False,
                    )
                    connection.execute("COMMIT")
                    row = get_owned_job(
                        connection,
                        job_id=job_id,
                        catalogue_id=catalogue_id,
                        organization_id=organization_id,
                        user_id=user_id,
                    )
                    assert row is not None
                    return row_to_job(row, current_revision=revision, current_hash=state_hash)
                live_revision = head_revision(connection, catalogue_id)
                live_hash = graded_state_hash(
                    result.__class__.model_validate(
                        json.loads(
                            connection.execute("SELECT payload FROM catalogues WHERE id = ?", (catalogue_id,)).fetchone()[
                                "payload"
                            ]
                        )
                    )
                )
                if live_revision != revision or live_hash != state_hash:
                    cas_fail_or_cancel(
                        connection,
                        job_id=job_id,
                        claim_token=claim_token,
                        status="STALE",
                        payload={**payload, "error": "Catalogue changed during generation.", "original_artifact_id": original_id},
                    )
                    _clear_running_if_owner(
                        connection,
                        catalogue_id=catalogue_id,
                        user_id=user_id,
                        organization_id=organization_id,
                        path=path,
                        job_id=job_id,
                        original_artifact_id=original_id,
                        clear_active=False,
                    )
                    connection.execute("COMMIT")
                    row = get_owned_job(
                        connection,
                        job_id=job_id,
                        catalogue_id=catalogue_id,
                        organization_id=organization_id,
                        user_id=user_id,
                    )
                    assert row is not None
                    return row_to_job(row, current_revision=revision, current_hash=state_hash)
                kind = "video" if result_media.media_kind == "video" else "candidate"
                candidate_artifact = _write_artifact(
                    connection,
                    user_id=user_id,
                    organization_id=organization_id,
                    catalogue_id=catalogue_id,
                    job_id=job_id,
                    kind=kind,
                    content_type=result_media.content_type,
                    data=result_media.data,
                )
                candidate = {
                    "id": new_id(),
                    "parent_id": request.parent_candidate_id,
                    "operation": operation,
                    "prompt": prompt,
                    "artifact_id": candidate_artifact,
                    "content_type": result_media.content_type,
                    "media_kind": result_media.media_kind,
                    "provider": (
                        engine.provider_id_for(operation)
                        if hasattr(engine, "provider_id_for")
                        else getattr(engine, "provider_id", PROVIDER_ID)
                    ),
                    "created_at": utcnow(),
                }
                final_payload = {
                    **payload,
                    "original_artifact_id": original_id,
                    "active_candidate_id": candidate["id"],
                    "candidates": [candidate],
                }
                accepted = cas_finish(
                    connection,
                    job_id=job_id,
                    claim_token=claim_token,
                    status="READY",
                    payload=final_payload,
                )
                space = get_workspace(
                    connection,
                    catalogue_id=catalogue_id,
                    user_id=user_id,
                    organization_id=organization_id,
                    path=path,
                )
                still_runner = space is not None and space["running_job_id"] == job_id
                if accepted and still_runner:
                    upsert_workspace(
                        connection,
                        catalogue_id=catalogue_id,
                        user_id=user_id,
                        organization_id=organization_id,
                        path=path,
                        active_job_id=job_id,
                        active_candidate_id=candidate["id"],
                        original_artifact_id=original_id,
                        running_job_id=None,
                    )
                elif not accepted:
                    latest = get_owned_job(
                        connection,
                        job_id=job_id,
                        catalogue_id=catalogue_id,
                        organization_id=organization_id,
                        user_id=user_id,
                    )
                    if latest is not None and latest["claim_token"] == claim_token:
                        cas_fail_or_cancel(
                            connection,
                            job_id=job_id,
                            claim_token=claim_token,
                            status="CANCELLED",
                            payload={**payload, "error": "Cancelled before activation.", "original_artifact_id": original_id},
                        )
                        _clear_running_if_owner(
                            connection,
                            catalogue_id=catalogue_id,
                            user_id=user_id,
                            organization_id=organization_id,
                            path=path,
                            job_id=job_id,
                            original_artifact_id=original_id,
                            clear_active=False,
                        )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        except (MediaProviderError, MediaSourceError, PromptRejected) as exc:
            begin_immediate(connection)
            try:
                cas_fail_or_cancel(
                    connection,
                    job_id=job_id,
                    claim_token=claim_token,
                    status="FAILED",
                    payload={
                        **payload,
                        "error": safe_job_error(exc, operation=operation),
                        "original_artifact_id": original_id,
                    },
                )
                _clear_running_if_owner(
                    connection,
                    catalogue_id=catalogue_id,
                    user_id=user_id,
                    organization_id=organization_id,
                    path=path,
                    job_id=job_id,
                    original_artifact_id=original_id,
                    clear_active=False,
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        except Exception as exc:
            begin_immediate(connection)
            try:
                cas_fail_or_cancel(
                    connection,
                    job_id=job_id,
                    claim_token=claim_token,
                    status="FAILED",
                    payload={**payload, "error": "Media generation failed.", "original_artifact_id": original_id},
                )
                _clear_running_if_owner(
                    connection,
                    catalogue_id=catalogue_id,
                    user_id=user_id,
                    organization_id=organization_id,
                    path=path,
                    job_id=job_id,
                    original_artifact_id=original_id,
                    clear_active=False,
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
            raise MediaUnsupported("Media generation failed.") from exc
        row = get_owned_job(
            connection,
            job_id=job_id,
            catalogue_id=catalogue_id,
            organization_id=organization_id,
            user_id=user_id,
        )
        assert row is not None
        after = json.loads(connection.execute("SELECT payload FROM catalogues WHERE id = ?", (catalogue_id,)).fetchone()["payload"])
        if after != before_payload:
            raise RuntimeError("Phase 7 mutated catalogues.payload")
        return row_to_job(row, current_revision=revision, current_hash=state_hash)
    finally:
        connection.close()


def cancel_media_job(*, user_id: str, organization_id: str, catalogue_id: str, job_id: str) -> MediaJob | None:
    connection = connect()
    try:
        _result, revision, state_hash = _snapshot(
            connection, user_id=user_id, organization_id=organization_id, catalogue_id=catalogue_id
        )
        begin_immediate(connection)
        try:
            row = get_owned_job(
                connection,
                job_id=job_id,
                catalogue_id=catalogue_id,
                organization_id=organization_id,
                user_id=user_id,
            )
            if row is None:
                connection.execute("COMMIT")
                return None
            updated = request_cancel(
                connection,
                job_id=job_id,
                user_id=user_id,
                organization_id=organization_id,
                catalogue_id=catalogue_id,
            )
            _clear_running_if_owner(
                connection,
                catalogue_id=catalogue_id,
                user_id=user_id,
                organization_id=organization_id,
                path=row["path"],
                job_id=job_id,
                original_artifact_id=json.loads(row["payload"]).get("original_artifact_id"),
                clear_active=False,
            )
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
        assert updated is not None
        return row_to_job(updated, current_revision=revision, current_hash=state_hash)
    finally:
        connection.close()


def revert_media_workspace(
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
    path: str,
    to: str = "original",
) -> MediaJob | None:
    connection = connect()
    try:
        result, revision, state_hash = _snapshot(
            connection, user_id=user_id, organization_id=organization_id, catalogue_id=catalogue_id
        )
        document = canonical_document_from_result(result)
        path, *_rest = _item_at(document, path)
        begin_immediate(connection)
        try:
            space = get_workspace(
                connection,
                catalogue_id=catalogue_id,
                user_id=user_id,
                organization_id=organization_id,
                path=path,
            )
            cancel_generating_for_path(
                connection,
                catalogue_id=catalogue_id,
                user_id=user_id,
                organization_id=organization_id,
                path=path,
            )
            active_job = None if space is None else space["active_job_id"]
            original_id = None if space is None else space["original_artifact_id"]
            candidate_id = None if to == "original" else to
            if active_job:
                job_row = get_owned_job(
                    connection,
                    job_id=active_job,
                    catalogue_id=catalogue_id,
                    organization_id=organization_id,
                    user_id=user_id,
                )
                if job_row is not None:
                    payload = json.loads(job_row["payload"])
                    payload["active_candidate_id"] = None if to == "original" else to
                    connection.execute(
                        "UPDATE catalogue_media_jobs SET payload = ?, updated_at = ? WHERE id = ?",
                        (json.dumps(payload, ensure_ascii=False), utcnow(), active_job),
                    )
                    original_id = payload.get("original_artifact_id") or original_id
            upsert_workspace(
                connection,
                catalogue_id=catalogue_id,
                user_id=user_id,
                organization_id=organization_id,
                path=path,
                active_job_id=None if to == "original" else active_job,
                active_candidate_id=candidate_id,
                original_artifact_id=original_id,
                running_job_id=None,
            )
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
        if active_job:
            row = get_owned_job(
                connection,
                job_id=active_job,
                catalogue_id=catalogue_id,
                organization_id=organization_id,
                user_id=user_id,
            )
            if row is not None:
                return row_to_job(row, current_revision=revision, current_hash=state_hash)
        return None
    finally:
        connection.close()


def load_artifact_bytes(
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
    artefact_id: str,
) -> tuple[bytes, str]:
    connection = connect()
    try:
        _snapshot(connection, user_id=user_id, organization_id=organization_id, catalogue_id=catalogue_id)
        row = get_artifact(
            connection,
            artefact_id=artefact_id,
            catalogue_id=catalogue_id,
            user_id=user_id,
            organization_id=organization_id,
        )
        if row is None:
            raise KeyError("Media artifact not found.")
        return read_artifact_file(row["rel_path"]), str(row["content_type"])
    finally:
        connection.close()


def apply_media_job(
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
    job_id: str,
    candidate_id: str | None = None,
) -> MediaApplyResult:
    from backend.improvement.apply import ApplyRejected, set_media_field
    from backend.services.grading_service import grade_catalogue
    from backend.store import get_catalogue, update_catalogue
    from scraper.swiggy.assets import assets_root

    stored = get_catalogue(user_id, catalogue_id, organization_id)
    if stored is None:
        raise KeyError("Catalogue not found for this restaurant organization.")
    job = get_media_job(
        user_id=user_id,
        organization_id=organization_id,
        catalogue_id=catalogue_id,
        job_id=job_id,
    )
    if job is None:
        raise LookupError("Media job not found.")
    if job.status == "APPLIED":
        from backend.improvement.apply import value_at_path

        current = value_at_path(stored.result, job.path)
        return MediaApplyResult(
            job=job,
            catalogue_url=str(current or ""),
            grade_letter=None,
            grade_score=None,
        )
    if job.status != "READY" or not job.candidates:
        raise MediaUnsupported("This media job has no ready candidate to apply.")
    from backend.history.compare import load_snapshot, regrade_snapshot
    from backend.history.service import record_field_change

    before = load_snapshot(user_id=user_id, organization_id=organization_id, catalogue_id=catalogue_id)
    candidate = next((row for row in job.candidates if row.id == (candidate_id or job.active_candidate_id)), None)
    if candidate is None:
        candidate = job.candidates[0]
    data, content_type = load_artifact_bytes(
        user_id=user_id,
        organization_id=organization_id,
        catalogue_id=catalogue_id,
        artefact_id=candidate.artifact_id,
    )
    suffix = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "video/mp4": ".mp4",
        "video/webm": ".webm",
    }.get(content_type, ".bin")
    dest_dir = assets_root() / catalogue_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = f"applied-{candidate.artifact_id}{suffix}"
    (dest_dir / filename).write_bytes(data)
    url = f"/catalogue-assets/{catalogue_id}/{filename}"
    video = candidate.media_kind == "video" or content_type.startswith("video/")
    patched = set_media_field(stored.result, job.path, url, video=video)
    saved = update_catalogue(
        user_id=user_id,
        catalogue_id=catalogue_id,
        organization_id=organization_id,
        result=patched,
    )
    if saved is None:
        raise KeyError("Catalogue not found for this restaurant organization.")
    applied_job = job.model_copy(update={"status": "APPLIED"})
    connection = connect()
    try:
        begin_immediate(connection)
        ok = cas_apply(
            connection,
            job_id=job.id,
            user_id=user_id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
        )
        connection.execute("COMMIT" if ok else "ROLLBACK")
    except Exception:
        try:
            connection.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        connection.close()
    if not ok:
        latest = get_media_job(
            user_id=user_id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
            job_id=job_id,
        )
        if latest is not None and latest.status == "APPLIED":
            return MediaApplyResult(
                job=latest,
                catalogue_url=url,
                grade_letter=None,
                grade_score=None,
            )
        raise MediaUnsupported("This media job was already resolved.")
    grade_letter = None
    grade_score = None
    after = before
    try:
        graded, after = regrade_snapshot(
            user_id=user_id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
        )
        grade_letter = getattr(graded, "grade", None) if graded is not None else after.letter
        grade_score = getattr(graded, "score", None) if graded is not None else after.score
    except Exception:
        pass
    record_field_change(
        user_id=user_id,
        organization_id=organization_id,
        catalogue_id=catalogue_id,
        source="media",
        operation=job.operation,
        path=job.path,
        before_result=stored.result,
        after_result=saved.result,
        media_job_id=job.id,
        provenance={"media_job_id": job.id, "operation": job.operation},
        before=before,
        after=after,
        source_head_revision=job.source_head_revision,
    )
    return MediaApplyResult(
        job=applied_job,
        catalogue_url=url,
        grade_letter=str(grade_letter) if grade_letter is not None else None,
        grade_score=float(grade_score) if isinstance(grade_score, (int, float)) else None,
    )
