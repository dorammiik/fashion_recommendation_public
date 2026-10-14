"""Durable request classification and confirmation, separate from recommendation execution."""
from fashion_recommendation_v2.module_compat import import_module as _role_module
from typing import Literal
from pydantic import Field
from pydantic import model_validator
from fashion_recommendation_v2.schemas.quick_start import QuickStartID
from fashion_recommendation_v2.schemas.quick_start import QuickStartSnapshot
from fashion_recommendation_v2.schemas.base import StrictBaseModel
from fashion_recommendation_v2.schemas.orchestrator import OrchestratorState


class ConversationDecision(StrictBaseModel):
    kind: Literal['new', 'followup', 'ambiguous']
    reason: str = Field(min_length=1)
    effective_query: str | None

    @model_validator(mode='after')
    def valid_query(self):
        if self.kind == 'ambiguous':
            if self.effective_query is not None:
                raise ValueError('Ambiguous request must wait before consolidation')
        elif not self.effective_query or not self.effective_query.strip():
            raise ValueError('Resolved request needs an effective query')
        return self


class ConversationInput(StrictBaseModel):
    user_query: str = Field(min_length=1)
    previous_query: str | None = None
    previous_response: dict | None = None
    confirmed_kind: Literal['new', 'followup'] | None = None
    validation_feedback: list[str] = Field(default_factory=list)


class ConversationRecord(StrictBaseModel):
    quick_start: QuickStartID | None = None
    quick_start_snapshot: QuickStartSnapshot | None = None
    personalization_mode: Literal['cold', 'warm'] | None = None
    request_id: str
    user_id: str
    user_query: str = Field(min_length=1)
    previous_request_id: str | None = None
    session_id: str | None = None
    status: Literal['queued', 'classifying', 'awaiting_confirmation', 'running', 'completed', 'blocked', 'failed', 'interrupted']
    revision: int = Field(default=1, ge=1)
    decision: ConversationDecision | None = None
    question: str | None = None
    state: OrchestratorState | None = None
    attempts: list[dict] = Field(default_factory=list)
    error_type: str | None = None
    idempotency_key: str | None = None
    new_request: bool = False
    confirmed_kind: Literal['new', 'followup'] | None = None
    updated_at: str | None = None
    progress: dict = Field(default_factory=dict)
    resumable: bool = False
    recovery_reason: str | None = None
