export type AssistantIntent =
  | "open_catalogue"
  | "open_grade"
  | "open_improvements"
  | "open_reviews"
  | "open_media"
  | "show_baba_score"
  | "explain_catalogue_grade"
  | "explain_fix_first"
  | "explain_review_complaints"
  | "explain_items_attention"
  | "explain_item_findings"
  | "explain_org_grades"
  | "refuse_mutation"
  | "propose_mutation"
  | "clarify"
  | "unsupported";

export type MutationProposalView = {
  proposal_id: string;
  confirm_token: string | null;
  operation: string;
  status: "PENDING" | "APPLIED" | "CANCELLED" | "STALE" | "EXPIRED";
  summary: string;
  item_name: string | null;
  category_name: string | null;
  current_value: string | null;
  proposed_value: string | null;
  expires_at: string | null;
  writes_payload: boolean;
  media_job_id: string | null;
  candidates: string[];
};

export type AssistantAction = {
  label: string;
  href: string;
};

export type AssistantTurnResponse = {
  message: string;
  intent: AssistantIntent;
  used_llm: boolean;
  actions: AssistantAction[];
  unavailable: string | null;
  proposal: MutationProposalView | null;
};
