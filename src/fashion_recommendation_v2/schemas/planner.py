"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- planner ----

from datetime import datetime
from typing import Literal
from pydantic import Field
from fashion_recommendation_v2.schemas.base import StrictBaseModel
from fashion_recommendation_v2.schemas.relation_intent import RelationIntent
from fashion_recommendation_v2.schemas.common import AgentName
from fashion_recommendation_v2.schemas.common import OutputName
from fashion_recommendation_v2.schemas.common import StateRef

@_preserve_class('PlannerUnresolvedState', 'fashion_recommendation_v2.schemas.planner')
class PlannerUnresolvedState(StrictBaseModel):
    state_id: str
    description: str
    resolution_agent: AgentName | None = None

@_preserve_class('AvailableAgent', 'fashion_recommendation_v2.schemas.planner')
class AvailableAgent(StrictBaseModel):
    name: AgentName
    description: str
    output_schema: OutputName

@_preserve_class('PlannerStateSnapshot', 'fashion_recommendation_v2.schemas.planner')
class PlannerStateSnapshot(StrictBaseModel):
    user_state: Literal["cold", "warm"]
    product_source: Literal["ebay", "hm"]
    profile_lookup_status: Literal["not_found", "empty", "available", "failed"] = "not_found"
    completed_outputs: list[OutputName] = Field(default_factory=list)

@_preserve_class('PlannerInput', 'fashion_recommendation_v2.schemas.planner')
class PlannerInput(StrictBaseModel):
    request_id: str
    user_query: str
    goal: str
    unresolved_states: list[PlannerUnresolvedState] = Field(default_factory=list)
    relation_intent: RelationIntent | None = None
    state: PlannerStateSnapshot
    available_agents: list[AvailableAgent]

@_preserve_class('PlanStep', 'fashion_recommendation_v2.schemas.planner')
class PlanStep(StrictBaseModel):
    step_id: str
    order: int = Field(ge=1)
    agent: AgentName
    objective: str
    depends_on: list[str] = Field(default_factory=list)
    required_inputs: list[StateRef] = Field(default_factory=list)
    expected_output: OutputName
    status: Literal["pending", "running", "completed", "failed", "skipped"] = "pending"

@_preserve_class('ExecutionPlan', 'fashion_recommendation_v2.schemas.planner')
class ExecutionPlan(StrictBaseModel):
    plan_id: str
    goal: str
    unresolved_states: list[str] = Field(default_factory=list)
    steps: list[PlanStep]
    created_at: datetime
