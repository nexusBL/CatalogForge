from __future__ import annotations

import logging
import os
import sqlite3

from contextlib import asynccontextmanager

from pydantic import ValidationError
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from scraper.swiggy.assets import assets_root

from backend.authz import require_organization_member
from backend.schemas import (
    AuthUser,
    AreaJobActionRequest,
    AreaJobCreateRequest,
    AreaJobStartRequest,
    CatalogCreateRequest,
    CatalogCreateResponse,
    CatalogueListResponse,
    StoredCatalogue,
)
from backend.services.area_service import (
    area_jobs_for,
    cancel_area_job,
    create_area_job,
    delete_area_discovery_job,
    scrape_area_batch,
    start_area_scrape,
)
from backend.services.catalog_service import (
    BrowserAccess,
    FixtureAccess,
    OfficialApiAccess,
    SwiggyAccess,
    create_catalog,
)
from backend.session import require_session
from backend.grading.contract import GradingResult
from backend.grade_explain.contract import GradeExplanation
from backend.platform_eval.adapters import UnsupportedPlatform
from backend.platform_eval.baba_score import load_baba_score
from backend.platform_eval.contract import BabaScore, CatalogueEvaluationResponse
from backend.services.grade_explain_service import IncompleteGradePayload, get_grade_explanation
from backend.improvement.contract import (
    ImprovementApplyResult,
    ImprovementLineRequest,
    ImprovementListResponse,
    ImprovementProposal,
)
from backend.improvement.service import (
    ImprovementUnsupported,
    TooManyImprovementPaths,
    apply_improvement,
    cancel_improvement,
    create_improvement,
    get_improvement,
    list_improvements,
)
from backend.history.contract import EditHistoryListResponse, EditHistoryRecord, HistoryRejected, RollbackRequest
from backend.history.service import list_history, rollback_history
from backend.media.contract import (
    MediaApplyResult,
    MediaJob,
    MediaJobListResponse,
    MediaJobRequest,
    MediaStudioResponse,
    PromptAssistRequest,
    PromptAssistResponse,
    RevertRequest,
)
from backend.media.prompts import PromptRejected
from backend.media.service import (
    MediaUnsupported,
    apply_media_job,
    assist_media_prompt,
    cancel_media_job,
    create_media_job,
    get_media_job,
    get_media_studio,
    list_media_jobs,
    load_artifact_bytes,
    revert_media_workspace,
)
from backend.media.source import MediaSourceError
from backend.review_intel.contract import (
    CustomerFeedbackRequest,
    CustomerFeedbackResponse,
    ReviewCollectRequest,
    ReviewCollectResponse,
    ReviewIntelligence,
    ReviewListResponse,
)
from backend.review_intel.service import (
    AnalysisInProgress,
    ReviewAnalysisFailed,
    ReviewLimitExceeded,
    ReviewMalformed,
    ReviewSourceUnsupported,
    StaleAnalysisClaim,
    collect_reviews,
    create_review_intelligence,
    get_review_intelligence,
    list_reviews,
    load_customer_photo,
    submit_customer_feedback,
)
from backend.assistant.contract import AssistantTurnRequest, AssistantTurnResponse
from backend.assistant.service import AssistantCatalogueMissing, run_turn
from backend.mutation.contract import MutationConfirmRequest, OwnerCatalogueMutationRequest
from backend.mutation.persist import connect as mutation_connect
from backend.mutation.service import MutationError, apply_owner_mutation, cancel_proposal, confirm_proposal
from backend.grading.document import graded_state_hash
from backend.grading.persist import head_revision
from backend.review_intel.evidence import PhotoRejected
from backend.services.grading_service import (
    GradeCancelled,
    GradeInProgress,
    GradePersistenceError,
    StaleClaim,
    get_catalogue_grade,
    grade_catalogue,
)
from backend.services.platform_eval_service import (
    PlatformEvalPersistenceError,
    PlatformEvalStageFailure,
    StaleCatalogueState,
    evaluate_catalogue_platforms,
    get_catalogue_platform_evaluation,
)
from backend.store import delete_catalogue, get_catalogue, list_catalogues, save_catalogue, CatalogueIdentityConflict
from backend.migrate_catalogues import migrate_catalogue_db
from backend.raw_capture import bind_raw_capture

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        result = migrate_catalogue_db()
        if result.get("status") != "applied":
            logger.warning("Catalogue schema migration status=%s detail=%s", result.get("status"), result.get("detail"))
    except Exception:
        logger.exception("Catalogue schema migration failed")
    yield


app = FastAPI(title="CatalogForge", version="0.3.0", lifespan=lifespan)
_assets = assets_root()
_assets.mkdir(parents=True, exist_ok=True)
app.mount("/catalogue-assets", StaticFiles(directory=_assets), name="catalogue-assets")


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


def get_swiggy_access() -> SwiggyAccess:
    mode = os.getenv("CATALOGFORGE_SWIGGY_ACCESS", "browser").strip().lower()
    if mode == "fixture":
        return FixtureAccess(
            json_path=os.getenv("CATALOGFORGE_SWIGGY_FIXTURE_JSON"),
            html_path=os.getenv("CATALOGFORGE_SWIGGY_FIXTURE_HTML"),
        )
    if mode == "official":
        return OfficialApiAccess()
    return BrowserAccess()


@app.post("/catalog/create", response_model=CatalogCreateResponse)
def catalog_create(
    request: CatalogCreateRequest,
    raw_request: Request,
    access: SwiggyAccess = Depends(get_swiggy_access),
    user: AuthUser = Depends(require_session),
) -> CatalogCreateResponse:
    organization_id = require_organization_member(raw_request, user, request.organization_id)
    result = create_catalog(request, access)
    try:
        stored = save_catalogue(
            user_id=user.id,
            organization_id=organization_id,
            result=result,
        )
    except CatalogueIdentityConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    bind_raw_capture(
        organization_id=organization_id,
        scrape_token=result.raw_capture_id,
        catalogue_id=stored.id,
        user_id=user.id,
    )
    return stored.result.model_copy(
        update={
            "raw_capture_id": result.raw_capture_id or stored.result.raw_capture_id,
            "quality": result.quality if result.quality is not None else stored.result.quality,
        }
    )


@app.get("/catalogues", response_model=CatalogueListResponse)
def catalogues_list(
    raw_request: Request,
    organization_id: str = Query(min_length=1),
    user: AuthUser = Depends(require_session),
) -> CatalogueListResponse:
    organization_id = require_organization_member(raw_request, user, organization_id)
    return CatalogueListResponse(catalogues=list_catalogues(user.id, organization_id, compact=True))


@app.get("/catalogues/{catalogue_id}", response_model=StoredCatalogue)
def catalogues_get(
    catalogue_id: str,
    raw_request: Request,
    organization_id: str = Query(min_length=1),
    user: AuthUser = Depends(require_session),
) -> StoredCatalogue:
    organization_id = require_organization_member(raw_request, user, organization_id)
    stored = get_catalogue(user.id, catalogue_id, organization_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Catalogue not found for this restaurant organization.")
    connection = mutation_connect()
    try:
        revision = head_revision(connection, catalogue_id)
    finally:
        connection.close()
    return stored.model_copy(
        update={"head_revision": revision, "state_hash": graded_state_hash(stored.result)},
    )


@app.post("/catalogues/{catalogue_id}/grade", response_model=GradingResult)
def catalogues_grade(
    catalogue_id: str,
    raw_request: Request,
    organization_id: str = Query(min_length=1),
    user: AuthUser = Depends(require_session),
) -> GradingResult:
    organization_id = require_organization_member(raw_request, user, organization_id)
    try:
        return grade_catalogue(user_id=user.id, organization_id=organization_id, catalogue_id=catalogue_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Catalogue not found for this restaurant organization.") from None
    except GradeInProgress as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except StaleClaim:
        raise HTTPException(status_code=409, detail="Grading claim is no longer valid.") from None
    except GradeCancelled:
        raise HTTPException(status_code=409, detail="Grading was cancelled.") from None
    except Exception as exc:
        from backend.grading.orchestrator import GradingStageFailure

        if isinstance(exc, (GradingStageFailure, GradePersistenceError)):
            raise HTTPException(status_code=502, detail="Grading could not be completed.") from exc
        raise


@app.get("/catalogues/{catalogue_id}/grade", response_model=GradingResult)
def catalogues_grade_get(
    catalogue_id: str,
    raw_request: Request,
    organization_id: str = Query(min_length=1),
    user: AuthUser = Depends(require_session),
) -> GradingResult:
    organization_id = require_organization_member(raw_request, user, organization_id)
    try:
        result = get_catalogue_grade(user_id=user.id, organization_id=organization_id, catalogue_id=catalogue_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Catalogue not found for this restaurant organization.") from None
    if result is None:
        raise HTTPException(status_code=404, detail="No completed grade for this catalogue revision.")
    return result


@app.get("/catalogues/{catalogue_id}/grade-explanation", response_model=GradeExplanation)
def catalogues_grade_explanation_get(
    catalogue_id: str,
    raw_request: Request,
    organization_id: str = Query(min_length=1),
    user: AuthUser = Depends(require_session),
) -> GradeExplanation:
    """Read-time explanation of the completed grading.v1 row for this revision.

    HTTP 404 means the catalogue exists but there is no completed grade for the
    current head revision and state hash (same condition as GET ``/grade``).
    """
    organization_id = require_organization_member(raw_request, user, organization_id)
    try:
        explanation = get_grade_explanation(
            user_id=user.id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Catalogue not found for this restaurant organization.") from None
    except IncompleteGradePayload:
        raise HTTPException(status_code=502, detail="Grade explanation could not be completed.") from None
    if explanation is None:
        raise HTTPException(status_code=404, detail="No completed grade for this catalogue revision.")
    return explanation


@app.post("/catalogues/{catalogue_id}/improvements", response_model=ImprovementProposal)
def catalogues_improvements_create(
    catalogue_id: str,
    body: ImprovementLineRequest,
    raw_request: Request,
    organization_id: str = Query(min_length=1),
    user: AuthUser = Depends(require_session),
) -> ImprovementProposal:
    organization_id = require_organization_member(raw_request, user, organization_id)
    try:
        return create_improvement(
            user_id=user.id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
            request=body,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Catalogue not found for this restaurant organization.") from None
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except IncompleteGradePayload:
        raise HTTPException(status_code=502, detail="Grade explanation could not be completed.") from None
    except TooManyImprovementPaths as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ImprovementUnsupported as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except sqlite3.Error:
        raise HTTPException(status_code=502, detail="Improvement proposal could not be persisted.") from None


@app.get("/catalogues/{catalogue_id}/improvements", response_model=ImprovementListResponse)
def catalogues_improvements_list(
    catalogue_id: str,
    raw_request: Request,
    organization_id: str = Query(min_length=1),
    user: AuthUser = Depends(require_session),
) -> ImprovementListResponse:
    organization_id = require_organization_member(raw_request, user, organization_id)
    try:
        return ImprovementListResponse(
            proposals=list_improvements(
                user_id=user.id,
                organization_id=organization_id,
                catalogue_id=catalogue_id,
            )
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Catalogue not found for this restaurant organization.") from None


@app.get("/catalogues/{catalogue_id}/improvements/{proposal_id}", response_model=ImprovementProposal)
def catalogues_improvements_get(
    catalogue_id: str,
    proposal_id: str,
    raw_request: Request,
    organization_id: str = Query(min_length=1),
    user: AuthUser = Depends(require_session),
) -> ImprovementProposal:
    organization_id = require_organization_member(raw_request, user, organization_id)
    try:
        proposal = get_improvement(
            user_id=user.id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
            proposal_id=proposal_id,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Catalogue not found for this restaurant organization.") from None
    if proposal is None:
        raise HTTPException(status_code=404, detail="Improvement proposal not found.")
    return proposal


@app.post("/catalogues/{catalogue_id}/improvements/{proposal_id}/apply", response_model=ImprovementApplyResult)
def catalogues_improvements_apply(
    catalogue_id: str,
    proposal_id: str,
    raw_request: Request,
    organization_id: str = Query(min_length=1),
    user: AuthUser = Depends(require_session),
) -> ImprovementApplyResult:
    organization_id = require_organization_member(raw_request, user, organization_id)
    try:
        from backend.improvement.apply import ApplyRejected

        return apply_improvement(
            user_id=user.id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
            proposal_id=proposal_id,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Catalogue not found for this restaurant organization.") from None
    except LookupError:
        raise HTTPException(status_code=404, detail="Improvement proposal not found.") from None
    except ApplyRejected as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/catalogues/{catalogue_id}/improvements/{proposal_id}/cancel", response_model=ImprovementProposal)
def catalogues_improvements_cancel(
    catalogue_id: str,
    proposal_id: str,
    raw_request: Request,
    organization_id: str = Query(min_length=1),
    user: AuthUser = Depends(require_session),
) -> ImprovementProposal:
    organization_id = require_organization_member(raw_request, user, organization_id)
    try:
        from backend.improvement.apply import ApplyRejected

        return cancel_improvement(
            user_id=user.id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
            proposal_id=proposal_id,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Catalogue not found for this restaurant organization.") from None
    except LookupError:
        raise HTTPException(status_code=404, detail="Improvement proposal not found.") from None
    except ApplyRejected as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/catalogues/{catalogue_id}/history", response_model=EditHistoryListResponse)
def catalogues_history_list(
    catalogue_id: str,
    raw_request: Request,
    organization_id: str = Query(min_length=1),
    user: AuthUser = Depends(require_session),
) -> EditHistoryListResponse:
    organization_id = require_organization_member(raw_request, user, organization_id)
    try:
        return list_history(user_id=user.id, organization_id=organization_id, catalogue_id=catalogue_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Catalogue not found for this restaurant organization.") from None


@app.post("/catalogues/{catalogue_id}/history/{history_id}/rollback", response_model=EditHistoryRecord)
def catalogues_history_rollback(
    catalogue_id: str,
    history_id: str,
    body: RollbackRequest,
    raw_request: Request,
    organization_id: str = Query(min_length=1),
    user: AuthUser = Depends(require_session),
) -> EditHistoryRecord:
    organization_id = require_organization_member(raw_request, user, organization_id)
    try:
        return rollback_history(
            user_id=user.id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
            history_id=history_id,
            confirm=body.confirm,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Catalogue not found for this restaurant organization.") from None
    except LookupError:
        raise HTTPException(status_code=404, detail="Edit history record not found.") from None
    except HistoryRejected as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/catalogues/{catalogue_id}/media-studio", response_model=MediaStudioResponse)
def catalogues_media_studio(
    catalogue_id: str,
    raw_request: Request,
    organization_id: str = Query(min_length=1),
    proposal_id: str | None = None,
    path: str | None = None,
    user: AuthUser = Depends(require_session),
) -> MediaStudioResponse:
    organization_id = require_organization_member(raw_request, user, organization_id)
    try:
        return get_media_studio(
            user_id=user.id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
            proposal_id=proposal_id,
            path=path,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Catalogue not found for this restaurant organization.") from None


@app.post("/catalogues/{catalogue_id}/media-jobs", response_model=MediaJob)
def catalogues_media_jobs_create(
    catalogue_id: str,
    body: MediaJobRequest,
    raw_request: Request,
    organization_id: str = Query(min_length=1),
    user: AuthUser = Depends(require_session),
) -> MediaJob:
    organization_id = require_organization_member(raw_request, user, organization_id)
    try:
        return create_media_job(
            user_id=user.id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
            request=body,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Catalogue not found for this restaurant organization.") from None
    except (MediaUnsupported, PromptRejected, MediaSourceError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except sqlite3.Error:
        raise HTTPException(status_code=502, detail="Media job could not be persisted.") from None


@app.get("/catalogues/{catalogue_id}/media-jobs", response_model=MediaJobListResponse)
def catalogues_media_jobs_list(
    catalogue_id: str,
    raw_request: Request,
    organization_id: str = Query(min_length=1),
    user: AuthUser = Depends(require_session),
) -> MediaJobListResponse:
    organization_id = require_organization_member(raw_request, user, organization_id)
    try:
        return list_media_jobs(user_id=user.id, organization_id=organization_id, catalogue_id=catalogue_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Catalogue not found for this restaurant organization.") from None


@app.get("/catalogues/{catalogue_id}/media-jobs/{job_id}", response_model=MediaJob)
def catalogues_media_jobs_get(
    catalogue_id: str,
    job_id: str,
    raw_request: Request,
    organization_id: str = Query(min_length=1),
    user: AuthUser = Depends(require_session),
) -> MediaJob:
    organization_id = require_organization_member(raw_request, user, organization_id)
    try:
        job = get_media_job(
            user_id=user.id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
            job_id=job_id,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Catalogue not found for this restaurant organization.") from None
    if job is None:
        raise HTTPException(status_code=404, detail="Media job not found.")
    return job


@app.post("/catalogues/{catalogue_id}/media-jobs/{job_id}/cancel", response_model=MediaJob)
def catalogues_media_jobs_cancel(
    catalogue_id: str,
    job_id: str,
    raw_request: Request,
    organization_id: str = Query(min_length=1),
    user: AuthUser = Depends(require_session),
) -> MediaJob:
    organization_id = require_organization_member(raw_request, user, organization_id)
    try:
        job = cancel_media_job(
            user_id=user.id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
            job_id=job_id,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Catalogue not found for this restaurant organization.") from None
    if job is None:
        raise HTTPException(status_code=404, detail="Media job not found.")
    return job


@app.post("/catalogues/{catalogue_id}/media-jobs/{job_id}/apply", response_model=MediaApplyResult)
def catalogues_media_jobs_apply(
    catalogue_id: str,
    job_id: str,
    raw_request: Request,
    organization_id: str = Query(min_length=1),
    candidate_id: str | None = None,
    user: AuthUser = Depends(require_session),
) -> MediaApplyResult:
    organization_id = require_organization_member(raw_request, user, organization_id)
    try:
        return apply_media_job(
            user_id=user.id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
            job_id=job_id,
            candidate_id=candidate_id,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Catalogue not found for this restaurant organization.") from None
    except LookupError:
        raise HTTPException(status_code=404, detail="Media job not found.") from None
    except MediaUnsupported as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/catalogues/{catalogue_id}/media-revert", response_model=MediaJob | None)
def catalogues_media_revert(
    catalogue_id: str,
    body: RevertRequest,
    raw_request: Request,
    path: str = Query(min_length=1),
    organization_id: str = Query(min_length=1),
    user: AuthUser = Depends(require_session),
) -> MediaJob | None:
    organization_id = require_organization_member(raw_request, user, organization_id)
    try:
        return revert_media_workspace(
            user_id=user.id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
            path=path,
            to=body.to,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Catalogue not found for this restaurant organization.") from None
    except MediaUnsupported as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/catalogues/{catalogue_id}/media-prompt-assist", response_model=PromptAssistResponse)
def catalogues_media_prompt_assist(
    catalogue_id: str,
    body: PromptAssistRequest,
    raw_request: Request,
    organization_id: str = Query(min_length=1),
    user: AuthUser = Depends(require_session),
) -> PromptAssistResponse:
    organization_id = require_organization_member(raw_request, user, organization_id)
    try:
        return assist_media_prompt(
            user_id=user.id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
            request=body,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Catalogue not found for this restaurant organization.") from None
    except (MediaUnsupported, PromptRejected) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/catalogues/{catalogue_id}/reviews/collect", response_model=ReviewCollectResponse)
def catalogues_reviews_collect(
    catalogue_id: str,
    body: ReviewCollectRequest,
    raw_request: Request,
    organization_id: str = Query(min_length=1),
    user: AuthUser = Depends(require_session),
) -> ReviewCollectResponse:
    organization_id = require_organization_member(raw_request, user, organization_id)
    try:
        return collect_reviews(
            user_id=user.id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
            request=body,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Catalogue not found for this restaurant organization.") from None
    except ReviewSourceUnsupported as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ReviewMalformed as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ReviewLimitExceeded as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except sqlite3.Error:
        raise HTTPException(status_code=502, detail="Reviews could not be collected.") from None


@app.post("/catalogues/{catalogue_id}/customer-feedback", response_model=CustomerFeedbackResponse)
async def catalogues_customer_feedback(
    catalogue_id: str,
    raw_request: Request,
    organization_id: str = Query(min_length=1),
    user: AuthUser = Depends(require_session),
) -> CustomerFeedbackResponse:
    organization_id = require_organization_member(raw_request, user, organization_id)
    content_type = (raw_request.headers.get("content-type") or "").lower()
    photo_bytes: bytes | None = None
    try:
        if "multipart/form-data" in content_type:
            form = await raw_request.form()
            rating_raw = form.get("observed_rating")
            rating_text = "" if rating_raw is None else str(rating_raw).strip()
            external_raw = form.get("external_id")
            payload = CustomerFeedbackRequest(
                body=str(form.get("body") or ""),
                external_id=None if external_raw in (None, "") else str(external_raw),
                observed_rating=None if rating_text == "" else float(rating_text),
            )
            upload = form.get("photo")
            if upload is not None and hasattr(upload, "read"):
                photo_bytes = await upload.read()
                if not photo_bytes:
                    photo_bytes = None
        else:
            raw = await raw_request.json()
            if not isinstance(raw, dict):
                raise ValueError("invalid payload")
            raw.pop("organization_id", None)
            raw.pop("catalogue_id", None)
            raw.pop("user_id", None)
            raw.pop("restaurant_id", None)
            payload = CustomerFeedbackRequest.model_validate(raw)
        return submit_customer_feedback(
            user_id=user.id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
            request=payload,
            photo_bytes=photo_bytes,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Catalogue not found for this restaurant organization.") from None
    except (ValidationError, ValueError, PhotoRejected) as exc:
        raise HTTPException(status_code=422, detail="Customer feedback could not be stored.") from exc
    except ReviewLimitExceeded as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except sqlite3.Error:
        raise HTTPException(status_code=502, detail="Customer feedback could not be stored.") from None


@app.get("/catalogues/{catalogue_id}/customer-feedback-photos/{photo_id}")
def catalogues_customer_feedback_photo(
    catalogue_id: str,
    photo_id: str,
    raw_request: Request,
    organization_id: str = Query(min_length=1),
    user: AuthUser = Depends(require_session),
) -> Response:
    organization_id = require_organization_member(raw_request, user, organization_id)
    try:
        data, content_type = load_customer_photo(
            user_id=user.id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
            photo_id=photo_id,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Photo not found.") from None
    except PhotoRejected:
        raise HTTPException(status_code=404, detail="Photo not found.") from None
    return Response(content=data, media_type=content_type)


@app.get("/catalogues/{catalogue_id}/reviews", response_model=ReviewListResponse)
def catalogues_reviews_list(
    catalogue_id: str,
    raw_request: Request,
    organization_id: str = Query(min_length=1),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=50),
    user: AuthUser = Depends(require_session),
) -> ReviewListResponse:
    organization_id = require_organization_member(raw_request, user, organization_id)
    try:
        return list_reviews(
            user_id=user.id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
            offset=offset,
            limit=limit,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Catalogue not found for this restaurant organization.") from None


@app.post("/catalogues/{catalogue_id}/review-intelligence", response_model=ReviewIntelligence)
def catalogues_review_intelligence_create(
    catalogue_id: str,
    raw_request: Request,
    organization_id: str = Query(min_length=1),
    user: AuthUser = Depends(require_session),
) -> ReviewIntelligence:
    organization_id = require_organization_member(raw_request, user, organization_id)
    try:
        return create_review_intelligence(
            user_id=user.id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Catalogue not found for this restaurant organization.") from None
    except AnalysisInProgress:
        raise HTTPException(status_code=409, detail="Review analysis is already in progress.") from None
    except StaleAnalysisClaim:
        raise HTTPException(status_code=409, detail="Review analysis is stale. Retry.") from None
    except ReviewAnalysisFailed:
        raise HTTPException(status_code=502, detail="Review analysis could not be completed.") from None
    except sqlite3.Error:
        raise HTTPException(status_code=502, detail="Review analysis could not be persisted.") from None


@app.post("/assistant/turn", response_model=AssistantTurnResponse)
def assistant_turn(
    body: AssistantTurnRequest,
    raw_request: Request,
    organization_id: str = Query(min_length=1),
    user: AuthUser = Depends(require_session),
) -> AssistantTurnResponse:
    organization_id = require_organization_member(raw_request, user, organization_id)
    try:
        return run_turn(
            user_id=user.id,
            organization_id=organization_id,
            catalogue_id=None,
            request=body,
        )
    except sqlite3.Error:
        raise HTTPException(status_code=502, detail="Assistant could not complete this request.") from None


@app.post("/catalogues/{catalogue_id}/assistant/turn", response_model=AssistantTurnResponse)
def catalogues_assistant_turn(
    catalogue_id: str,
    body: AssistantTurnRequest,
    raw_request: Request,
    organization_id: str = Query(min_length=1),
    user: AuthUser = Depends(require_session),
) -> AssistantTurnResponse:
    organization_id = require_organization_member(raw_request, user, organization_id)
    try:
        return run_turn(
            user_id=user.id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
            request=body,
        )
    except AssistantCatalogueMissing:
        raise HTTPException(status_code=404, detail="Catalogue not found for this restaurant organization.") from None
    except sqlite3.Error:
        raise HTTPException(status_code=502, detail="Assistant could not complete this request.") from None


@app.post("/catalogues/{catalogue_id}/assistant/mutations/{proposal_id}/confirm", response_model=AssistantTurnResponse)
def catalogues_assistant_mutation_confirm(
    catalogue_id: str,
    proposal_id: str,
    body: MutationConfirmRequest,
    raw_request: Request,
    organization_id: str = Query(min_length=1),
    user: AuthUser = Depends(require_session),
) -> AssistantTurnResponse:
    organization_id = require_organization_member(raw_request, user, organization_id)
    stored = get_catalogue(user.id, catalogue_id, organization_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Catalogue not found for this restaurant organization.")
    try:
        return confirm_proposal(
            user_id=user.id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
            proposal_id=proposal_id,
            request=body,
        )
    except MutationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except sqlite3.Error:
        raise HTTPException(status_code=502, detail="Catalogue mutation could not be confirmed.") from None


@app.post("/catalogues/{catalogue_id}/catalogue-mutations", response_model=StoredCatalogue)
def catalogues_owner_mutation(
    catalogue_id: str,
    body: OwnerCatalogueMutationRequest,
    raw_request: Request,
    organization_id: str = Query(min_length=1),
    user: AuthUser = Depends(require_session),
) -> StoredCatalogue:
    organization_id = require_organization_member(raw_request, user, organization_id)
    try:
        return apply_owner_mutation(
            user_id=user.id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
            draft=body.draft,
            item_id=body.item_id,
            source_head_revision=body.source_head_revision,
            source_state_hash=body.source_state_hash,
        )
    except MutationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except sqlite3.Error:
        raise HTTPException(status_code=502, detail="Catalogue could not be updated.") from None


@app.post("/catalogues/{catalogue_id}/assistant/mutations/{proposal_id}/cancel", response_model=AssistantTurnResponse)
def catalogues_assistant_mutation_cancel(
    catalogue_id: str,
    proposal_id: str,
    body: MutationConfirmRequest,
    raw_request: Request,
    organization_id: str = Query(min_length=1),
    user: AuthUser = Depends(require_session),
) -> AssistantTurnResponse:
    organization_id = require_organization_member(raw_request, user, organization_id)
    stored = get_catalogue(user.id, catalogue_id, organization_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Catalogue not found for this restaurant organization.")
    try:
        return cancel_proposal(
            user_id=user.id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
            proposal_id=proposal_id,
            confirm_token=body.confirm_token,
        )
    except MutationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except sqlite3.Error:
        raise HTTPException(status_code=502, detail="Catalogue mutation could not be cancelled.") from None


@app.get("/catalogues/{catalogue_id}/review-intelligence", response_model=ReviewIntelligence)
def catalogues_review_intelligence_get(
    catalogue_id: str,
    raw_request: Request,
    organization_id: str = Query(min_length=1),
    user: AuthUser = Depends(require_session),
) -> ReviewIntelligence:
    organization_id = require_organization_member(raw_request, user, organization_id)
    try:
        analysis = get_review_intelligence(
            user_id=user.id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Catalogue not found for this restaurant organization.") from None
    if analysis is None:
        raise HTTPException(status_code=404, detail="No review intelligence for this catalogue.")
    return analysis


@app.get("/catalogues/{catalogue_id}/media-artifacts/{artefact_id}")
def catalogues_media_artifact(
    catalogue_id: str,
    artefact_id: str,
    raw_request: Request,
    organization_id: str = Query(min_length=1),
    user: AuthUser = Depends(require_session),
) -> Response:
    organization_id = require_organization_member(raw_request, user, organization_id)
    try:
        data, content_type = load_artifact_bytes(
            user_id=user.id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
            artefact_id=artefact_id,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Media artifact not found.") from None
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Media artifact not found.") from None
    return Response(content=data, media_type=content_type)


@app.post("/catalogues/{catalogue_id}/platform-evaluation", response_model=CatalogueEvaluationResponse)
def catalogues_platform_evaluation(
    catalogue_id: str,
    raw_request: Request,
    organization_id: str = Query(min_length=1),
    platform: list[str] | None = Query(default=None),
    user: AuthUser = Depends(require_session),
) -> CatalogueEvaluationResponse:
    organization_id = require_organization_member(raw_request, user, organization_id)
    try:
        return evaluate_catalogue_platforms(
            user_id=user.id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
            platforms=platform,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Catalogue not found for this restaurant organization.") from None
    except UnsupportedPlatform as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except StaleCatalogueState:
        raise HTTPException(status_code=409, detail="Catalogue revision changed during platform evaluation.") from None
    except (PlatformEvalPersistenceError, PlatformEvalStageFailure):
        raise HTTPException(status_code=502, detail="Platform evaluation could not be completed.") from None


@app.get("/catalogues/{catalogue_id}/platform-evaluation", response_model=CatalogueEvaluationResponse)
def catalogues_platform_evaluation_get(
    catalogue_id: str,
    raw_request: Request,
    organization_id: str = Query(min_length=1),
    user: AuthUser = Depends(require_session),
) -> CatalogueEvaluationResponse:
    """Read stored platform evidence for the current catalogue revision.

    HTTP 200 with ``platform_evaluations: []`` means the catalogue exists and
    no Phase 4 evaluation row has been stored yet. That empty list is the
    contract (not HTTP 404). ``baba_score`` is null until a completed
    ``grading.v1`` row exists.
    """
    organization_id = require_organization_member(raw_request, user, organization_id)
    try:
        return get_catalogue_platform_evaluation(
            user_id=user.id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Catalogue not found for this restaurant organization.") from None
    except PlatformEvalPersistenceError:
        raise HTTPException(status_code=502, detail="Platform evaluation could not be completed.") from None


@app.get("/catalogues/{catalogue_id}/baba-score", response_model=BabaScore)
def catalogues_baba_score_get(
    catalogue_id: str,
    raw_request: Request,
    organization_id: str = Query(min_length=1),
    user: AuthUser = Depends(require_session),
) -> BabaScore:
    organization_id = require_organization_member(raw_request, user, organization_id)
    try:
        result = load_baba_score(user_id=user.id, organization_id=organization_id, catalogue_id=catalogue_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Catalogue not found for this restaurant organization.") from None
    if result is None:
        raise HTTPException(status_code=404, detail="No completed Baba Score for this catalogue revision.")
    return result


@app.delete("/catalogues/{catalogue_id}")
def catalogues_delete(
    catalogue_id: str,
    raw_request: Request,
    organization_id: str = Query(min_length=1),
    user: AuthUser = Depends(require_session),
) -> dict[str, str | bool]:
    organization_id = require_organization_member(raw_request, user, organization_id)
    deleted = delete_catalogue(user.id, catalogue_id, organization_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Catalogue not found for this restaurant organization.")
    return {"ok": True, "id": catalogue_id}


@app.post("/area-jobs")
def area_jobs_create(
    request: AreaJobCreateRequest,
    raw_request: Request,
    access: SwiggyAccess = Depends(get_swiggy_access),
    user: AuthUser = Depends(require_session),
) -> dict:
    organization_id = require_organization_member(raw_request, user, request.organization_id)
    try:
        return create_area_job(
            user_id=user.id,
            organization_id=organization_id,
            location_input=request.location,
            platforms=list(request.platforms),
            catalogue_type=request.catalogue_type,
            access=access,
            max_venues=request.max_venues,
            concurrency=request.concurrency,
            max_retries=request.max_retries,
            delay_seconds=request.delay_seconds,
            magicpin_dining=request.magicpin_dining,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/area-jobs")
def area_jobs_list(
    raw_request: Request,
    organization_id: str = Query(min_length=1),
    user: AuthUser = Depends(require_session),
) -> dict:
    organization_id = require_organization_member(raw_request, user, organization_id)
    return {"jobs": area_jobs_for(user.id, organization_id)}


@app.get("/area-jobs/{job_id}")
def area_jobs_get(
    job_id: str,
    raw_request: Request,
    organization_id: str = Query(min_length=1),
    user: AuthUser = Depends(require_session),
) -> dict:
    from backend.store import get_area_job

    organization_id = require_organization_member(raw_request, user, organization_id)
    payload = get_area_job(user.id, job_id, organization_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Area job not found.")
    return payload


@app.post("/area-jobs/{job_id}/start")
def area_jobs_start(
    job_id: str,
    request: AreaJobStartRequest,
    raw_request: Request,
    user: AuthUser = Depends(require_session),
) -> dict:
    organization_id = require_organization_member(raw_request, user, request.organization_id)
    try:
        return start_area_scrape(
            user_id=user.id,
            organization_id=organization_id,
            job_id=job_id,
            selected_keys=request.selected_keys,
            existing_actions=request.existing_actions,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Area job not found.") from exc


@app.post("/area-jobs/{job_id}/scrape-batch")
def area_jobs_scrape_batch(
    job_id: str,
    request: AreaJobActionRequest,
    raw_request: Request,
    access: SwiggyAccess = Depends(get_swiggy_access),
    user: AuthUser = Depends(require_session),
) -> dict:
    organization_id = require_organization_member(raw_request, user, request.organization_id)
    try:
        return scrape_area_batch(
            user_id=user.id,
            organization_id=organization_id,
            job_id=job_id,
            access=access,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Area job not found.") from exc


@app.delete("/area-jobs/{job_id}")
def area_jobs_delete(
    job_id: str,
    raw_request: Request,
    organization_id: str = Query(min_length=1),
    user: AuthUser = Depends(require_session),
) -> dict:
    organization_id = require_organization_member(raw_request, user, organization_id)
    try:
        return delete_area_discovery_job(user_id=user.id, organization_id=organization_id, job_id=job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Area job not found.") from exc


@app.post("/area-jobs/{job_id}/cancel")
def area_jobs_cancel(
    job_id: str,
    request: AreaJobActionRequest,
    raw_request: Request,
    user: AuthUser = Depends(require_session),
) -> dict:
    organization_id = require_organization_member(raw_request, user, request.organization_id)
    try:
        return cancel_area_job(user_id=user.id, organization_id=organization_id, job_id=job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Area job not found.") from exc
