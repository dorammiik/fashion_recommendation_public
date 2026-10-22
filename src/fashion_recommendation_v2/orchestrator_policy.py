"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- orchestrator_policy ----

"""Assessment release selection and unchanged call policy, without agent/prompt imports."""
from dataclasses import dataclass
from types import MappingProxyType
ORCHESTRATOR_V2_ASSESSMENT_MODEL = 'gpt-6-luna'
ASSESSMENT_MAX_ATTEMPTS = 2

@_preserve_class('AssessmentContract', 'fashion_recommendation_v2.orchestrator_policy')
@dataclass(frozen=True)
class AssessmentContract:
    prompt_module: str = 'orchestrator'
    prompt_name: str = 'ORCHESTRATOR_PROMPT'
    correction_prompt_name: str = 'ORCHESTRATOR_CORRECTION_PROMPT_V4'
    collected_validation: bool = False
    force_assessment_model: bool = False
    compose_search_query: bool = True
    preserve_personalized_version: bool = False
    strict_agent_inputs: bool = False
    restore_omitted_conditions: bool = False
    removal_feedback: bool = False
    terminal_period_warning: bool = False
    reuse_ranking_handoff: bool = False
    derive_quote_coordinates: bool = False
    quote_only: bool = False
ASSESSMENT_CONTRACTS = MappingProxyType({'v12': AssessmentContract('orchestrator_v12', 'ORCHESTRATOR_PROMPT_V12', correction_prompt_name='ORCHESTRATOR_CORRECTION_PROMPT_V12', collected_validation=True, force_assessment_model=True, preserve_personalized_version=True, strict_agent_inputs=True, restore_omitted_conditions=True, reuse_ranking_handoff=True, quote_only=True), 'v11': AssessmentContract('orchestrator_v11', 'ORCHESTRATOR_PROMPT_V11', correction_prompt_name='ORCHESTRATOR_CORRECTION_PROMPT_V11', collected_validation=True, force_assessment_model=True, preserve_personalized_version=True, strict_agent_inputs=True, restore_omitted_conditions=True, removal_feedback=True, terminal_period_warning=True, reuse_ranking_handoff=True, derive_quote_coordinates=True), 'v10': AssessmentContract('orchestrator_v9', 'ORCHESTRATOR_PROMPT_V9', correction_prompt_name='ORCHESTRATOR_CORRECTION_PROMPT_V9', collected_validation=True, force_assessment_model=True, preserve_personalized_version=True, strict_agent_inputs=True, restore_omitted_conditions=True, removal_feedback=True, terminal_period_warning=True, reuse_ranking_handoff=True), 'v9': AssessmentContract('orchestrator_v9', 'ORCHESTRATOR_PROMPT_V9', correction_prompt_name='ORCHESTRATOR_CORRECTION_PROMPT_V9', collected_validation=True, force_assessment_model=True, preserve_personalized_version=True, strict_agent_inputs=True, restore_omitted_conditions=True, removal_feedback=True, terminal_period_warning=True), 'v0': AssessmentContract(compose_search_query=False), 'v1': AssessmentContract(), 'v2': AssessmentContract(), 'v3': AssessmentContract('orchestrator_v3', 'ORCHESTRATOR_PROMPT_V3', force_assessment_model=True, preserve_personalized_version=True), 'v8': AssessmentContract('orchestrator_v8', 'ORCHESTRATOR_PROMPT_V8', correction_prompt_name='ORCHESTRATOR_CORRECTION_PROMPT_V8', collected_validation=True, force_assessment_model=True, preserve_personalized_version=True, strict_agent_inputs=True, restore_omitted_conditions=True, removal_feedback=True), 'v7': AssessmentContract('orchestrator_v7', 'ORCHESTRATOR_PROMPT_V7', correction_prompt_name='ORCHESTRATOR_CORRECTION_PROMPT_V7', collected_validation=True, force_assessment_model=True, preserve_personalized_version=True, strict_agent_inputs=True, restore_omitted_conditions=True), 'v6': AssessmentContract('orchestrator_v4', 'ORCHESTRATOR_PROMPT_V4', collected_validation=True, force_assessment_model=True, preserve_personalized_version=True, strict_agent_inputs=True, restore_omitted_conditions=True), 'v5': AssessmentContract('orchestrator_v4', 'ORCHESTRATOR_PROMPT_V4', collected_validation=True, force_assessment_model=True, preserve_personalized_version=True), 'v4': AssessmentContract('orchestrator_v4', 'ORCHESTRATOR_PROMPT_V4', collected_validation=True, force_assessment_model=True, preserve_personalized_version=True)})

@_preserve_function('assessment_contract', 'fashion_recommendation_v2.orchestrator_policy')
def assessment_contract(version):
    from fashion_recommendation_v2.compatibility import ORCHESTRATOR_VERSION
    try:
        return ASSESSMENT_CONTRACTS[version or ORCHESTRATOR_VERSION]
    except KeyError:
        raise ValueError('Unsupported Orchestrator version') from None

@_preserve_function('recorded_version', 'fashion_recommendation_v2.orchestrator_policy')
def recorded_version(version, personalized):
    return version if not personalized or assessment_contract(version).preserve_personalized_version else 'v2'
