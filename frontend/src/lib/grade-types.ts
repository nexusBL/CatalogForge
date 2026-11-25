export type GradeLetter = "A" | "B" | "C" | "D" | "F";
export type GradeSectionId = "deterministic" | "nlp" | "vision";
export type EvidenceSeverity = "info" | "ordinary" | "hard";
export type EvidenceResult = "pass" | "fail" | "skip" | "error";

export type SectionGrade = {
  section: GradeSectionId;
  label: string;
  letter: GradeLetter;
  score: number;
};

export type FindingEvidence = {
  failed_criterion: string;
  affected_count: number;
  affected_field?: string | null;
  measured_value?: unknown;
  paths: string[];
  details: Record<string, unknown>;
};

export type GradeRecommendation = {
  finding_id: string;
  priority: number;
  action: string;
  section: GradeSectionId;
  check_id: string;
  severity: EvidenceSeverity;
};

export type GradeFinding = {
  finding_id: string;
  section: GradeSectionId;
  check_id: string;
  severity: EvidenceSeverity;
  result: EvidenceResult;
  why: string;
  evidence: FindingEvidence;
  recommendation?: GradeRecommendation | null;
};

export type GradeExplanation = {
  catalogue_id: string;
  graded_head_revision: number;
  graded_state_hash: string;
  engine_version: string;
  explanation_version: string;
  overall_grade: GradeLetter;
  overall_score: number;
  overall_why: string;
  section_grades: SectionGrade[];
  findings: GradeFinding[];
  recommendations: GradeRecommendation[];
  fix_first?: GradeRecommendation | null;
  priority_rule: string;
  derived: true;
};
