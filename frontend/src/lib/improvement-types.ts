export type ImprovementKind = "description" | "category_name" | "labels" | "media_handoff" | "item_price";
export type ProposalStatus = "READY" | "FAILED" | "PARTIAL" | "STALE" | "APPLIED" | "CANCELLED";
export type LineStatus = "READY" | "FAILED";

export type MediaHandoff = {
  phase7_required: boolean;
  media_type: "image" | "video";
  capability: string;
  current_ref: string | null;
};

export type ImprovementLine = {
  path: string;
  kind: ImprovementKind;
  check_id: string;
  finding_id: string;
  current_value: string | null;
  proposed_value: string | null;
  proposed_labels?: string[] | null;
  media_handoff?: MediaHandoff | null;
  status: LineStatus;
  failure_reason: string | null;
  why: string;
  provenance?: Record<string, unknown>;
};

export type ImprovementProposal = {
  id: string;
  catalogue_id: string;
  organization_id: string;
  source_head_revision: number;
  source_state_hash: string;
  check_id: string;
  finding_id: string;
  improvement_version: string;
  status: ProposalStatus;
  lines: ImprovementLine[];
  created_at: string;
  idempotent_replay: boolean;
};

export type ImprovementListResponse = {
  proposals: ImprovementProposal[];
};

export const PHASE6_V1_CHECK_IDS = new Set([
  "missing_description",
  "description_coverage",
  "placeholder_text",
  "malformed_text",
  "repeated_description",
  "missing_category_name",
  "missing_item_image",
  "image_missing",
  "image_invalid",
  "image_unreadable",
  "image_low_quality",
  "no_images_present",
  "missing_price",
  "invalid_price",
  "empty_item_labels",
]);
