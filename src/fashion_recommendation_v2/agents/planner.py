"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- planner ----

from fashion_recommendation_v2.llm.base import StructuredLLM
from fashion_recommendation_v2.prompts.planner import PLANNER_SYSTEM_PROMPT
from fashion_recommendation_v2.schemas.planner import ExecutionPlan
from fashion_recommendation_v2.schemas.planner import PlannerInput
from fashion_recommendation_v2.planner.planner_contracts import PLANNER_VERSION
PLANNER_MODEL = 'gpt-6-luna'
PLANNER_REASONING_EFFORT = 'low'
PLANNER_MAX_OUTPUT_TOKENS = 4096

@_preserve_class('PlannerAgent', 'fashion_recommendation_v2.agents.planner')
class PlannerAgent:
    evaluation_version = PLANNER_VERSION

    def __init__(self, llm: StructuredLLM, *, max_output_tokens: int | None=None):
        self.llm = llm
        self.max_output_tokens = max_output_tokens

    def run(self, planner_input: PlannerInput) -> ExecutionPlan:
        return self.llm.generate(system_prompt=PLANNER_SYSTEM_PROMPT, user_input=planner_input, output_schema=ExecutionPlan, **{'max_output_tokens': self.max_output_tokens} if self.max_output_tokens is not None else {})
