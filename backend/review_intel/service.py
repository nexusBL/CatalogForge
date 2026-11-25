"""Phase 8 review intelligence service. Preview-only; never writes catalogues.payload."""

from __future__ import annotations

import json
import sqlite3
from typing import Literal, cast

from backend.grading.document import canonical_document_from_result, graded_state_hash
from backend.grading.persist import head_revision
from backend.review_intel.analyze import analyze_reviews, reviews_fingerprint
from backend.review_intel.contract import (
    ALLOWED_INGEST_SOURCE,
    CLAIM_TTL_SECONDS,
    CUSTOMER_INGEST_SOURCE,
    DEFAULT_PAGE_SIZE,
    ENGINE_VERSION,
    MAX_PAGE_SIZE,
    MAX_STORED_REVIEWS,
    CustomerFeedbackRequest,
    CustomerFeedbackResponse,
    ReviewCollectRequest,
    ReviewCollectResponse,
    ReviewIngestItem,
    ReviewIntelligence,
    ReviewListResponse,
    StoredReview,
)
from backend.review_intel.evidence import read_photo, write_photo
from backend.review_intel.persist import (
    RESERVATION_STATUS,
    analysis_from_row,
    analysis_request_key,
    begin_immediate,
    cas_finish_analysis,
    connect,
    count_reviews,
    customer_author_key,
    derived_external_id,
    get_analysis_by_key,
    get_review_by_external,
    get_review_by_photo,
    insert_analysis_reservation,
    insert_review,
    latest_analysis_row,
    list_all_reviews,
    list_review_rows,
    load_catalogue_result,
    new_id,
    reclaim_analysis,
    reservation_age_seconds,
    row_to_review,
    utcnow,
)
from backend.store import get_catalogue


class ReviewSourceUnsupported(ValueError):
    pass


class ReviewMalformed(ValueError):
    pass


class AnalysisInProgress(RuntimeError):
    pass


class StaleAnalysisClaim(RuntimeError):
    pass


class ReviewAnalysisFailed(RuntimeError):
    pass


class ReviewLimitExceeded(ValueError):
    pass


def _fail_analysis(*, analysis_id: str, claim_token: str, placeholder: ReviewIntelligence, reason: str) -> None:
    failed = placeholder.model_copy(update={"status": "FAILED", "failure_reason": reason, "updated_at": utcnow()})
    connection = connect()
    try:
        begin_immediate(connection)
        cas_finish_analysis(
            connection,
            analysis_id=analysis_id,
            claim_token=claim_token,
            analysis=failed,
        )
        connection.execute("COMMIT")
    except Exception:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        connection.close()


def _require_catalogue(user_id: str, organization_id: str, catalogue_id: str):
    stored = get_catalogue(user_id, catalogue_id, organization_id)
    if stored is None:
        raise KeyError("Catalogue not found for this restaurant organization.")
    return stored


def _snapshot(user_id: str, organization_id: str, catalogue_id: str):
    stored = _require_catalogue(user_id, organization_id, catalogue_id)
    connection = connect()
    try:
        revision = head_revision(connection, catalogue_id)
    finally:
        connection.close()
    return stored, revision, graded_state_hash(stored.result)


def collect_reviews(
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
    request: ReviewCollectRequest,
) -> ReviewCollectResponse:
    stored = _require_catalogue(user_id, organization_id, catalogue_id)
    payload_before = json.dumps(stored.result.model_dump(mode="json"), sort_keys=True)
    accepted: list[StoredReview] = []
    duplicates: list[StoredReview] = []
    connection = connect()
    try:
        begin_immediate(connection)
        existing_count = count_reviews(
            connection,
            catalogue_id=catalogue_id,
            user_id=user_id,
            organization_id=organization_id,
        )
        incoming_new = 0
        for item in request.reviews:
            stored_review, duplicate = _upsert_review(
                connection,
                user_id=user_id,
                organization_id=organization_id,
                catalogue_id=catalogue_id,
                item=item,
            )
            if duplicate:
                duplicates.append(stored_review)
            else:
                incoming_new += 1
                if existing_count + incoming_new > MAX_STORED_REVIEWS:
                    raise ReviewLimitExceeded("Review store exceeds the Phase 8 size limit.")
                accepted.append(stored_review)
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()
    after = get_catalogue(user_id, catalogue_id, organization_id)
    if after is None or json.dumps(after.result.model_dump(mode="json"), sort_keys=True) != payload_before:
        raise RuntimeError("Phase 8 mutated catalogues.payload")
    return ReviewCollectResponse(
        accepted=len(accepted),
        duplicate=len(duplicates),
        reviews=accepted + duplicates,
    )


def _upsert_review(
    connection: sqlite3.Connection,
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
    item: ReviewIngestItem,
    source: str | None = None,
    photo_id: str | None = None,
) -> tuple[StoredReview, bool]:
    resolved_source = source or item.source
    if resolved_source not in {ALLOWED_INGEST_SOURCE, CUSTOMER_INGEST_SOURCE}:
        raise ReviewSourceUnsupported("Review collection source is unresolved.")
    if source is None and item.source != ALLOWED_INGEST_SOURCE:
        raise ReviewSourceUnsupported("Review collection source is unresolved.")
    external_id = item.external_id or derived_external_id(
        body=item.body,
        posted_at=item.posted_at,
        author_key=item.author_key,
    )
    existing = get_review_by_external(
        connection,
        catalogue_id=catalogue_id,
        organization_id=organization_id,
        source=resolved_source,
        external_id=external_id,
    )
    if existing is not None:
        review = row_to_review(existing)
        return review.model_copy(update={"duplicate": True}), True
    review = StoredReview(
        id=new_id(),
        catalogue_id=catalogue_id,
        organization_id=organization_id,
        source=cast(Literal["supplied", "customer"], resolved_source),
        external_id=external_id,
        body=item.body,
        posted_at=item.posted_at,
        author_key=item.author_key,
        observed_rating=item.observed_rating,
        photo_id=photo_id,
        created_at=utcnow(),
        duplicate=False,
    )
    try:
        insert_review(connection, user_id=user_id, review=review)
    except sqlite3.IntegrityError:
        raced = get_review_by_external(
            connection,
            catalogue_id=catalogue_id,
            organization_id=organization_id,
            source=resolved_source,
            external_id=external_id,
        )
        if raced is None:
            raise
        return row_to_review(raced).model_copy(update={"duplicate": True}), True
    return review, False


def list_reviews(
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
    offset: int = 0,
    limit: int = DEFAULT_PAGE_SIZE,
) -> ReviewListResponse:
    _require_catalogue(user_id, organization_id, catalogue_id)
    page = max(1, min(int(limit or DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE))
    start = max(0, int(offset or 0))
    connection = connect()
    try:
        total, rows = list_review_rows(
            connection,
            catalogue_id=catalogue_id,
            user_id=user_id,
            organization_id=organization_id,
            limit=page,
            offset=start,
        )
    finally:
        connection.close()
    reviews = [row_to_review(row) for row in rows]
    return ReviewListResponse(
        total=total,
        offset=start,
        limit=page,
        ingest_mode=_list_ingest_mode(reviews),
        reviews=reviews,
    )


def _list_ingest_mode(reviews: list[StoredReview]):
    sources = {row.source for row in reviews}
    if not sources or sources == {ALLOWED_INGEST_SOURCE}:
        return ALLOWED_INGEST_SOURCE
    if sources == {CUSTOMER_INGEST_SOURCE}:
        return CUSTOMER_INGEST_SOURCE
    return "mixed"


def submit_customer_feedback(
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
    request: CustomerFeedbackRequest,
    photo_bytes: bytes | None = None,
) -> CustomerFeedbackResponse:
    stored = _require_catalogue(user_id, organization_id, catalogue_id)
    payload_before = json.dumps(stored.result.model_dump(mode="json"), sort_keys=True)
    author_key = customer_author_key(user_id)
    item = ReviewIngestItem(
        body=request.body,
        external_id=request.external_id,
        author_key=author_key,
        observed_rating=request.observed_rating,
        source=ALLOWED_INGEST_SOURCE,
    )
    photo_id = new_id() if photo_bytes else None
    if photo_bytes is not None:
        from backend.review_intel.evidence import detect_image_type

        detect_image_type(photo_bytes)
    connection = connect()
    try:
        begin_immediate(connection)
        existing_count = count_reviews(
            connection,
            catalogue_id=catalogue_id,
            user_id=user_id,
            organization_id=organization_id,
        )
        pending = get_review_by_external(
            connection,
            catalogue_id=catalogue_id,
            organization_id=organization_id,
            source=CUSTOMER_INGEST_SOURCE,
            external_id=item.external_id
            or derived_external_id(body=item.body, posted_at=item.posted_at, author_key=item.author_key),
        )
        incoming_new = 0 if pending is not None else 1
        if incoming_new and existing_count + incoming_new > MAX_STORED_REVIEWS:
            raise ReviewLimitExceeded("Review store exceeds the Phase 8 size limit.")
        stored_review, duplicate = _upsert_review(
            connection,
            user_id=user_id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
            item=item,
            source=CUSTOMER_INGEST_SOURCE,
            photo_id=None if pending is not None else photo_id,
        )
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()
    if photo_bytes is not None and not stored_review.duplicate and stored_review.photo_id:
        write_photo(
            user_id=user_id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
            photo_id=stored_review.photo_id,
            data=photo_bytes,
        )
    after = get_catalogue(user_id, catalogue_id, organization_id)
    if after is None or json.dumps(after.result.model_dump(mode="json"), sort_keys=True) != payload_before:
        raise RuntimeError("Phase 8 mutated catalogues.payload")
    return CustomerFeedbackResponse(duplicate=stored_review.duplicate, review=stored_review)


def load_customer_photo(
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
    photo_id: str,
) -> tuple[bytes, str]:
    _require_catalogue(user_id, organization_id, catalogue_id)
    connection = connect()
    try:
        row = get_review_by_photo(
            connection,
            catalogue_id=catalogue_id,
            user_id=user_id,
            organization_id=organization_id,
            photo_id=photo_id,
        )
    finally:
        connection.close()
    if row is None:
        raise KeyError("Photo not found.")
    return read_photo(
        user_id=user_id,
        organization_id=organization_id,
        catalogue_id=catalogue_id,
        photo_id=photo_id,
    )


def create_review_intelligence(
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
) -> ReviewIntelligence:
    _require_catalogue(user_id, organization_id, catalogue_id)
    connection = connect()
    try:
        begin_immediate(connection)
        result = load_catalogue_result(
            connection,
            user_id=user_id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
        )
        revision = head_revision(connection, catalogue_id)
        state_hash = graded_state_hash(result)
        payload_before = json.dumps(result.model_dump(mode="json"), sort_keys=True)
        reviews = list_all_reviews(
            connection,
            catalogue_id=catalogue_id,
            user_id=user_id,
            organization_id=organization_id,
        )
        fingerprint = reviews_fingerprint(reviews)
        key = analysis_request_key(
            catalogue_id=catalogue_id,
            source_head_revision=revision,
            source_state_hash=state_hash,
            reviews_fingerprint=fingerprint,
        )
        now = utcnow()
        claim_token = new_id()
        existing = get_analysis_by_key(connection, key)
        placeholder = ReviewIntelligence(
            id=new_id(),
            catalogue_id=catalogue_id,
            organization_id=organization_id,
            engine_version=ENGINE_VERSION,
            source_head_revision=revision,
            source_state_hash=state_hash,
            reviews_fingerprint=fingerprint,
            status="GENERATING",
            review_count=len(reviews),
            created_at=now,
            updated_at=now,
        )
        if existing is not None:
            if existing["organization_id"] != organization_id or existing["user_id"] != user_id:
                connection.execute("ROLLBACK")
                raise KeyError("Catalogue not found for this restaurant organization.")
            if _stealable(existing):
                placeholder = placeholder.model_copy(update={"id": existing["id"], "created_at": existing["created_at"]})
                updated = reclaim_analysis(
                    connection,
                    analysis_id=existing["id"],
                    from_status=existing["status"],
                    claim_token=claim_token,
                    analysis=placeholder,
                )
                if updated != 1:
                    connection.execute("ROLLBACK")
                    raise AnalysisInProgress("Review analysis is already in progress.")
                connection.execute("COMMIT")
            elif existing["status"] == RESERVATION_STATUS:
                connection.execute("ROLLBACK")
                raise AnalysisInProgress("Review analysis is already in progress.")
            else:
                connection.execute("COMMIT")
                return analysis_from_row(
                    existing,
                    current_revision=revision,
                    current_hash=state_hash,
                    current_fingerprint=fingerprint,
                    replay=True,
                )
        else:
            try:
                insert_analysis_reservation(
                    connection,
                    request_key_value=key,
                    user_id=user_id,
                    claim_token=claim_token,
                    analysis=placeholder,
                )
            except sqlite3.IntegrityError:
                raced = get_analysis_by_key(connection, key)
                connection.execute("ROLLBACK")
                if raced is not None and raced["status"] == RESERVATION_STATUS:
                    raise AnalysisInProgress("Review analysis is already in progress.") from None
                if raced is not None and raced["status"] == "READY":
                    return analysis_from_row(
                        raced,
                        current_revision=revision,
                        current_hash=state_hash,
                        current_fingerprint=fingerprint,
                        replay=True,
                    )
                raise AnalysisInProgress("Review analysis is already in progress.") from None
            connection.execute("COMMIT")
    except (KeyError, AnalysisInProgress):
        raise
    except Exception:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        connection.close()

    try:
        document = canonical_document_from_result(result)
        finished = analyze_reviews(
            analysis_id=placeholder.id,
            catalogue_id=catalogue_id,
            organization_id=organization_id,
            source_head_revision=revision,
            source_state_hash=state_hash,
            reviews=reviews,
            document=document,
            created_at=placeholder.created_at,
        )
        finished = finished.model_copy(update={"updated_at": utcnow(), "status": "READY"})
    except Exception:
        _fail_analysis(
            analysis_id=placeholder.id,
            claim_token=claim_token,
            placeholder=placeholder,
            reason="Review analysis could not be completed.",
        )
        raise ReviewAnalysisFailed("Review analysis could not be completed.") from None

    connection = connect()
    try:
        begin_immediate(connection)
        current_result = load_catalogue_result(
            connection,
            user_id=user_id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
        )
        current_revision = head_revision(connection, catalogue_id)
        current_hash = graded_state_hash(current_result)
        current_reviews = list_all_reviews(
            connection,
            catalogue_id=catalogue_id,
            user_id=user_id,
            organization_id=organization_id,
        )
        current_fingerprint = reviews_fingerprint(current_reviews)
        if (
            current_revision != revision
            or current_hash != state_hash
            or current_fingerprint != fingerprint
        ):
            failed = placeholder.model_copy(
                update={
                    "status": "FAILED",
                    "failure_reason": "Catalogue or review set changed during analysis.",
                    "updated_at": utcnow(),
                }
            )
            cas_finish_analysis(
                connection,
                analysis_id=placeholder.id,
                claim_token=claim_token,
                analysis=failed,
            )
            connection.execute("COMMIT")
            raise StaleAnalysisClaim("Catalogue or review set changed during analysis.")
        updated = cas_finish_analysis(
            connection,
            analysis_id=placeholder.id,
            claim_token=claim_token,
            analysis=finished,
        )
        if updated != 1:
            connection.execute("ROLLBACK")
            raise StaleAnalysisClaim("Review analysis claim is no longer owned.")
        connection.execute("COMMIT")
    except StaleAnalysisClaim:
        raise
    except Exception:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        connection.close()

    after = get_catalogue(user_id, catalogue_id, organization_id)
    if after is None or json.dumps(after.result.model_dump(mode="json"), sort_keys=True) != payload_before:
        raise RuntimeError("Phase 8 mutated catalogues.payload")
    return finished


def _stealable(row: sqlite3.Row) -> bool:
    status = row["status"]
    if status == "FAILED":
        return True
    if status != RESERVATION_STATUS:
        return False
    stamp = str(row["updated_at"] or row["created_at"])
    return reservation_age_seconds(stamp) > CLAIM_TTL_SECONDS


def get_review_intelligence(
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
) -> ReviewIntelligence | None:
    _stored, revision, state_hash = _snapshot(user_id, organization_id, catalogue_id)
    connection = connect()
    try:
        reviews = list_all_reviews(
            connection,
            catalogue_id=catalogue_id,
            user_id=user_id,
            organization_id=organization_id,
        )
        fingerprint = reviews_fingerprint(reviews)
        row = latest_analysis_row(
            connection,
            catalogue_id=catalogue_id,
            user_id=user_id,
            organization_id=organization_id,
        )
    finally:
        connection.close()
    if row is None:
        return None
    return analysis_from_row(
        row,
        current_revision=revision,
        current_hash=state_hash,
        current_fingerprint=fingerprint,
    )
