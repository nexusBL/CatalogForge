"""Record approved catalogue writes and owner-confirmed rollback."""

from __future__ import annotations

from typing import Any

from backend.grading.persist import head_revision
from backend.history.compare import load_snapshot, overall_delta, regrade_snapshot, resolved_issue_ids
from backend.history.contract import EditHistoryListResponse, EditHistoryRecord, HistoryRejected
from backend.history.persist import begin_immediate, connect, get_record, insert_record, list_records, new_id, utcnow
from backend.history.restore import apply_restore_spec, current_matches_new_value
from backend.improvement.apply import item_name_at_path, value_at_path
from backend.schemas import CatalogCreateResponse
from backend.store import get_catalogue, update_catalogue

_MUTATION_FIELD = {
    "change_price": "price",
    "rename_item": "name",
    "update_description": "description",
    "update_labels": "labels",
}


def _head(catalogue_id: str) -> int | None:
    connection = connect()
    try:
        return head_revision(connection, catalogue_id)
    except Exception:
        return None
    finally:
        connection.close()


def record_change(
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
    source: str,
    operation: str,
    path: str | None,
    item_name: str | None,
    previous_value: Any,
    new_value: Any,
    restore_spec: dict[str, Any],
    proposal_id: str | None = None,
    media_job_id: str | None = None,
    rolled_back_history_id: str | None = None,
    provenance: dict[str, Any] | None = None,
    before: Any = None,
    after: Any = None,
    source_head_revision: int | None = None,
    result_head_revision: int | None = None,
) -> EditHistoryRecord:
    before = before or load_snapshot(user_id=user_id, organization_id=organization_id, catalogue_id=catalogue_id)
    after = after or before
    record = EditHistoryRecord(
        id=new_id(),
        catalogue_id=catalogue_id,
        user_id=user_id,
        organization_id=organization_id,
        source=source,  # type: ignore[arg-type]
        operation=operation,
        path=path,
        item_name=item_name,
        previous_value=previous_value,
        new_value=new_value,
        restore_spec=restore_spec,
        proposal_id=proposal_id,
        media_job_id=media_job_id,
        rolled_back_history_id=rolled_back_history_id,
        actor=user_id,
        provenance=provenance or {},
        approval_state="APPLIED",
        before_grade_letter=before.letter,
        before_grade_score=before.score,
        after_grade_letter=after.letter,
        after_grade_score=after.score,
        before_section_scores=before.section_scores,
        after_section_scores=after.section_scores,
        resolved_issue_ids=resolved_issue_ids(before, after),
        overall_score_delta=overall_delta(before, after),
        source_head_revision=source_head_revision,
        result_head_revision=result_head_revision if result_head_revision is not None else _head(catalogue_id),
        created_at=utcnow(),
    )
    connection = connect()
    try:
        begin_immediate(connection)
        insert_record(connection, record)
        connection.execute("COMMIT")
    except Exception:
        try:
            connection.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        connection.close()
    return record


def list_history(*, user_id: str, organization_id: str, catalogue_id: str) -> EditHistoryListResponse:
    stored = get_catalogue(user_id, catalogue_id, organization_id)
    if stored is None:
        raise KeyError("Catalogue not found for this restaurant organization.")
    connection = connect()
    try:
        return EditHistoryListResponse(
            records=list_records(connection, catalogue_id=catalogue_id, organization_id=organization_id)
        )
    finally:
        connection.close()


def rollback_history(
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
    history_id: str,
    confirm: bool,
) -> EditHistoryRecord:
    if not confirm:
        raise HistoryRejected("Owner confirmation is required to roll back this catalogue change.")
    stored = get_catalogue(user_id, catalogue_id, organization_id)
    if stored is None:
        raise KeyError("Catalogue not found for this restaurant organization.")
    connection = connect()
    try:
        record = get_record(
            connection,
            history_id=history_id,
            catalogue_id=catalogue_id,
            organization_id=organization_id,
        )
    finally:
        connection.close()
    if record is None:
        raise LookupError("Edit history record not found.")
    if not record.restore_spec:
        raise HistoryRejected("This history record cannot be rolled back.")
    if not current_matches_new_value(stored.result, record.restore_spec, record.new_value):
        raise HistoryRejected(
            "The live catalogue no longer matches this history record. Review the current value before rolling back."
        )
    before = load_snapshot(user_id=user_id, organization_id=organization_id, catalogue_id=catalogue_id)
    source_revision = _head(catalogue_id)
    restored = apply_restore_spec(stored.result, record.restore_spec)
    saved = update_catalogue(
        user_id=user_id,
        catalogue_id=catalogue_id,
        organization_id=organization_id,
        result=restored,
    )
    if saved is None:
        raise KeyError("Catalogue not found for this restaurant organization.")
    _, after = regrade_snapshot(user_id=user_id, organization_id=organization_id, catalogue_id=catalogue_id)
    path = record.path
    previous_value = record.new_value
    new_value = record.previous_value
    if path:
        previous_value = value_at_path(stored.result, path)
        new_value = value_at_path(saved.result, path)
    inverse: dict[str, Any]
    if path:
        inverse = {"op": "set_path", "path": path, "value": previous_value}
    else:
        inverse = {}
    return record_change(
        user_id=user_id,
        organization_id=organization_id,
        catalogue_id=catalogue_id,
        source="rollback",
        operation=f"rollback:{record.operation}",
        path=path,
        item_name=record.item_name,
        previous_value=previous_value,
        new_value=new_value,
        restore_spec=inverse,
        proposal_id=record.proposal_id,
        media_job_id=record.media_job_id,
        rolled_back_history_id=record.id,
        provenance={"rolled_back_history_id": record.id, "original_source": record.source},
        before=before,
        after=after,
        source_head_revision=source_revision,
        result_head_revision=_head(catalogue_id),
    )


def record_field_change(
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
    source: str,
    operation: str,
    path: str,
    before_result: CatalogCreateResponse,
    after_result: CatalogCreateResponse,
    proposal_id: str | None = None,
    media_job_id: str | None = None,
    provenance: dict[str, Any] | None = None,
    before: Any = None,
    after: Any = None,
    source_head_revision: int | None = None,
) -> EditHistoryRecord:
    previous_value = value_at_path(before_result, path)
    new_value = value_at_path(after_result, path)
    return record_change(
        user_id=user_id,
        organization_id=organization_id,
        catalogue_id=catalogue_id,
        source=source,
        operation=operation,
        path=path,
        item_name=item_name_at_path(after_result, path) or item_name_at_path(before_result, path),
        previous_value=previous_value,
        new_value=new_value,
        restore_spec={"op": "set_path", "path": path, "value": previous_value},
        proposal_id=proposal_id,
        media_job_id=media_job_id,
        provenance=provenance,
        before=before,
        after=after,
        source_head_revision=source_head_revision,
        result_head_revision=_head(catalogue_id),
    )


def _mutation_field_path(item_path: str | None, operation: str) -> str | None:
    if not item_path:
        return None
    field = _MUTATION_FIELD.get(operation)
    if not field:
        return item_path
    suffix = f".{field}"
    if item_path.endswith(suffix):
        return item_path
    return f"{item_path}{suffix}"


def record_mutation_change(
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
    mutation,
    before_result: CatalogCreateResponse,
    after_result: CatalogCreateResponse,
    before: Any = None,
    after: Any = None,
    source_head_revision: int | None = None,
) -> EditHistoryRecord:
    operation = mutation.operation
    path = _mutation_field_path(mutation.item_path, operation)
    if operation in {"change_price", "rename_item", "update_description", "update_labels"} and path:
        return record_field_change(
            user_id=user_id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
            source="mutation",
            operation=operation,
            path=path,
            before_result=before_result,
            after_result=after_result,
            proposal_id=mutation.id,
            provenance={"mutation_id": mutation.id},
            before=before,
            after=after,
            source_head_revision=source_head_revision,
        )
    restore_spec: dict[str, Any]
    previous_value: Any = mutation.current_value
    new_value: Any = mutation.proposed_value
    if operation == "add_item":
        added = _first_new_item(before_result, after_result)
        item_id = str((added or {}).get("item_id") or (added or {}).get("id") or "")
        restore_spec = {"op": "remove_item", "item_id": item_id}
        previous_value = None
        new_value = added
    elif operation == "remove_item":
        removed = _item_snapshot(before_result, mutation.item_id)
        category_index, item_index = _item_location(before_result, mutation.item_id)
        restore_spec = {
            "op": "insert_item",
            "category_index": category_index,
            "item_index": item_index,
            "item": removed or {},
        }
        previous_value = removed
        new_value = None
    elif operation == "move_item":
        restore_spec = {
            "op": "move_item",
            "item_id": mutation.item_id,
            "from_index": (mutation.patch or {}).get("to_index"),
            "to_index": (mutation.patch or {}).get("from_index"),
        }
    else:
        restore_spec = {"op": "patch", "patch": mutation.patch or {}}
    return record_change(
        user_id=user_id,
        organization_id=organization_id,
        catalogue_id=catalogue_id,
        source="mutation",
        operation=operation,
        path=path,
        item_name=mutation.item_name,
        previous_value=previous_value,
        new_value=new_value,
        restore_spec=restore_spec,
        proposal_id=mutation.id,
        provenance={"mutation_id": mutation.id},
        before=before,
        after=after,
        source_head_revision=source_head_revision,
        result_head_revision=_head(catalogue_id),
    )


def _item_snapshot(result: CatalogCreateResponse, item_id: str | None) -> dict[str, Any] | None:
    if not item_id:
        return None
    for category in result.categories or []:
        if not isinstance(category, dict):
            continue
        for item in category.get("items") or []:
            if isinstance(item, dict) and str(item.get("item_id") or item.get("id") or "") == item_id:
                return dict(item)
    return None


def _item_location(result: CatalogCreateResponse, item_id: str | None) -> tuple[int, int]:
    if not item_id:
        return 0, 0
    for category_index, category in enumerate(result.categories or []):
        if not isinstance(category, dict):
            continue
        for item_index, item in enumerate(category.get("items") or []):
            if isinstance(item, dict) and str(item.get("item_id") or item.get("id") or "") == item_id:
                return category_index, item_index
    return 0, 0


def _first_new_item(before: CatalogCreateResponse, after: CatalogCreateResponse) -> dict[str, Any] | None:
    before_ids: set[str] = set()
    for category in before.categories or []:
        if not isinstance(category, dict):
            continue
        for item in category.get("items") or []:
            if isinstance(item, dict):
                before_ids.add(str(item.get("item_id") or item.get("id") or item.get("name") or ""))
    for category in after.categories or []:
        if not isinstance(category, dict):
            continue
        for item in category.get("items") or []:
            if not isinstance(item, dict):
                continue
            key = str(item.get("item_id") or item.get("id") or item.get("name") or "")
            if key not in before_ids:
                return dict(item)
    return None
