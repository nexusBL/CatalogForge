"""Append-only catalogue edit history. Proposals are not history."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

HISTORY_VERSION = "edit_history.v1"

HistorySource = Literal["improvement", "mutation", "media", "rollback"]
ApprovalState = Literal["APPLIED"]


class GradeSnapshot(BaseModel):
    letter: str | None = None
    score: float | None = None
    section_scores: dict[str, float] = Field(default_factory=dict)
    finding_ids: list[str] = Field(default_factory=list)
    check_ids: list[str] = Field(default_factory=list)


class EditHistoryRecord(BaseModel):
    id: str
    catalogue_id: str
    user_id: str
    organization_id: str
    source: HistorySource
    operation: str
    path: str | None = None
    item_name: str | None = None
    previous_value: Any = None
    new_value: Any = None
    restore_spec: dict[str, Any] = Field(default_factory=dict)
    proposal_id: str | None = None
    media_job_id: str | None = None
    rolled_back_history_id: str | None = None
    actor: str
    provenance: dict[str, Any] = Field(default_factory=dict)
    approval_state: ApprovalState = "APPLIED"
    before_grade_letter: str | None = None
    before_grade_score: float | None = None
    after_grade_letter: str | None = None
    after_grade_score: float | None = None
    before_section_scores: dict[str, float] = Field(default_factory=dict)
    after_section_scores: dict[str, float] = Field(default_factory=dict)
    resolved_issue_ids: list[str] = Field(default_factory=list)
    overall_score_delta: float | None = None
    source_head_revision: int | None = None
    result_head_revision: int | None = None
    created_at: str
    history_version: str = HISTORY_VERSION


class EditHistoryListResponse(BaseModel):
    records: list[EditHistoryRecord] = Field(default_factory=list)


class RollbackRequest(BaseModel):
    confirm: bool = False


class HistoryRejected(ValueError):
    pass
