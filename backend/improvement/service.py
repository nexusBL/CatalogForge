"""Phase 6/11 improvement service. Generate/preview proposals; apply is a separate authorized write."""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Callable

from backend.grading.document import canonical_document_from_result, graded_state_hash
from backend.grading.persist import head_revision
from backend.improvement.contract import (
    GeneratorCandidate,
    ImprovementApplyResult,
    ImprovementLine,
    ImprovementLineRequest,
    ImprovementProposal,
    MAX_LABELS,
    MAX_LINES_PER_REQUEST,
    MediaHandoff,
)
from backend.improvement.eligibility import (
    ImprovementUnsupported,
    TooManyImprovementPaths,
    resolve_targets,
)
from backend.improvement.generators.base import ImprovementGenerator
from backend.improvement.generators.ollama import (
    OllamaImprovementGenerator,
    OllamaMalformed,
    OllamaModelUnavailable,
    OllamaTimeout,
    OllamaUnavailable,
    ollama_settings,
)
from backend.improvement.persist import (
    RESERVATION_STATUS,
    begin_immediate,
    cas_proposal_status,
    connect,
    finalize_proposal,
    get_proposal_by_id,
    get_proposal_by_key,
    get_request_row,
    insert_reservation,
    list_proposals,
    new_proposal_id,
    request_key,
    reservation_age_seconds,
    touch_reservation,
    utcnow,
)
from backend.improvement.validate import CandidateRejected, validate_candidate, validate_labels
from backend.services.grade_explain_service import IncompleteGradePayload, get_grade_explanation


def default_generator() -> ImprovementGenerator:
    return OllamaImprovementGenerator()


_generator_factory: Callable[[], ImprovementGenerator] = default_generator


def set_generator_factory(factory: Callable[[], ImprovementGenerator] | None) -> None:
    global _generator_factory
    _generator_factory = factory or default_generator


def _envelope_status(lines: list[ImprovementLine]) -> str:
    if not lines:
        return "FAILED"
    ready = any(line.status == "READY" for line in lines)
    failed = any(line.status == "FAILED" for line in lines)
    if ready and failed:
        return "PARTIAL"
    if ready:
        return "READY"
    return "FAILED"


def _line_from_error(*, path: str, kind: str, check_id: str, finding_id: str, current_value: str | None, why: str, reason: str) -> ImprovementLine:
    return ImprovementLine(
        path=path,
        kind=kind,  # type: ignore[arg-type]
        check_id=check_id,
        finding_id=finding_id,
        current_value=current_value,
        proposed_value=None,
        status="FAILED",
        failure_reason=reason,
        why=why,
    )


def _grounded_description_text(context) -> str | None:
    current = (context.current_value or "").strip()
    if current:
        return current
    name = (context.name or "").strip()
    if not name:
        return None
    category = (context.category_name or "").strip()
    if category and category.casefold() != "menu":
        return f"{name} in {category}."
    return f"{name}."


def _grounded_description_line(context, *, finding_id: str, check_id: str, why: str, reason: str) -> ImprovementLine | None:
    if context.kind != "description":
        return None
    text = _grounded_description_text(context)
    if not text:
        return None
    try:
        proposed = validate_candidate(context, GeneratorCandidate(proposed_value=text))
    except CandidateRejected:
        return None
    return ImprovementLine(
        path=context.path,
        kind="description",
        check_id=check_id,
        finding_id=finding_id,
        current_value=context.current_value,
        proposed_value=proposed,
        status="READY",
        why=why,
        provenance={
            "generator": "deterministic_facts",
            "mode": "GROUNDED_FALLBACK",
            "fallback_from": reason,
        },
    )


def _generate_line(generator: ImprovementGenerator, context, *, finding_id: str, check_id: str, why: str) -> ImprovementLine:
    if context.kind == "media_handoff":
        current = context.current_value
        return ImprovementLine(
            path=context.path,
            kind="media_handoff",
            check_id=check_id,
            finding_id=finding_id,
            current_value=current,
            proposed_value="Phase 7 image/video improvement handoff",
            media_handoff=MediaHandoff(
                phase7_required=True,
                media_type=context.media_type or "image",
                capability="image_improvement",
                current_ref=context.image_url or current,
            ),
            status="READY",
            why=why,
            provenance={"generator": "none", "phase7_required": True},
        )
    if context.kind == "item_price":
        if not context.original_price:
            return _line_from_error(
                path=context.path,
                kind=context.kind,
                check_id=check_id,
                finding_id=finding_id,
                current_value=context.current_value,
                why=why,
                reason="Cannot invent a selling price",
            )
        return ImprovementLine(
            path=context.path,
            kind="item_price",
            check_id=check_id,
            finding_id=finding_id,
            current_value=context.current_value,
            proposed_value=context.original_price,
            status="READY",
            why=why,
            provenance={"generator": "deterministic", "source": "original_price"},
        )
    if context.kind == "labels" and not context.needs_ollama:
        food = (context.food_type or "").strip()
        proposed = list(context.labels)
        if food and food.casefold() not in {label.casefold() for label in proposed}:
            proposed.append(food)
        try:
            labels = validate_labels(context, proposed)
        except CandidateRejected as exc:
            return _line_from_error(
                path=context.path,
                kind=context.kind,
                check_id=check_id,
                finding_id=finding_id,
                current_value=context.current_value,
                why=why,
                reason=exc.reason,
            )
        return ImprovementLine(
            path=context.path,
            kind="labels",
            check_id=check_id,
            finding_id=finding_id,
            current_value=context.current_value,
            proposed_value=", ".join(labels),
            proposed_labels=labels,
            status="READY",
            why=why,
            provenance={"generator": "deterministic", "source": "food_type"},
        )
    try:
        candidate = generator.generate(context, why=why)
    except (OllamaTimeout, OllamaModelUnavailable, OllamaUnavailable, OllamaMalformed) as exc:
        reason = {
            OllamaTimeout: "Ollama timeout",
            OllamaModelUnavailable: "Ollama model unavailable",
            OllamaUnavailable: "Ollama unavailable",
            OllamaMalformed: "malformed JSON",
        }[type(exc)]
        grounded = _grounded_description_line(
            context, finding_id=finding_id, check_id=check_id, why=why, reason=reason
        )
        if grounded is not None:
            return grounded
        return _line_from_error(
            path=context.path,
            kind=context.kind,
            check_id=check_id,
            finding_id=finding_id,
            current_value=context.current_value,
            why=why,
            reason=reason,
        )
    except CandidateRejected as exc:
        return _line_from_error(
            path=context.path,
            kind=context.kind,
            check_id=check_id,
            finding_id=finding_id,
            current_value=context.current_value,
            why=why,
            reason=exc.reason,
        )
    if context.kind == "labels":
        raw_labels = candidate.proposed_labels
        if raw_labels is None:
            return _line_from_error(
                path=context.path,
                kind=context.kind,
                check_id=check_id,
                finding_id=finding_id,
                current_value=context.current_value,
                why=why,
                reason="malformed JSON",
            )
        food = (context.food_type or "").strip()
        canonical: list[str] = []
        if food:
            canonical.append(food)
        for lbl in context.labels:
            if lbl and str(lbl).strip() and str(lbl).strip().casefold() not in {c.casefold() for c in canonical}:
                canonical.append(str(lbl).strip())
        merged = canonical + list(raw_labels)
        # Deduplicate preserving order and cap at MAX_LABELS
        seen_labels: set[str] = set()
        deduped: list[str] = []
        for lbl in merged:
            lbl_clean = str(lbl).strip()
            if lbl_clean and lbl_clean.casefold() not in seen_labels:
                seen_labels.add(lbl_clean.casefold())
                deduped.append(lbl_clean)
        deduped = deduped[:MAX_LABELS]
        try:
            labels = validate_labels(context, deduped)
        except CandidateRejected as exc:
            return _line_from_error(
                path=context.path,
                kind=context.kind,
                check_id=check_id,
                finding_id=finding_id,
                current_value=context.current_value,
                why=why,
                reason=exc.reason,
            )
        mode = "OWNER_REFINED" if context.instruction else "LLM_GENERATED"
        prov = {
            "generator": "ollama",
            "mode": mode,
            "model": candidate.model,
        }
        if context.instruction:
            prov["owner_instruction"] = context.instruction
        return ImprovementLine(
            path=context.path,
            kind="labels",
            check_id=check_id,
            finding_id=finding_id,
            current_value=context.current_value,
            proposed_value=", ".join(labels),
            proposed_labels=labels,
            status="READY",
            why=why,
            provenance=prov,
        )
    try:
        proposed = validate_candidate(context, candidate)
    except CandidateRejected as exc:
        return _line_from_error(
            path=context.path,
            kind=context.kind,
            check_id=check_id,
            finding_id=finding_id,
            current_value=context.current_value,
            why=why,
            reason=exc.reason,
        )
    mode = "OWNER_REFINED" if context.instruction else "LLM_GENERATED"
    prov = {
        "generator": "ollama",
        "mode": mode,
        "model": candidate.model,
        "model_digest": candidate.model_digest,
        "elapsed_ms": candidate.elapsed_ms,
    }
    if context.instruction:
        prov["owner_instruction"] = context.instruction
    return ImprovementLine(
        path=context.path,
        kind=context.kind,
        check_id=check_id,
        finding_id=finding_id,
        current_value=context.current_value,
        proposed_value=proposed,
        status="READY",
        failure_reason=None,
        why=why,
        provenance=prov,
    )


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
    revision = head_revision(connection, catalogue_id)
    state_hash = graded_state_hash(result)
    return result, revision, state_hash


def _generation_wait_seconds() -> float:
    _url, _model, timeout = ollama_settings()
    return float(MAX_LINES_PER_REQUEST * timeout + 5)


def _wait_for_complete(
    *,
    request_key_value: str,
    organization_id: str,
    current_revision: int,
    current_hash: str,
    timeout_s: float,
) -> ImprovementProposal | None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        connection = connect()
        try:
            found = get_proposal_by_key(
                connection,
                request_key_value=request_key_value,
                organization_id=organization_id,
                current_revision=current_revision,
                current_hash=current_hash,
            )
            if found is not None:
                return found
            row = get_request_row(connection, request_key_value)
            if row is None:
                return None
            if row["status"] != RESERVATION_STATUS:
                return get_proposal_by_key(
                    connection,
                    request_key_value=request_key_value,
                    organization_id=organization_id,
                    current_revision=current_revision,
                    current_hash=current_hash,
                )
            if reservation_age_seconds(row["created_at"]) > timeout_s:
                return None
        finally:
            connection.close()
        time.sleep(0.05)
    return None


def _claim_generation(
    connection: sqlite3.Connection,
    *,
    request_key_value: str,
    user_id: str,
    reservation: ImprovementProposal,
    timeout_s: float,
) -> tuple[str, ImprovementProposal | None]:
    begin_immediate(connection)
    try:
        row = get_request_row(connection, request_key_value)
        if row is None:
            insert_reservation(
                connection,
                request_key_value=request_key_value,
                user_id=user_id,
                proposal=reservation,
            )
            connection.execute("COMMIT")
            return "owner", None
        if row["organization_id"] != reservation.organization_id:
            raise KeyError("Catalogue not found for this restaurant organization.")
        if row["status"] != RESERVATION_STATUS:
            if row["status"] in {"READY", "PARTIAL"}:
                existing = ImprovementProposal.model_validate(json.loads(row["payload"]))
                existing = existing.model_copy(update={"idempotent_replay": True})
                connection.execute("COMMIT")
                return "existing", existing
            connection.execute(
                "DELETE FROM catalogue_improvement_proposals WHERE request_key = ?",
                (request_key_value,),
            )
            insert_reservation(
                connection,
                request_key_value=request_key_value,
                user_id=user_id,
                proposal=reservation,
            )
            connection.execute("COMMIT")
            return "owner", None
        if reservation_age_seconds(row["created_at"]) > timeout_s:
            touch_reservation(connection, request_key_value)
            connection.execute("COMMIT")
            return "owner", None
        connection.execute("COMMIT")
        return "wait", None
    except sqlite3.IntegrityError:
        connection.execute("ROLLBACK")
        return "wait", None
    except KeyError:
        connection.execute("ROLLBACK")
        raise
    except Exception:
        connection.execute("ROLLBACK")
        raise


def create_improvement(
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
    request: ImprovementLineRequest,
    generator: ImprovementGenerator | None = None,
) -> ImprovementProposal:
    explanation = get_grade_explanation(
        user_id=user_id,
        organization_id=organization_id,
        catalogue_id=catalogue_id,
    )
    if explanation is None:
        from backend.services.grading_service import grade_catalogue
        try:
            grade_catalogue(user_id=user_id, organization_id=organization_id, catalogue_id=catalogue_id)
            explanation = get_grade_explanation(
                user_id=user_id,
                organization_id=organization_id,
                catalogue_id=catalogue_id,
            )
        except Exception:
            explanation = None
    if explanation is None:
        raise LookupError("No completed grade for this catalogue revision.")
    connection = connect()
    try:
        result, revision, state_hash = _snapshot(
            connection, user_id=user_id, organization_id=organization_id, catalogue_id=catalogue_id
        )
        document = canonical_document_from_result(result)
        resolved = resolve_targets(
            document=document,
            explanation=explanation,
            check_id=request.check_id,
            requested_paths=request.paths,
        )
        instruction = (request.instruction or "").strip() or None
        refining_proposal = None
        if request.refining_proposal_id:
            refining_proposal = get_proposal_by_id(
                connection,
                proposal_id=request.refining_proposal_id,
                catalogue_id=catalogue_id,
                organization_id=organization_id,
                user_id=user_id,
                current_revision=revision,
                current_hash=state_hash,
            )

        for target in resolved.targets:
            if instruction:
                target.instruction = instruction
            if refining_proposal:
                line_match = next((l for l in refining_proposal.lines if l.path == target.path), None)
                if line_match and line_match.proposed_value:
                    target.current_proposal_value = line_match.proposed_value

        key = request_key(
            catalogue_id=catalogue_id,
            source_head_revision=revision,
            source_state_hash=state_hash,
            check_id=resolved.check_id,
            paths=[target.path for target in resolved.targets],
            instruction=instruction,
        )
        timeout_s = _generation_wait_seconds()
        reservation = ImprovementProposal(
            id=new_proposal_id(),
            catalogue_id=catalogue_id,
            organization_id=organization_id,
            source_head_revision=revision,
            source_state_hash=state_hash,
            check_id=resolved.check_id,
            finding_id=resolved.finding_id,
            status="FAILED",
            lines=[],
            created_at=utcnow(),
        )
        for _attempt in range(3):
            role, existing = _claim_generation(
                connection,
                request_key_value=key,
                user_id=user_id,
                reservation=reservation,
                timeout_s=timeout_s,
            )
            if role == "existing" and existing is not None:
                if existing.source_head_revision != revision or existing.source_state_hash != state_hash:
                    return existing.model_copy(update={"status": "STALE"})
                return existing
            if role == "wait":
                waited = _wait_for_complete(
                    request_key_value=key,
                    organization_id=organization_id,
                    current_revision=revision,
                    current_hash=state_hash,
                    timeout_s=timeout_s,
                )
                if waited is not None:
                    return waited
                continue
            gen = generator or _generator_factory()
            lines = [
                _generate_line(
                    gen,
                    target,
                    finding_id=resolved.finding_id,
                    check_id=resolved.check_id,
                    why=resolved.why,
                )
                for target in resolved.targets
            ]
            reserved_row = get_request_row(connection, key)
            proposal_id = reserved_row["id"] if reserved_row is not None else reservation.id
            proposal = ImprovementProposal(
                id=str(proposal_id),
                catalogue_id=catalogue_id,
                organization_id=organization_id,
                source_head_revision=revision,
                source_state_hash=state_hash,
                check_id=resolved.check_id,
                finding_id=resolved.finding_id,
                status=_envelope_status(lines),  # type: ignore[arg-type]
                lines=lines,
                created_at=utcnow(),
            )
            begin_immediate(connection)
            try:
                finalize_proposal(connection, request_key_value=key, proposal=proposal)
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
            return proposal
        raise sqlite3.Error("Improvement proposal could not be claimed for generation.")
    finally:
        connection.close()


def get_improvement(
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
    proposal_id: str,
) -> ImprovementProposal | None:
    connection = connect()
    try:
        _result, revision, state_hash = _snapshot(
            connection, user_id=user_id, organization_id=organization_id, catalogue_id=catalogue_id
        )
        return get_proposal_by_id(
            connection,
            proposal_id=proposal_id,
            catalogue_id=catalogue_id,
            organization_id=organization_id,
            user_id=user_id,
            current_revision=revision,
            current_hash=state_hash,
        )
    finally:
        connection.close()


def list_improvements(
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
) -> list[ImprovementProposal]:
    connection = connect()
    try:
        _result, revision, state_hash = _snapshot(
            connection, user_id=user_id, organization_id=organization_id, catalogue_id=catalogue_id
        )
        return list_proposals(
            connection,
            catalogue_id=catalogue_id,
            organization_id=organization_id,
            user_id=user_id,
            current_revision=revision,
            current_hash=state_hash,
        )
    finally:
        connection.close()


def apply_improvement(
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
    proposal_id: str,
) -> ImprovementApplyResult:
    from backend.history.compare import load_snapshot, regrade_snapshot
    from backend.history.service import record_field_change
    from backend.improvement.apply import ApplyRejected, apply_proposal_lines
    from backend.store import get_catalogue, update_catalogue

    stored = get_catalogue(user_id, catalogue_id, organization_id)
    if stored is None:
        raise KeyError("Catalogue not found for this restaurant organization.")
    proposal = get_improvement(
        user_id=user_id,
        organization_id=organization_id,
        catalogue_id=catalogue_id,
        proposal_id=proposal_id,
    )
    if proposal is None:
        raise LookupError("Improvement proposal not found.")
    if proposal.status == "APPLIED":
        return ImprovementApplyResult(proposal=proposal)
    if proposal.status in {"CANCELLED", "FAILED", "STALE"}:
        raise ApplyRejected(f"This proposal cannot be applied ({proposal.status}).")
    if proposal.status not in {"READY", "PARTIAL"}:
        raise ApplyRejected("This proposal is not ready to apply.")
    before_result = stored.result
    before = load_snapshot(user_id=user_id, organization_id=organization_id, catalogue_id=catalogue_id)
    source_revision = proposal.source_head_revision
    patched, applied_paths, skipped_media = apply_proposal_lines(stored.result, proposal)
    saved = update_catalogue(
        user_id=user_id,
        catalogue_id=catalogue_id,
        organization_id=organization_id,
        result=patched,
    )
    if saved is None:
        raise KeyError("Catalogue not found for this restaurant organization.")
    updated = proposal.model_copy(update={"status": "APPLIED"})
    connection = connect()
    try:
        begin_immediate(connection)
        ok = cas_proposal_status(
            connection,
            proposal_id=proposal.id,
            user_id=user_id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
            expected=("READY", "PARTIAL"),
            proposal=updated,
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
        latest = get_improvement(
            user_id=user_id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
            proposal_id=proposal_id,
        )
        if latest is not None and latest.status == "APPLIED":
            return ImprovementApplyResult(
                proposal=latest,
                applied_paths=applied_paths,
                skipped_media_paths=skipped_media,
            )
        raise ApplyRejected("This proposal was already resolved.")
    grade_letter = None
    grade_score = None
    after = before
    try:
        graded, after = regrade_snapshot(
            user_id=user_id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
        )
        grade_letter = getattr(graded, "grade", None) or getattr(graded, "letter", None) or after.letter
        grade_score = getattr(graded, "score", None) if graded is not None else after.score
    except Exception:
        pass
    lines_by_path = {line.path: line for line in proposal.lines}
    for path in applied_paths:
        line = lines_by_path.get(path)
        record_field_change(
            user_id=user_id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
            source="improvement",
            operation=(line.kind if line is not None else "improvement"),
            path=path,
            before_result=before_result,
            after_result=saved.result,
            proposal_id=proposal.id,
            provenance=dict(line.provenance) if line is not None else {},
            before=before,
            after=after,
            source_head_revision=source_revision,
        )
    return ImprovementApplyResult(
        proposal=updated,
        applied_paths=applied_paths,
        skipped_media_paths=skipped_media,
        grade_letter=str(grade_letter) if grade_letter is not None else None,
        grade_score=float(grade_score) if isinstance(grade_score, (int, float)) else None,
    )


def cancel_improvement(
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
    proposal_id: str,
) -> ImprovementProposal:
    from backend.improvement.apply import ApplyRejected

    proposal = get_improvement(
        user_id=user_id,
        organization_id=organization_id,
        catalogue_id=catalogue_id,
        proposal_id=proposal_id,
    )
    if proposal is None:
        raise LookupError("Improvement proposal not found.")
    if proposal.status == "CANCELLED":
        return proposal
    if proposal.status == "APPLIED":
        raise ApplyRejected("This proposal was already applied.")
    if proposal.status not in {"READY", "PARTIAL", "FAILED", "STALE"}:
        raise ApplyRejected("This proposal cannot be cancelled.")
    updated = proposal.model_copy(update={"status": "CANCELLED"})
    connection = connect()
    try:
        begin_immediate(connection)
        ok = cas_proposal_status(
            connection,
            proposal_id=proposal.id,
            user_id=user_id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
            expected=("READY", "PARTIAL", "FAILED", "STALE"),
            proposal=updated,
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
        latest = get_improvement(
            user_id=user_id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
            proposal_id=proposal_id,
        )
        if latest is not None and latest.status == "CANCELLED":
            return latest
        raise ApplyRejected("This proposal was already resolved.")
    return updated


__all__ = [
    "IncompleteGradePayload",
    "ImprovementUnsupported",
    "TooManyImprovementPaths",
    "apply_improvement",
    "cancel_improvement",
    "create_improvement",
    "get_improvement",
    "list_improvements",
    "set_generator_factory",
]
