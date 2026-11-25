export type LinkageStatus = "exact" | "normalized" | "ambiguous" | "no_match";
export type AnalysisStatus = "GENERATING" | "READY" | "FAILED" | "STALE";
export type IngestSource = "supplied" | "customer";
export type FeedbackTarget =
  | "product_item"
  | "catalogue_menu"
  | "website_ux"
  | "restaurant_service"
  | "other";
export type RequestKind = "none" | "improvement_request";
export type Polarity = "positive" | "negative" | "neutral" | "mixed";
export type AspectName =
  | "taste"
  | "quantity"
  | "value"
  | "service"
  | "catalogue_info"
  | "website_ux"
  | "other";
export type FeedbackIntent = "observation" | "praise" | "complaint" | "mixed";
export type RecurrenceLabel = "one_off" | "repeated" | "recurring_complaint";
export type PositiveThemeLabel = "none" | "positive_theme";

export type StoredReview = {
  id: string;
  catalogue_id: string;
  organization_id: string;
  source: IngestSource;
  external_id: string;
  body: string;
  posted_at: string | null;
  author_key: string | null;
  observed_rating: number | null;
  photo_id: string | null;
  created_at: string;
  duplicate: boolean;
};

export type ReviewListResponse = {
  collection_source: "unresolved";
  ingest_mode: IngestSource | "mixed";
  total: number;
  offset: number;
  limit: number;
  reviews: StoredReview[];
};

export type ReviewCollectResponse = {
  collection_source: "unresolved";
  ingest_mode: "supplied";
  accepted: number;
  duplicate: number;
  reviews: StoredReview[];
};

export type CustomerFeedbackResponse = {
  collection_source: "unresolved";
  ingest_mode: "customer";
  duplicate: boolean;
  review: StoredReview;
};

export type ReviewLinkage = {
  status: LinkageStatus;
  item_id: string | null;
  item_name: string | null;
  path: string | null;
  span_text: string | null;
  candidate_item_ids: string[];
};

export type ReviewEvidence = {
  review_id: string;
  posted_at: string | null;
  span_text: string | null;
  observed_rating: number | null;
  photo_id: string | null;
  target: FeedbackTarget;
  request_kind: RequestKind;
  intent: FeedbackIntent;
  aspect: AspectName;
  polarity: Polarity;
  polarity_status: Polarity;
  aspect_status: AspectName;
  linkage: ReviewLinkage;
};

export type ReviewObservation = {
  observation_id: string;
  kind:
    | "item_feedback"
    | "unmatched_feedback"
    | "catalogue_feedback"
    | "website_feedback"
    | "service_feedback";
  target: FeedbackTarget;
  request_kind: RequestKind;
  intent: FeedbackIntent;
  aspect: AspectName;
  polarity: Polarity;
  item_id: string | null;
  item_name: string | null;
  path: string | null;
  linkage_status: LinkageStatus;
  review_count: number;
  observed_ratings: number[];
  polarity_status: Polarity;
  aspect_status: AspectName;
  recurrence_status: RecurrenceLabel;
  positive_theme_status: PositiveThemeLabel;
  evidence: ReviewEvidence[];
};

export type ReviewRecommendation = {
  recommendation_id: string;
  observation_id: string;
  action: string;
  target: FeedbackTarget;
  request_kind: RequestKind;
  intent: FeedbackIntent;
  aspect: AspectName;
  polarity: Polarity;
  recurrence_status: RecurrenceLabel;
  positive_theme_status: PositiveThemeLabel;
  evidence_review_ids: string[];
};

export type ReviewIntelligence = {
  id: string;
  catalogue_id: string;
  organization_id: string;
  engine_version: string;
  source_head_revision: number;
  source_state_hash: string;
  reviews_fingerprint: string;
  status: AnalysisStatus;
  collection_source: "unresolved";
  polarity_status: Polarity;
  aspect_status: "ok";
  recurrence_status: RecurrenceLabel;
  positive_theme_status: PositiveThemeLabel;
  review_count: number;
  observations: ReviewObservation[];
  recommendations: ReviewRecommendation[];
  created_at: string;
  updated_at: string;
  idempotent_replay: boolean;
  failure_reason: string | null;
};
