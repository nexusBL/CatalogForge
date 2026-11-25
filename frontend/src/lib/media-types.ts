export type MediaStatus = "GENERATING" | "READY" | "FAILED" | "CANCELLED" | "STALE";
export type MediaKind = "image" | "video";
export type MediaOperation =
  | "generate_image"
  | "enhance"
  | "background_removal"
  | "background_generation"
  | "blur"
  | "crop"
  | "expand"
  | "cleanup"
  | "edit"
  | "image_to_video";

export type MediaCandidate = {
  id: string;
  parent_id: string | null;
  operation: MediaOperation;
  prompt: string | null;
  artifact_id: string;
  content_type: string;
  media_kind: MediaKind;
  provider: string;
  created_at: string;
};

export type MediaJob = {
  id: string;
  catalogue_id: string;
  organization_id: string;
  path: string;
  operation: MediaOperation;
  status: MediaStatus;
  prompt: string | null;
  proposal_id: string | null;
  source_head_revision: number;
  source_state_hash: string;
  source_ref: string | null;
  original_artifact_id: string | null;
  active_candidate_id: string | null;
  candidates: MediaCandidate[];
  reference_paths: string[];
  error: string | null;
  idempotent_replay: boolean;
  created_at: string;
  updated_at: string;
};

export type MediaWorkspaceItem = {
  path: string;
  name: string;
  description: string | null;
  category_name: string;
  image_url: string | null;
  has_usable_image: boolean;
  active_job_id: string | null;
  active_candidate_id: string | null;
};

export type MediaReference = {
  path: string;
  image_url: string;
  name: string;
  category_name: string;
  reason: string;
};

export type MediaStudioResponse = {
  catalogue_id: string;
  restaurant_name: string | null;
  source_head_revision: number;
  source_state_hash: string;
  items: MediaWorkspaceItem[];
  references: MediaReference[];
  jobs: MediaJob[];
  handoff_path: string | null;
  handoff_check_id: string | null;
};
