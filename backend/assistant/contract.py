"""Phase 9 assistant HTTP and planner contracts. Extra planner keys are forbidden."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.mutation.contract import MutationProposalView

MAX_MESSAGE_CHARS = 2_000
MAX_TEXT_CHARS = 400
MAX_FINDINGS = 5
MAX_OBSERVATIONS = 5
MAX_TOOLS_PER_TURN = 3

AssistantIntent = Literal[
    "open_catalogue",
    "open_grade",
    "open_improvements",
    "open_reviews",
    "open_media",
    "show_baba_score",
    "explain_catalogue_grade",
    "explain_fix_first",
    "explain_review_complaints",
    "explain_items_attention",
    "explain_item_findings",
    "explain_org_grades",
    "explain_catalogue_summary",
    "explain_capabilities",
    "explain_problems",
    "refuse_mutation",
    "propose_mutation",
    "clarify",
    "unsupported",
]

AssistantToolName = Literal[
    "get_catalogue_summary",
    "get_grade_explanation",
    "get_baba_score",
    "get_review_intelligence",
    "get_item_context",
    "list_improvement_proposals",
    "list_org_grade_summaries",
]

ALLOWED_TOOLS: frozenset[str] = frozenset(
    {
        "get_catalogue_summary",
        "get_grade_explanation",
        "get_baba_score",
        "get_review_intelligence",
        "get_item_context",
        "list_improvement_proposals",
        "list_org_grade_summaries",
    }
)

WRITE_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "create_catalogue",
        "update_catalogue",
        "delete_catalogue",
        "change_price",
        "add_item",
        "remove_item",
        "apply_improvement",
        "approve_improvement",
        "rollback_history",
        "apply_rollback",
        "rollback_edit",
        "create_media_job",
        "execute_media_job",
        "grade",
        "regrade",
        "publish",
        "collect_reviews",
        "create_review_intelligence",
    }
)


class AssistantClientContext(BaseModel):
    current_route: str | None = None


class AssistantTurnRequest(BaseModel):
    message: str
    context: AssistantClientContext | None = None

    @field_validator("message")
    @classmethod
    def message_present_and_bounded(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValueError("message is required")
        if len(text) > MAX_MESSAGE_CHARS:
            raise ValueError("message exceeds the Phase 9 size limit")
        return text


class AssistantAction(BaseModel):
    label: str
    href: str


class AssistantTurnResponse(BaseModel):
    message: str
    intent: AssistantIntent
    used_llm: bool
    actions: list[AssistantAction] = Field(default_factory=list)
    unavailable: str | None = None
    proposal: MutationProposalView | None = None


class PlannerOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: AssistantIntent
    item_name: str | None = None
    tool: AssistantToolName | None = None

    @field_validator("item_name")
    @classmethod
    def strip_item_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None
