from fashion_recommendation_v2.module_compat import import_module as _role_module
from datetime import datetime
from typing import Literal

from pydantic import Field

from fashion_recommendation_v2.schemas.base import StrictBaseModel
from fashion_recommendation_v2.schemas.relation_intent import RelationIntent
from fashion_recommendation_v2.schemas.common import AgentName
from fashion_recommendation_v2.schemas.common import OutputName
from fashion_recommendation_v2.schemas.common import StateRef


class PlannerUnresolvedState(StrictBaseModel):
    state_id: str
    description: str

    resolution_agent: AgentName | None = None


class AvailableAgent(StrictBaseModel):
    name: AgentName
    description: str
    output_schema: OutputName


class PlannerStateSnapshot(StrictBaseModel):
    user_state: Literal[
        "cold",
        "warm",
    ]

    product_source: Literal[
        "ebay",
        "hm",
    ]

    profile_lookup_status: Literal["not_found", "empty", "available", "failed"] = "not_found"

    completed_outputs: list[OutputName] = Field(
        default_factory=list
    )


class PlannerInput(StrictBaseModel):
    request_id: str

    user_query: str

    goal: str

    unresolved_states: list[
        PlannerUnresolvedState
    ] = Field(default_factory=list)

    relation_intent: RelationIntent | None = None

    state: PlannerStateSnapshot

    available_agents: list[
        AvailableAgent
    ]


class PlanStep(StrictBaseModel):
    step_id: str

    order: int = Field(ge=1)

    agent: AgentName

    objective: str

    depends_on: list[str] = Field(
        default_factory=list
    )

    required_inputs: list[StateRef] = Field(
        default_factory=list
    )

    expected_output: OutputName

    status: Literal[
        "pending",
        "running",
        "completed",
        "failed",
        "skipped",
    ] = "pending"


class ExecutionPlan(StrictBaseModel):
    plan_id: str

    goal: str

    unresolved_states: list[str] = Field(
        default_factory=list
    )

    steps: list[PlanStep]

    created_at: datetime