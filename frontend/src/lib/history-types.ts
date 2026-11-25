export type EditHistoryRecord = {
  id: string;
  catalogue_id: string;
  user_id: string;
  organization_id: string;
  source: "improvement" | "mutation" | "media" | "rollback";
  operation: string;
  path: string | null;
  item_name: string | null;
  previous_value: unknown;
  new_value: unknown;
  proposal_id: string | null;
  media_job_id: string | null;
  rolled_back_history_id: string | null;
  actor: string;
  approval_state: "APPLIED";
  before_grade_letter: string | null;
  before_grade_score: number | null;
  after_grade_letter: string | null;
  after_grade_score: number | null;
  before_section_scores: Record<string, number>;
  after_section_scores: Record<string, number>;
  resolved_issue_ids: string[];
  overall_score_delta: number | null;
  created_at: string;
};

export type EditHistoryListResponse = {
  records: EditHistoryRecord[];
};
