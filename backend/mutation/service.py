"""Phase 10 propose/confirm/apply. Callers must already authorize session + org + catalogue."""

from __future__ import annotations

from datetime import datetime, timezone

from backend.assistant.contract import AssistantTurnResponse
from backend.assistant.links import actions_for_intent
from backend.grading.document import graded_state_hash
from backend.grading.persist import head_revision
from backend.media.contract import MediaJobRequest
from backend.media.service import MediaUnsupported, create_media_job
from backend.mutation.contract import (
    MEDIA_OPS,
    PAYLOAD_OPS,
    MutationConfirmRequest,
    MutationDraft,
    MutationProposalView,
    MutationRecord,
)
from backend.mutation.parse import is_cancel_message, is_confirm_message, parse_mutation_draft
from backend.mutation.patch import PatchRejected, apply_patch, build_patch, display_value
from backend.mutation.persist import (
    begin_immediate,
    cas_status,
    connect,
    expiry_timestamp,
    get_latest_pending,
    get_owned_proposal,
    insert_proposal,
    new_id,
    new_token,
    utcnow,
)
from backend.mutation.quality import polish_description, suggest_labels
from backend.mutation.resolve import ResolvedItem, resolve_category, resolve_item_id, resolve_item_name
from backend.schemas import CatalogCreateResponse, StoredCatalogue
from backend.store import get_catalogue, update_catalogue


class MutationError(Exception):
    def __init__(self, message: str, *, status_code: int = 400, candidates: list[str] | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.candidates = candidates or []


def maybe_handle_turn(
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str | None,
    message: str,
) -> AssistantTurnResponse | None:
    draft = parse_mutation_draft(message)
    confirming = is_confirm_message(message) or is_cancel_message(message)
    if draft is None and not confirming:
        return None
    if not catalogue_id:
        return _response(
            "Which restaurant catalogue should I change? Open a venue, then ask again.",
            intent="clarify",
            catalogue_id="",
        )
    stored = get_catalogue(user_id, catalogue_id, organization_id)
    if stored is None:
        return None
    if confirming:
        pending = _latest_pending(user_id, organization_id, catalogue_id)
        if pending is None:
            return None
        if is_cancel_message(message):
            return cancel_proposal(
                user_id=user_id,
                organization_id=organization_id,
                catalogue_id=catalogue_id,
                proposal_id=pending.id,
                confirm_token=pending.confirm_token,
            )
        return confirm_proposal(
            user_id=user_id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
            proposal_id=pending.id,
            request=MutationConfirmRequest(confirm_token=pending.confirm_token),
        )
    assert draft is not None
    try:
        return propose_mutation(
            user_id=user_id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
            stored=stored,
            draft=draft,
        )
    except MutationError as exc:
        return _clarify(catalogue_id, exc.message, exc.candidates)
    except PatchRejected as exc:
        return _clarify(catalogue_id, str(exc))


def apply_owner_mutation(
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
    draft: MutationDraft,
    item_id: str | None = None,
    source_head_revision: int,
    source_state_hash: str,
) -> StoredCatalogue:
    """Apply one allowlisted payload mutation from Manage Catalogue (UI confirm replaces chat confirm)."""
    if draft.operation in MEDIA_OPS:
        raise MutationError("Image and video changes must be made from Generated Media.", status_code=400)
    if draft.operation not in PAYLOAD_OPS:
        raise MutationError("Unsupported catalogue operation.", status_code=400)
    stored = get_catalogue(user_id, catalogue_id, organization_id)
    if stored is None:
        raise MutationError("Catalogue not found for this restaurant organization.", status_code=404)
    revision, state_hash = _cas_identity(catalogue_id, stored.result)
    if revision != source_head_revision or state_hash != source_state_hash:
        raise MutationError(
            "This catalogue changed since you opened it. Reload and try again.",
            status_code=409,
        )
    forced_item: ResolvedItem | None = None
    if draft.operation != "add_item" and item_id:
        resolution = resolve_item_id(stored.result, item_id)
        if resolution.item is None:
            raise MutationError("Item not found on this catalogue.", status_code=404)
        forced_item = resolution.item
    try:
        item, category_index, target_index, current, proposed, _summary = _plan(
            stored.result,
            draft,
            forced_item=forced_item,
        )
        patch = build_patch(
            stored.result,
            draft,
            item=item,
            category_index=category_index,
            target_category_index=target_index,
        )
    except PatchRejected as exc:
        raise MutationError(str(exc), status_code=400) from exc
    from backend.history.compare import load_snapshot, regrade_snapshot
    from backend.history.service import record_mutation_change

    before_result = stored.result
    before = load_snapshot(user_id=user_id, organization_id=organization_id, catalogue_id=catalogue_id)
    patched = apply_patch(stored.result, patch)
    saved = update_catalogue(
        user_id=user_id,
        catalogue_id=catalogue_id,
        organization_id=organization_id,
        result=patched,
    )
    if saved is None:
        raise MutationError("Catalogue not found for this restaurant organization.", status_code=404)
    record = MutationRecord(
        id=new_id(),
        confirm_token=new_token(),
        user_id=user_id,
        organization_id=organization_id,
        catalogue_id=catalogue_id,
        operation=draft.operation,
        status="APPLIED",
        source_head_revision=revision,
        source_state_hash=state_hash,
        item_id=item.item_id if item else None,
        item_name=item.name if item else draft.item_name,
        category_name=(item.category_name if item else None) or draft.category_name,
        source_category_name=draft.source_category_name,
        target_category_name=draft.target_category_name,
        item_path=item.path if item else None,
        current_value=current,
        proposed_value=proposed,
        patch=patch,
        writes_payload=True,
        expires_at=expiry_timestamp(),
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    _, after = regrade_snapshot(
        user_id=user_id,
        organization_id=organization_id,
        catalogue_id=catalogue_id,
    )
    record_mutation_change(
        user_id=user_id,
        organization_id=organization_id,
        catalogue_id=catalogue_id,
        mutation=record,
        before_result=before_result,
        after_result=saved.result,
        before=before,
        after=after,
        source_head_revision=revision,
    )
    new_revision, new_state_hash = _cas_identity(catalogue_id, saved.result)
    return saved.model_copy(update={"head_revision": new_revision, "state_hash": new_state_hash})


def propose_mutation(
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
    stored: StoredCatalogue,
    draft: MutationDraft,
) -> AssistantTurnResponse:
    item, category_index, target_index, current, proposed, summary = _plan(stored.result, draft)
    patch = build_patch(
        stored.result,
        draft,
        item=item,
        category_index=category_index,
        target_category_index=target_index,
    )
    revision, state_hash = _cas_identity(catalogue_id, stored.result)
    record = MutationRecord(
        id=new_id(),
        confirm_token=new_token(),
        user_id=user_id,
        organization_id=organization_id,
        catalogue_id=catalogue_id,
        operation=draft.operation,
        status="PENDING",
        source_head_revision=revision,
        source_state_hash=state_hash,
        item_id=item.item_id if item else None,
        item_name=item.name if item else draft.item_name,
        category_name=(item.category_name if item else None) or draft.category_name,
        source_category_name=draft.source_category_name,
        target_category_name=draft.target_category_name,
        item_path=item.path if item else None,
        current_value=current,
        proposed_value=proposed,
        patch=patch,
        writes_payload=draft.operation in PAYLOAD_OPS,
        expires_at=expiry_timestamp(),
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    connection = connect()
    try:
        begin_immediate(connection)
        insert_proposal(connection, record)
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()
    return _response(
        _pending_message(record, summary),
        intent="propose_mutation",
        catalogue_id=catalogue_id,
        proposal=_view(record, include_token=True),
        item_path=record.item_path,
    )


def confirm_proposal(
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
    proposal_id: str,
    request: MutationConfirmRequest,
) -> AssistantTurnResponse:
    stored = get_catalogue(user_id, catalogue_id, organization_id)
    if stored is None:
        raise MutationError("Catalogue not found for this restaurant organization.", status_code=404)
    connection = connect()
    try:
        record = get_owned_proposal(
            connection,
            proposal_id=proposal_id,
            user_id=user_id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
        )
    finally:
        connection.close()
    if record is None:
        raise MutationError("Mutation proposal not found.", status_code=404)
    if record.confirm_token != request.confirm_token:
        raise MutationError("Confirmation token is invalid.", status_code=403)
    if record.status == "APPLIED":
        return _applied(record, catalogue_id, replay=True)
    if record.status in {"CANCELLED", "STALE", "EXPIRED"}:
        return _response(
            _status_message(record),
            intent="propose_mutation",
            catalogue_id=catalogue_id,
            proposal=_view(record, include_token=False),
        )
    if _is_expired(record.expires_at):
        return _finalize_status(record, "EXPIRED", catalogue_id, user_id=user_id, organization_id=organization_id)
    revision, state_hash = _cas_identity(catalogue_id, stored.result)
    if revision != record.source_head_revision or state_hash != record.source_state_hash:
        return _finalize_status(record, "STALE", catalogue_id, user_id=user_id, organization_id=organization_id)
    try:
        from backend.history.compare import load_snapshot, regrade_snapshot
        from backend.history.service import record_mutation_change

        media_job_id = None
        before_result = stored.result
        before = None
        if record.operation not in MEDIA_OPS:
            before = load_snapshot(user_id=user_id, organization_id=organization_id, catalogue_id=catalogue_id)
        saved = None
        if record.operation in MEDIA_OPS:
            media_job_id = _start_media(user_id, organization_id, catalogue_id, record)
        else:
            patched = apply_patch(stored.result, record.patch)
            saved = update_catalogue(
                user_id=user_id,
                catalogue_id=catalogue_id,
                organization_id=organization_id,
                result=patched,
            )
            if saved is None:
                raise MutationError("Catalogue not found for this restaurant organization.", status_code=404)
        updated = record.model_copy(
            update={"status": "APPLIED", "media_job_id": media_job_id or record.media_job_id, "updated_at": utcnow()}
        )
        if not _cas_pending(updated, user_id=user_id, organization_id=organization_id, catalogue_id=catalogue_id):
            latest = _reload(updated.id, user_id, organization_id, catalogue_id)
            if latest is not None and latest.status == "APPLIED":
                return _applied(latest, catalogue_id, replay=True)
            raise MutationError("This proposal was already resolved.", status_code=409)
        if saved is not None:
            _, after = regrade_snapshot(
                user_id=user_id,
                organization_id=organization_id,
                catalogue_id=catalogue_id,
            )
            record_mutation_change(
                user_id=user_id,
                organization_id=organization_id,
                catalogue_id=catalogue_id,
                mutation=updated,
                before_result=before_result,
                after_result=saved.result,
                before=before,
                after=after,
                source_head_revision=record.source_head_revision,
            )
        return _applied(updated, catalogue_id, replay=False)
    except (PatchRejected, MediaUnsupported) as exc:
        return _clarify(catalogue_id, str(exc))


def cancel_proposal(
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
    proposal_id: str,
    confirm_token: str,
) -> AssistantTurnResponse:
    connection = connect()
    try:
        begin_immediate(connection)
        record = get_owned_proposal(
            connection,
            proposal_id=proposal_id,
            user_id=user_id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
        )
        if record is None:
            connection.execute("ROLLBACK")
            raise MutationError("Mutation proposal not found.", status_code=404)
        if record.confirm_token != confirm_token:
            connection.execute("ROLLBACK")
            raise MutationError("Confirmation token is invalid.", status_code=403)
        if record.status != "PENDING":
            connection.execute("ROLLBACK")
            return _response(
                _status_message(record),
                intent="propose_mutation",
                catalogue_id=catalogue_id,
                proposal=_view(record, include_token=False),
            )
        updated = record.model_copy(update={"status": "CANCELLED", "updated_at": utcnow()})
        cas_status(
            connection,
            proposal_id=record.id,
            user_id=user_id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
            expected="PENDING",
            record=updated,
        )
        connection.execute("COMMIT")
        return _response(
            "Cancelled. No catalogue changes were made.",
            intent="propose_mutation",
            catalogue_id=catalogue_id,
            proposal=_view(updated, include_token=False),
        )
    except MutationError:
        raise
    except Exception:
        try:
            connection.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        connection.close()


def _cas_pending(record: MutationRecord, *, user_id: str, organization_id: str, catalogue_id: str) -> bool:
    connection = connect()
    try:
        begin_immediate(connection)
        ok = cas_status(
            connection,
            proposal_id=record.id,
            user_id=user_id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
            expected="PENDING",
            record=record,
        )
        connection.execute("COMMIT" if ok else "ROLLBACK")
        return ok
    except Exception:
        try:
            connection.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        connection.close()


def _finalize_status(
    record: MutationRecord,
    status: str,
    catalogue_id: str,
    *,
    user_id: str,
    organization_id: str,
) -> AssistantTurnResponse:
    updated = record.model_copy(update={"status": status, "updated_at": utcnow()})
    _cas_pending(updated, user_id=user_id, organization_id=organization_id, catalogue_id=catalogue_id)
    return _response(
        _status_message(updated),
        intent="propose_mutation",
        catalogue_id=catalogue_id,
        proposal=_view(updated, include_token=False),
    )


def _reload(proposal_id: str, user_id: str, organization_id: str, catalogue_id: str) -> MutationRecord | None:
    connection = connect()
    try:
        return get_owned_proposal(
            connection,
            proposal_id=proposal_id,
            user_id=user_id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
        )
    finally:
        connection.close()


def _plan(
    result: CatalogCreateResponse,
    draft: MutationDraft,
    *,
    forced_item: ResolvedItem | None = None,
) -> tuple[ResolvedItem | None, int | None, int | None, str, str, str]:
    if draft.operation == "add_item":
        category = resolve_category(result, draft.category_name)
        if category.status == "missing_category":
            raise MutationError("Which category should I add that item to?", candidates=list(category.candidates))
        if category.status == "ambiguous_category":
            raise MutationError("Several categories match that name. Which one do you mean?", candidates=list(category.candidates))
        if not draft.item_name:
            raise MutationError("What item should I add?")
        if draft.price is None:
            raise MutationError(f"What price should I set for {draft.item_name}?")
        current = "(none)"
        proposed = f"{draft.item_name} · {display_value('change_price', {'price': draft.price})} · {category.category_name}"
        summary = f"Add {draft.item_name} to {category.category_name}."
        return None, category.category_index, None, current, proposed, summary

    if forced_item is not None:
        item = forced_item
    else:
        hint = draft.category_name or draft.source_category_name
        resolution = resolve_item_name(result, draft.item_name, category_name=hint)
        if resolution.status == "missing_item":
            raise MutationError(f"I couldn't find {draft.item_name or 'that item'} on this catalogue.")
        if resolution.status == "ambiguous_item":
            raise MutationError("Several menu items match that name. Which one do you mean?", candidates=list(resolution.candidates))
        item = resolution.item
        assert item is not None
    target_index = None
    if draft.operation == "move_item":
        target = resolve_category(result, draft.target_category_name)
        if target.category_index is None:
            raise MutationError("I couldn't uniquely identify the destination category.", candidates=list(target.candidates))
        if target.category_index == item.category_index:
            raise MutationError(f"{item.name} is already in {item.category_name}.")
        target_index = target.category_index
    current = display_value(draft.operation, item.item, extra=item.category_name if draft.operation == "move_item" else None)
    if draft.operation == "change_price":
        proposed = display_value("change_price", {"price": draft.price})
        summary = f"Change {item.name} from {current} to {proposed}."
    elif draft.operation == "rename_item":
        proposed = draft.new_item_name or ""
        if _name_taken(result, proposed, item.category_index, except_item_id=item.item_id):
            raise MutationError(f"{item.category_name} already has an item named {proposed}.")
        summary = f"Rename {item.name} to {proposed}."
    elif draft.operation == "update_description":
        proposed = draft.description or polish_description(
            name=item.name,
            category_name=item.category_name,
            description=str(item.item.get("description") or ""),
            labels=item.item.get("labels") if isinstance(item.item.get("labels"), list) else [],
        )
        summary = f"Update the description for {item.name}."
    elif draft.operation == "update_labels":
        labels = draft.labels or suggest_labels(
            name=item.name,
            category_name=item.category_name,
            description=str(item.item.get("description") or ""),
            labels=item.item.get("labels") if isinstance(item.item.get("labels"), list) else [],
        )
        proposed = ", ".join(labels)
        summary = f"Update tags for {item.name}."
    elif draft.operation == "remove_item":
        proposed = f"Remove from {item.category_name}"
        summary = f"Remove {item.name} from {item.category_name}. This deletes the item from the catalogue."
    elif draft.operation == "move_item":
        proposed = draft.target_category_name or ""
        summary = f"Move {item.name} from {item.category_name} to {proposed}."
    elif draft.operation == "improve_image":
        proposed = "Start image job (live catalogue photo will not change)"
        summary = f"Start an image job for {item.name}. The live catalogue image will not be replaced."
    else:
        proposed = "Start video job (live catalogue media will not change)"
        summary = f"Start a video job for {item.name}. The live catalogue will not be updated."
    return item, item.category_index, target_index, current, proposed, summary


def _start_media(user_id: str, organization_id: str, catalogue_id: str, record: MutationRecord) -> str:
    path = record.item_path or str((record.patch or {}).get("path") or "")
    if not path:
        raise MutationError("I couldn't identify the item media path.")
    operation = "generate_image" if record.operation == "improve_image" else "image_to_video"
    try:
        job = create_media_job(
            user_id=user_id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
            request=MediaJobRequest(path=path, operation=operation),
        )
    except MediaUnsupported:
        if operation != "generate_image":
            raise
        job = create_media_job(
            user_id=user_id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
            request=MediaJobRequest(path=path, operation="edit", prompt="Improve food photography quality"),
        )
    return job.id


def _cas_identity(catalogue_id: str, result: CatalogCreateResponse) -> tuple[int, str]:
    connection = connect()
    try:
        return head_revision(connection, catalogue_id), graded_state_hash(result)
    finally:
        connection.close()


def _latest_pending(user_id: str, organization_id: str, catalogue_id: str) -> MutationRecord | None:
    connection = connect()
    try:
        return get_latest_pending(
            connection,
            user_id=user_id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
        )
    finally:
        connection.close()


def _is_expired(expires_at: str) -> bool:
    try:
        expiry = datetime.fromisoformat(expires_at)
    except ValueError:
        return True
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) >= expiry


def _view(record: MutationRecord, *, include_token: bool) -> MutationProposalView:
    return MutationProposalView(
        proposal_id=record.id,
        confirm_token=record.confirm_token if include_token else None,
        operation=record.operation,
        status=record.status,
        summary=_pending_message(record, None) if record.status == "PENDING" else _status_message(record),
        item_name=record.item_name,
        category_name=record.category_name,
        current_value=record.current_value,
        proposed_value=record.proposed_value,
        expires_at=record.expires_at,
        writes_payload=record.writes_payload,
        media_job_id=record.media_job_id,
    )


def _pending_message(record: MutationRecord, summary: str | None) -> str:
    lines = [summary or "Please confirm this catalogue change.", ""]
    if record.item_name:
        lines.append(f"Item: {record.item_name}")
    if record.category_name:
        lines.append(f"Category: {record.category_name}")
    if record.current_value:
        lines.append(f"Current: {record.current_value}")
    if record.proposed_value:
        lines.append(f"Proposed: {record.proposed_value}")
    if record.operation == "remove_item":
        lines.append("This will remove the item from the catalogue.")
    elif record.writes_payload:
        lines.append("No other catalogue fields will be changed.")
    else:
        lines.append("This starts a media job only. The live catalogue image/video will not change.")
    lines.append("Confirm the change or cancel.")
    return "\n".join(lines)


def _status_message(record: MutationRecord) -> str:
    if record.status == "APPLIED" and record.operation == "change_price":
        return f"Changed {record.item_name} from {record.current_value} to {record.proposed_value}."
    if record.status == "APPLIED" and record.operation == "rename_item":
        return f"Renamed {record.current_value} to {record.proposed_value}."
    if record.status == "APPLIED" and record.operation == "move_item":
        return f"Moved {record.item_name} from {record.current_value} to {record.proposed_value}."
    if record.status == "APPLIED" and record.operation == "add_item":
        return f"Added {record.item_name} to {record.category_name}."
    if record.status == "APPLIED" and record.operation == "remove_item":
        return f"Removed {record.item_name} from {record.category_name}."
    if record.status == "APPLIED" and record.operation == "update_description":
        return f"Updated the description for {record.item_name}."
    if record.status == "APPLIED" and record.operation == "update_labels":
        return f"Updated tags for {record.item_name} from {record.current_value} to {record.proposed_value}."
    if record.status == "APPLIED" and record.writes_payload:
        return f"Done. {record.item_name or 'The catalogue'} was updated."
    if record.status == "APPLIED":
        return (
            f"Media job {record.media_job_id} started for {record.item_name or 'this item'}. "
            "The live catalogue image/video has not been changed."
        )
    if record.status == "STALE":
        return "This proposal is stale because the catalogue changed. Ask me again if you still want the edit."
    if record.status == "EXPIRED":
        return "This proposal expired. Ask me again if you still want the edit."
    if record.status == "CANCELLED":
        return "Cancelled. No catalogue changes were made."
    return "This proposal is no longer pending."


def _applied(record: MutationRecord, catalogue_id: str, *, replay: bool) -> AssistantTurnResponse:
    prefix = "Already applied. " if replay else ""
    return _response(
        prefix + _status_message(record),
        intent="propose_mutation",
        catalogue_id=catalogue_id,
        proposal=_view(record, include_token=False),
        item_path=record.item_path,
    )


def _clarify(catalogue_id: str, message: str, candidates: list[str] | None = None) -> AssistantTurnResponse:
    text = message
    if candidates:
        text = message + "\n" + "\n".join(f"- {row}" for row in candidates)
    return _response(text, intent="clarify", catalogue_id=catalogue_id)


def _name_taken(result: CatalogCreateResponse, name: str, category_index: int, *, except_item_id: str) -> bool:
    from backend.review_intel.link import normalize_item_name

    categories = list(result.categories or [])
    if category_index < 0 or category_index >= len(categories) or not isinstance(categories[category_index], dict):
        return False
    needle = normalize_item_name(name)
    for item in categories[category_index].get("items") or []:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("item_id") or item.get("id") or "")
        if item_id == except_item_id:
            continue
        if normalize_item_name(str(item.get("name") or "")) == needle:
            return True
    return False


def _response(
    message: str,
    *,
    intent: str,
    catalogue_id: str,
    proposal: MutationProposalView | None = None,
    item_path: str | None = None,
) -> AssistantTurnResponse:
    action_intent = "open_catalogue"
    if intent == "propose_mutation" and proposal is not None and not proposal.writes_payload:
        action_intent = "open_media"
    elif intent != "propose_mutation":
        action_intent = intent
    try:
        actions = actions_for_intent(action_intent, catalogue_id, item_path=item_path)  # type: ignore[arg-type]
    except Exception:
        actions = []
    return AssistantTurnResponse(
        message=message,
        intent=intent,  # type: ignore[arg-type]
        used_llm=False,
        actions=actions,
        unavailable=None,
        proposal=proposal,
    )


# Aliases for mixed import spellings used by assistant/main.
maybe_handle_turn = maybe_handle_turn
confirm_proposal = confirm_proposal
cancel_proposal = cancel_proposal
