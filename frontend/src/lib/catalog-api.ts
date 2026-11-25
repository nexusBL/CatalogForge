import { CatalogApiError } from "@/lib/catalog-api-error";
import type { CatalogCreateResponse, CatalogueListResponse, StoredCatalogue } from "@/lib/catalog-types";
import type { AreaJob } from "@/lib/area-jobs";
import { toStoredCatalogue } from "@/lib/catalog-types";
import type { GradeExplanation } from "@/lib/grade-types";
import type { ImprovementListResponse, ImprovementProposal } from "@/lib/improvement-types";
import type { EditHistoryListResponse, EditHistoryRecord } from "@/lib/history-types";
import type { MediaJob, MediaOperation, MediaStudioResponse } from "@/lib/media-types";
import type { AssistantTurnResponse } from "@/lib/assistant-types";
import type { CatalogueMutationDraft } from "@/lib/manage-catalogue-ui";
import type {
  CustomerFeedbackResponse,
  ReviewCollectResponse,
  ReviewIntelligence,
  ReviewListResponse,
} from "@/lib/review-types";

export { CatalogApiError } from "@/lib/catalog-api-error";

const QUICK_TIMEOUT_MS = 30_000;
const SCRAPE_TIMEOUT_MS = 300_000;
const NETWORK_RETRY_DELAY_MS = 5_000;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => globalThis.setTimeout(resolve, ms));
}

function isNetworkFailure(error: unknown): boolean {
  if (error instanceof DOMException && error.name === "AbortError") {
    return false;
  }
  return error instanceof TypeError || error instanceof DOMException;
}

async function timedFetch(
  input: string,
  init: RequestInit | undefined,
  timeoutMs: number,
  retriesLeft = 1,
): Promise<Response> {
  const userSignal = init?.signal;
  if (userSignal?.aborted) {
    throw new CatalogApiError("Scraping cancelled.", 499);
  }
  const controller = new AbortController();
  const onUserAbort = () => controller.abort();
  userSignal?.addEventListener("abort", onUserAbort);
  const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(input, { ...init, credentials: "include", signal: controller.signal });
  } catch (error) {
    if (userSignal?.aborted) {
      throw new CatalogApiError("Scraping cancelled.", 499);
    }
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new CatalogApiError("The request timed out. Try again.", 408);
    }
    if (retriesLeft > 0 && isNetworkFailure(error)) {
      await sleep(NETWORK_RETRY_DELAY_MS);
      return timedFetch(input, init, timeoutMs, retriesLeft - 1);
    }
    throw new CatalogApiError("The CatalogForge API is unavailable. Confirm FastAPI is running.", 503);
  } finally {
    userSignal?.removeEventListener("abort", onUserAbort);
    globalThis.clearTimeout(timeout);
  }
}

function quickFetch(input: string, init?: RequestInit): Promise<Response> {
  return timedFetch(input, init, QUICK_TIMEOUT_MS);
}

function scrapeFetch(input: string, init?: RequestInit): Promise<Response> {
  return timedFetch(input, init, SCRAPE_TIMEOUT_MS);
}

function rejectIfAuthOrInvalid(response: Response): void {
  if (response.status === 401) {
    throw new CatalogApiError("You need to sign in before using catalogues.", 401);
  }
  if (response.status === 422) {
    throw new CatalogApiError("The catalogue form is invalid. Check the Swiggy URL and required fields.", 422);
  }
}

async function extractErrorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const data = await response.json();
    if (data && typeof data === "object") {
      if (typeof data.detail === "string" && data.detail) return data.detail;
      if (typeof data.error === "string" && data.error) return data.error;
      if (typeof data.message === "string" && data.message) return data.message;
    }
  } catch {
    // ignored
  }
  return fallback;
}

export async function createCatalogue(
  payload: {
    restaurant_name: string;
    fssai_number: string;
    swiggy_url: string;
    organization_id: string;
    catalogue_type?: "restaurant" | "dineout" | "both";
    platform?: "swiggy" | "zomato" | "magicpin";
    dineout_url?: string;
  },
  signal?: AbortSignal,
): Promise<CatalogCreateResponse> {
  const response = await scrapeFetch("/api/catalog/create", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
  rejectIfAuthOrInvalid(response);
  if (!response.ok) {
    const errorMsg = await extractErrorMessage(response, "Catalogue creation failed. Try again in a moment.");
    throw new CatalogApiError(errorMsg, response.status);
  }
  return (await response.json()) as CatalogCreateResponse;
}

export async function listCataloguesApi(organizationId: string): Promise<StoredCatalogue[]> {
  const response = await quickFetch(`/api/catalogues?organization_id=${encodeURIComponent(organizationId)}`);
  rejectIfAuthOrInvalid(response);
  if (!response.ok) {
    throw new CatalogApiError("Could not load catalogues.", response.status);
  }
  const body = (await response.json()) as CatalogueListResponse;
  return (body.catalogues || []).map(toStoredCatalogue);
}

export async function getCatalogueApi(id: string, organizationId: string): Promise<StoredCatalogue | null> {
  const response = await quickFetch(
    `/api/catalogues/${encodeURIComponent(id)}?organization_id=${encodeURIComponent(organizationId)}`,
  );
  rejectIfAuthOrInvalid(response);
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new CatalogApiError("Could not load this catalogue.", response.status);
  }
  const body = (await response.json()) as CatalogueListResponse["catalogues"][number];
  return toStoredCatalogue(body);
}

export async function getGradeExplanationApi(
  id: string,
  organizationId: string,
): Promise<GradeExplanation | null> {
  const response = await quickFetch(
    `/api/catalogues/${encodeURIComponent(id)}/grade-explanation?organization_id=${encodeURIComponent(organizationId)}`,
  );
  rejectIfAuthOrInvalid(response);
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new CatalogApiError("Could not load this catalogue grade.", response.status);
  }
  return (await response.json()) as GradeExplanation;
}

export async function gradeCatalogueApi(id: string, organizationId: string): Promise<GradeExplanation> {
  const response = await scrapeFetch(
    `/api/catalogues/${encodeURIComponent(id)}/grade?organization_id=${encodeURIComponent(organizationId)}`,
    { method: "POST" },
  );
  rejectIfAuthOrInvalid(response);
  if (response.status === 404) {
    throw new CatalogApiError("Catalogue not found for this restaurant organization.", 404);
  }
  if (response.status === 409) {
    throw new CatalogApiError("Grading is already in progress or the claim is no longer valid.", 409);
  }
  if (!response.ok) {
    throw new CatalogApiError("Could not grade this catalogue.", response.status);
  }
  const explanation = await getGradeExplanationApi(id, organizationId);
  if (explanation === null) {
    throw new CatalogApiError("Grading finished without a persisted explanation.", 502);
  }
  return explanation;
}

export async function listImprovementsApi(
  id: string,
  organizationId: string,
): Promise<ImprovementProposal[]> {
  const response = await quickFetch(
    `/api/catalogues/${encodeURIComponent(id)}/improvements?organization_id=${encodeURIComponent(organizationId)}`,
  );
  rejectIfAuthOrInvalid(response);
  if (response.status === 404) {
    throw new CatalogApiError("Catalogue not found for this restaurant organization.", 404);
  }
  if (!response.ok) {
    throw new CatalogApiError("Could not load improvement previews.", response.status);
  }
  const body = (await response.json()) as ImprovementListResponse;
  return body.proposals || [];
}

export async function createImprovementApi(
  id: string,
  organizationId: string,
  payload: { check_id: string; paths?: string[]; instruction?: string; refining_proposal_id?: string },
): Promise<ImprovementProposal> {
  const response = await scrapeFetch(
    `/api/catalogues/${encodeURIComponent(id)}/improvements?organization_id=${encodeURIComponent(organizationId)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (response.status === 401) {
    throw new CatalogApiError("You need to sign in before using catalogues.", 401);
  }
  if (response.status === 404) {
    throw new CatalogApiError("Catalogue not found for this restaurant organization.", 404);
  }
  if (response.status === 422) {
    throw new CatalogApiError("This finding cannot produce a Phase 6 preview.", 422);
  }
  if (!response.ok) {
    const errorMsg = await extractErrorMessage(response, "Could not generate an improvement preview.");
    throw new CatalogApiError(errorMsg, response.status);
  }
  return (await response.json()) as ImprovementProposal;
}

export async function applyImprovementApi(
  id: string,
  organizationId: string,
  proposalId: string,
): Promise<{
  proposal: ImprovementProposal;
  applied_paths: string[];
  skipped_media_paths: string[];
  grade_letter: string | null;
  grade_score: number | null;
}> {
  const response = await scrapeFetch(
    `/api/catalogues/${encodeURIComponent(id)}/improvements/${encodeURIComponent(proposalId)}/apply?organization_id=${encodeURIComponent(organizationId)}`,
    { method: "POST" },
  );
  if (response.status === 401) {
    throw new CatalogApiError("You need to sign in before using catalogues.", 401);
  }
  if (response.status === 404) {
    throw new CatalogApiError("Catalogue or proposal not found for this restaurant organization.", 404);
  }
  if (response.status === 409) {
    throw new CatalogApiError("This improvement can no longer be applied.", 409);
  }
  if (!response.ok) {
    throw new CatalogApiError("Could not apply this improvement.", response.status);
  }
  return (await response.json()) as {
    proposal: ImprovementProposal;
    applied_paths: string[];
    skipped_media_paths: string[];
    grade_letter: string | null;
    grade_score: number | null;
  };
}

export async function cancelImprovementApi(
  id: string,
  organizationId: string,
  proposalId: string,
): Promise<ImprovementProposal> {
  const response = await scrapeFetch(
    `/api/catalogues/${encodeURIComponent(id)}/improvements/${encodeURIComponent(proposalId)}/cancel?organization_id=${encodeURIComponent(organizationId)}`,
    { method: "POST" },
  );
  if (response.status === 401) {
    throw new CatalogApiError("You need to sign in before using catalogues.", 401);
  }
  if (response.status === 404) {
    throw new CatalogApiError("Catalogue or proposal not found for this restaurant organization.", 404);
  }
  if (response.status === 409) {
    throw new CatalogApiError("This improvement can no longer be cancelled.", 409);
  }
  if (!response.ok) {
    throw new CatalogApiError("Could not cancel this improvement.", response.status);
  }
  return (await response.json()) as ImprovementProposal;
}

export async function listHistoryApi(
  id: string,
  organizationId: string,
): Promise<EditHistoryListResponse> {
  const response = await scrapeFetch(
    `/api/catalogues/${encodeURIComponent(id)}/history?organization_id=${encodeURIComponent(organizationId)}`,
  );
  if (response.status === 401) {
    throw new CatalogApiError("You need to sign in before using catalogues.", 401);
  }
  if (response.status === 404) {
    throw new CatalogApiError("Catalogue not found for this restaurant organization.", 404);
  }
  if (!response.ok) {
    throw new CatalogApiError("Could not load edit history.", response.status);
  }
  return (await response.json()) as EditHistoryListResponse;
}

export async function rollbackHistoryApi(
  id: string,
  organizationId: string,
  historyId: string,
): Promise<EditHistoryRecord> {
  const response = await scrapeFetch(
    `/api/catalogues/${encodeURIComponent(id)}/history/${encodeURIComponent(historyId)}/rollback?organization_id=${encodeURIComponent(organizationId)}`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confirm: true }) },
  );
  if (response.status === 401) {
    throw new CatalogApiError("You need to sign in before using catalogues.", 401);
  }
  if (response.status === 404) {
    throw new CatalogApiError("Catalogue or history record not found.", 404);
  }
  if (response.status === 409) {
    throw new CatalogApiError("This catalogue change can no longer be rolled back.", 409);
  }
  if (!response.ok) {
    throw new CatalogApiError("Could not roll back this catalogue change.", response.status);
  }
  return (await response.json()) as EditHistoryRecord;
}

export async function getMediaStudioApi(
  id: string,
  organizationId: string,
  proposalId?: string,
  path?: string,
): Promise<MediaStudioResponse> {
  const params = new URLSearchParams({ organization_id: organizationId });
  if (proposalId) {
    params.set("proposal_id", proposalId);
  }
  if (path) {
    params.set("path", path);
  }
  const response = await quickFetch(`/api/catalogues/${encodeURIComponent(id)}/media-studio?${params}`);
  rejectIfAuthOrInvalid(response);
  if (response.status === 404) {
    throw new CatalogApiError("Catalogue not found for this restaurant organization.", 404);
  }
  if (!response.ok) {
    throw new CatalogApiError("Could not load Generated Media.", response.status);
  }
  return (await response.json()) as MediaStudioResponse;
}

export async function createMediaJobApi(
  id: string,
  organizationId: string,
  payload: { path: string; operation: MediaOperation; prompt?: string; proposal_id?: string; parent_candidate_id?: string; revision_ordinal?: number },
): Promise<MediaJob> {
  const response = await scrapeFetch(
    `/api/catalogues/${encodeURIComponent(id)}/media-jobs?organization_id=${encodeURIComponent(organizationId)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (response.status === 401) {
    throw new CatalogApiError("You need to sign in before using catalogues.", 401);
  }
  if (response.status === 404) {
    throw new CatalogApiError("Catalogue not found for this restaurant organization.", 404);
  }
  if (response.status === 422) {
    throw new CatalogApiError("This media request is not allowed.", 422);
  }
  if (!response.ok) {
    throw new CatalogApiError("Could not generate media.", response.status);
  }
  return (await response.json()) as MediaJob;
}

export async function assistMediaPromptApi(
  id: string,
  organizationId: string,
  payload: { path: string; kind: "edit" | "image_to_video"; prompt?: string },
): Promise<{ suggested_prompt: string }> {
  const response = await quickFetch(
    `/api/catalogues/${encodeURIComponent(id)}/media-prompt-assist?organization_id=${encodeURIComponent(organizationId)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  rejectIfAuthOrInvalid(response);
  if (!response.ok) {
    throw new CatalogApiError("Could not assist the prompt.", response.status);
  }
  return (await response.json()) as { suggested_prompt: string };
}

export async function revertMediaApi(
  id: string,
  organizationId: string,
  path: string,
  to: string = "original",
): Promise<MediaJob | null> {
  const params = new URLSearchParams({ organization_id: organizationId, path });
  const response = await quickFetch(`/api/catalogues/${encodeURIComponent(id)}/media-revert?${params}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ to }),
  });
  rejectIfAuthOrInvalid(response);
  if (!response.ok) {
    throw new CatalogApiError("Could not revert generated media.", response.status);
  }
  if (response.status === 204) {
    return null;
  }
  const text = await response.text();
  if (!text || text === "null") {
    return null;
  }
  return JSON.parse(text) as MediaJob;
}

export async function applyMediaJobApi(
  id: string,
  organizationId: string,
  jobId: string,
): Promise<{ job: MediaJob; catalogue_url: string; grade_letter: string | null; grade_score: number | null }> {
  const response = await scrapeFetch(
    `/api/catalogues/${encodeURIComponent(id)}/media-jobs/${encodeURIComponent(jobId)}/apply?organization_id=${encodeURIComponent(organizationId)}`,
    { method: "POST" },
  );
  if (response.status === 401) {
    throw new CatalogApiError("You need to sign in before using catalogues.", 401);
  }
  if (response.status === 404) {
    throw new CatalogApiError("Catalogue or media job not found for this restaurant organization.", 404);
  }
  if (response.status === 409) {
    throw new CatalogApiError("This generated media cannot be applied yet.", 409);
  }
  if (!response.ok) {
    throw new CatalogApiError("Could not apply generated media to the catalogue.", response.status);
  }
  return (await response.json()) as {
    job: MediaJob;
    catalogue_url: string;
    grade_letter: string | null;
    grade_score: number | null;
  };
}

export async function deleteCatalogueApi(id: string, organizationId: string): Promise<void> {
  const response = await quickFetch(
    `/api/catalogues/${encodeURIComponent(id)}?organization_id=${encodeURIComponent(organizationId)}`,
    { method: "DELETE" },
  );
  rejectIfAuthOrInvalid(response);
  if (response.status === 404) {
    throw new CatalogApiError("Catalogue not found for this restaurant organization.", 404);
  }
  if (!response.ok) {
    throw new CatalogApiError("Could not delete this catalogue.", response.status);
  }
}

export async function createAreaJob(
  payload: {
    location: string;
    platforms: Array<"swiggy" | "zomato" | "magicpin">;
    catalogue_type: "restaurant" | "dineout" | "both";
    organization_id: string;
    max_venues?: number | null;
    concurrency?: number;
    max_retries?: number;
    magicpin_dining?: "all" | "budget" | "fine";
  },
  signal?: AbortSignal,
): Promise<AreaJob> {
  const response = await scrapeFetch("/api/area-jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
  rejectIfAuthOrInvalid(response);
  if (!response.ok) {
    throw new CatalogApiError("Area discovery failed. Try again in a moment.", response.status);
  }
  return (await response.json()) as AreaJob;
}

export async function listAreaJobsApi(organizationId: string): Promise<AreaJob[]> {
  const response = await quickFetch(`/api/area-jobs?organization_id=${encodeURIComponent(organizationId)}`);
  rejectIfAuthOrInvalid(response);
  if (!response.ok) {
    throw new CatalogApiError("Could not load area jobs.", response.status);
  }
  const body = (await response.json()) as { jobs?: AreaJob[] };
  return body.jobs || [];
}

export async function getAreaJobApi(id: string, organizationId: string): Promise<AreaJob | null> {
  const response = await quickFetch(
    `/api/area-jobs/${encodeURIComponent(id)}?organization_id=${encodeURIComponent(organizationId)}`,
  );
  rejectIfAuthOrInvalid(response);
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new CatalogApiError("Could not load this area job.", response.status);
  }
  return (await response.json()) as AreaJob;
}

export async function startAreaJobApi(
  id: string,
  payload: {
    organization_id: string;
    selected_keys?: string[];
    existing_actions?: Record<string, "skip" | "rescrape" | "update">;
  },
): Promise<AreaJob> {
  const response = await quickFetch(`/api/area-jobs/${encodeURIComponent(id)}/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  rejectIfAuthOrInvalid(response);
  if (!response.ok) {
    throw new CatalogApiError("Could not start scraping.", response.status);
  }
  return (await response.json()) as AreaJob;
}

export async function scrapeAreaBatchApi(id: string, organizationId: string): Promise<AreaJob> {
  const response = await scrapeFetch(`/api/area-jobs/${encodeURIComponent(id)}/scrape-batch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ organization_id: organizationId }),
  });
  rejectIfAuthOrInvalid(response);
  if (!response.ok) {
    throw new CatalogApiError("Could not continue scraping.", response.status);
  }
  return (await response.json()) as AreaJob;
}

export async function deleteAreaJobApi(id: string, organizationId: string): Promise<void> {
  const response = await quickFetch(
    `/api/area-jobs/${encodeURIComponent(id)}?organization_id=${encodeURIComponent(organizationId)}`,
    { method: "DELETE" },
  );
  rejectIfAuthOrInvalid(response);
  if (response.status === 404) {
    throw new CatalogApiError("Discovery job not found.", 404);
  }
  if (!response.ok) {
    throw new CatalogApiError("Could not delete this discovery job.", response.status);
  }
}

export async function cancelAreaJobApi(id: string, organizationId: string): Promise<AreaJob> {
  const response = await quickFetch(`/api/area-jobs/${encodeURIComponent(id)}/cancel`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ organization_id: organizationId }),
  });
  rejectIfAuthOrInvalid(response);
  if (!response.ok) {
    throw new CatalogApiError("Could not cancel this job.", response.status);
  }
  return (await response.json()) as AreaJob;
}

export async function collectReviewsApi(
  id: string,
  organizationId: string,
  reviews: Array<{ body: string; external_id?: string; observed_rating?: number }>,
): Promise<ReviewCollectResponse> {
  const response = await quickFetch(
    `/api/catalogues/${encodeURIComponent(id)}/reviews/collect?organization_id=${encodeURIComponent(organizationId)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reviews }),
    },
  );
  rejectIfAuthOrInvalid(response);
  if (response.status === 404) {
    throw new CatalogApiError("Catalogue not found for this restaurant organization.", 404);
  }
  if (response.status === 422) {
    throw new CatalogApiError("Those reviews could not be stored.", 422);
  }
  if (!response.ok) {
    throw new CatalogApiError("Could not collect reviews.", response.status);
  }
  return (await response.json()) as ReviewCollectResponse;
}

export async function listReviewsApi(
  id: string,
  organizationId: string,
  offset = 0,
  limit = 50,
): Promise<ReviewListResponse> {
  const params = new URLSearchParams({
    organization_id: organizationId,
    offset: String(offset),
    limit: String(limit),
  });
  const response = await quickFetch(`/api/catalogues/${encodeURIComponent(id)}/reviews?${params}`);
  rejectIfAuthOrInvalid(response);
  if (response.status === 404) {
    throw new CatalogApiError("Catalogue not found for this restaurant organization.", 404);
  }
  if (!response.ok) {
    throw new CatalogApiError("Could not load reviews.", response.status);
  }
  return (await response.json()) as ReviewListResponse;
}

export async function createReviewIntelligenceApi(id: string, organizationId: string): Promise<ReviewIntelligence> {
  const response = await quickFetch(
    `/api/catalogues/${encodeURIComponent(id)}/review-intelligence?organization_id=${encodeURIComponent(organizationId)}`,
    { method: "POST" },
  );
  rejectIfAuthOrInvalid(response);
  if (response.status === 404) {
    throw new CatalogApiError("Catalogue not found for this restaurant organization.", 404);
  }
  if (response.status === 409) {
    throw new CatalogApiError("Review analysis is already in progress or stale. Retry.", 409);
  }
  if (!response.ok) {
    throw new CatalogApiError("Could not analyze reviews.", response.status);
  }
  return (await response.json()) as ReviewIntelligence;
}

export async function getReviewIntelligenceApi(
  id: string,
  organizationId: string,
): Promise<ReviewIntelligence | null> {
  const response = await quickFetch(
    `/api/catalogues/${encodeURIComponent(id)}/review-intelligence?organization_id=${encodeURIComponent(organizationId)}`,
  );
  rejectIfAuthOrInvalid(response);
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new CatalogApiError("Could not load review intelligence.", response.status);
  }
  return (await response.json()) as ReviewIntelligence;
}

export async function submitCustomerFeedbackApi(
  id: string,
  organizationId: string,
  input: { body: string; externalId?: string; observedRating?: number; photo?: File | null },
): Promise<CustomerFeedbackResponse> {
  const query = `organization_id=${encodeURIComponent(organizationId)}`;
  const url = `/api/catalogues/${encodeURIComponent(id)}/customer-feedback?${query}`;
  let response: Response;
  if (input.photo) {
    const form = new FormData();
    form.set("body", input.body);
    if (input.externalId) {
      form.set("external_id", input.externalId);
    }
    if (input.observedRating != null) {
      form.set("observed_rating", String(input.observedRating));
    }
    form.set("photo", input.photo);
    response = await quickFetch(url, { method: "POST", body: form });
  } else {
    response = await quickFetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        body: input.body,
        ...(input.externalId ? { external_id: input.externalId } : {}),
        ...(input.observedRating != null ? { observed_rating: input.observedRating } : {}),
      }),
    });
  }
  rejectIfAuthOrInvalid(response);
  if (response.status === 404) {
    throw new CatalogApiError("Catalogue not found for this restaurant organization.", 404);
  }
  if (response.status === 422) {
    throw new CatalogApiError("That feedback could not be stored.", 422);
  }
  if (!response.ok) {
    throw new CatalogApiError("Could not send feedback.", response.status);
  }
  return (await response.json()) as CustomerFeedbackResponse;
}

export async function assistantTurnApi(
  id: string | null,
  organizationId: string,
  message: string,
  options?: { currentRoute?: string },
): Promise<AssistantTurnResponse> {
  const path = id
    ? `/api/catalogues/${encodeURIComponent(id)}/assistant/turn`
    : "/api/assistant/turn";
  const payload: { message: string; context?: { current_route: string } } = { message };
  if (options?.currentRoute) {
    payload.context = { current_route: options.currentRoute };
  }
  const response = await quickFetch(
    `${path}?organization_id=${encodeURIComponent(organizationId)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  rejectIfAuthOrInvalid(response);
  if (response.status === 404) {
    throw new CatalogApiError("Catalogue not found for this restaurant organization.", 404);
  }
  if (response.status === 422) {
    throw new CatalogApiError("Ask Baba a short question about this catalogue.", 422);
  }
  if (!response.ok) {
    throw new CatalogApiError("Could not ask Baba about this catalogue.", response.status);
  }
  return (await response.json()) as AssistantTurnResponse;
}

async function mutationDecisionApi(
  id: string,
  organizationId: string,
  proposalId: string,
  confirmToken: string,
  action: "confirm" | "cancel",
): Promise<AssistantTurnResponse> {
  const response = await quickFetch(
    `/api/catalogues/${encodeURIComponent(id)}/assistant/mutations/${encodeURIComponent(proposalId)}/${action}?organization_id=${encodeURIComponent(organizationId)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirm_token: confirmToken }),
    },
  );
  rejectIfAuthOrInvalid(response);
  if (response.status === 404) {
    throw new CatalogApiError("Catalogue not found for this restaurant organization.", 404);
  }
  if (response.status === 403) {
    throw new CatalogApiError("That confirmation is not valid for this catalogue.", 403);
  }
  if (!response.ok) {
    throw new CatalogApiError("Could not resolve that catalogue change.", response.status);
  }
  return (await response.json()) as AssistantTurnResponse;
}

export async function confirmMutationApi(
  id: string,
  organizationId: string,
  proposalId: string,
  confirmToken: string,
): Promise<AssistantTurnResponse> {
  return mutationDecisionApi(id, organizationId, proposalId, confirmToken, "confirm");
}

export async function cancelMutationApi(
  id: string,
  organizationId: string,
  proposalId: string,
  confirmToken: string,
): Promise<AssistantTurnResponse> {
  return mutationDecisionApi(id, organizationId, proposalId, confirmToken, "cancel");
}

export async function applyCatalogueMutationApi(
  id: string,
  organizationId: string,
  body: {
    draft: CatalogueMutationDraft;
    item_id?: string | null;
    source_head_revision: number;
    source_state_hash: string;
  },
): Promise<StoredCatalogue> {
  const response = await quickFetch(
    `/api/catalogues/${encodeURIComponent(id)}/catalogue-mutations?organization_id=${encodeURIComponent(organizationId)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  rejectIfAuthOrInvalid(response);
  if (response.status === 404) {
    throw new CatalogApiError("Catalogue not found for this restaurant organization.", 404);
  }
  if (!response.ok) {
    const errorMsg = await extractErrorMessage(response, "Could not update this catalogue.");
    throw new CatalogApiError(errorMsg, response.status);
  }
  return toStoredCatalogue(await response.json());
}
