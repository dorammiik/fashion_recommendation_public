"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- planner_contracts ----

"""Planner conditional input contract shared by instructions and validators.

Neutral module: no agent/prompt imports. Existing base contracts remain unchanged.
"""
PLANNER_VERSION = "v4"
CONTRACT_VERSION = "planner-input-conditions-v2"
CONDITIONAL_REFS = (("warm", ("stylist_agent", "search_agent", "ranking_agent"), "request.preference_profile"), ("stylist", ("search_agent",), "agent_outputs.stylist_result"), ("relation", ("ranking_agent", "summary_agent"), "agent_outputs.ralationRatio"))

@_preserve_function('conditional_required_refs', 'fashion_recommendation_v2.planner.planner_contracts')
def conditional_required_refs(agent, *, warm=False, stylist=False, relation=False):
    active = {"warm": warm, "stylist": stylist, "relation": relation}
    return {ref for condition, agents, ref in CONDITIONAL_REFS if active[condition] and agent in agents}

@_preserve_function('conditional_input_instructions', 'fashion_recommendation_v2.planner.planner_contracts')
def conditional_input_instructions(agent):
    labels = {"warm": "state.user_state=warm이면", "stylist": "Stylist 단계가 있으면", "relation": "relation_intent가 있으면"}
    return "\n".join((f'  조건부 추가 참조: {labels[condition]} "{ref}"를 반드시 추가한다.' for condition, agents, ref in CONDITIONAL_REFS if agent in agents))
