"""Role-consolidated implementation; service contracts and behavior are preserved."""
from __future__ import annotations
from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function

# ---- orchestrator ----
"""Single-request orchestration contracts, without agent calls or state mutation.

Validate complete snapshots after updates (models are mutable like existing agent
contracts). Natural-language meaning and safe search projection need runtime checks.
"""


from datetime import date
from typing import Annotated
from typing import Literal as Literal_base
from typing import Self
from typing import Any as Any_base

from pydantic import Field as Field_base
from pydantic import model_validator
from pydantic import model_serializer
from pydantic import PrivateAttr

from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_base
from fashion_recommendation_v2.schemas.relation_intent import RelationIntent
from fashion_recommendation_v2.schemas.relation import RelationRatio
from fashion_recommendation_v2.schemas.relation import ReferenceItem
from fashion_recommendation_v2.schemas.preference_profile import PreferenceProfile
from fashion_recommendation_v2.schemas.preference_profile import Attribute
from fashion_recommendation_v2.schemas.planner import ExecutionPlan
from fashion_recommendation_v2.schemas.planner import PlannerUnresolvedState
from fashion_recommendation_v2.schemas.ranking import FinalRanking
from fashion_recommendation_v2.schemas.ranking import RankingAgentInput_base as RankingAgentInput
from fashion_recommendation_v2.schemas.search.candidate_pool.search_candidate_pool import CandidateSet
from fashion_recommendation_v2.schemas.stylist import StylistResultV3_v3 as StylistResultV3
from fashion_recommendation_v2.schemas.stylist import StylistConditionProvenanceV3_v3 as StylistConditionProvenanceV3
from fashion_recommendation_v2.schemas.stylist import StylistResultV4_v4 as StylistResultV4
from fashion_recommendation_v2.schemas.stylist import StylistConditionProvenanceV4_v4 as StylistConditionProvenanceV4
from fashion_recommendation_v2.schemas.stylist import StylistResultV5_v5 as StylistResultV5
from fashion_recommendation_v2.schemas.stylist import StylistConditionProvenanceV5_v5 as StylistConditionProvenanceV5
from fashion_recommendation_v2.schemas.stylist import StylistResultV6
from fashion_recommendation_v2.schemas.stylist import StylistConditionProvenanceV6
from fashion_recommendation_v2.schemas.stylist import StylistResultV2_v2 as StylistResultV2
from fashion_recommendation_v2.schemas.stylist import StylistAgentInput_base as StylistAgentInput
from fashion_recommendation_v2.schemas.stylist import StylistResult_base as StylistResult
from fashion_recommendation_v2.schemas.summary import BlockedResponse
from fashion_recommendation_v2.schemas.summary import BlockedSummaryInput
from fashion_recommendation_v2.schemas.summary import SummaryAgentInput_base as SummaryAgentInput
from fashion_recommendation_v2.schemas.summary_response import RecommendationResponse

Text = Annotated[str, Field_base(min_length=1, pattern=r"\S")]
Count = Annotated[int, Field_base(ge=1)]


@_preserve_function('omitted_conditions', 'fashion_recommendation_v2.schemas.orchestrator')
def omitted_conditions(assessment, stylist_result):
    from fashion_recommendation_v2.schemas.summary import OmittedCondition
    if stylist_result is None:
        return []
    states = {s.state_id: s for s in assessment.unresolved_states}
    return [OmittedCondition(state_id=entry.state_id,
        source_text=states[entry.state_id].evidence[0].source_text,
        reason=states[entry.state_id].description + ': ' + entry.reason)
        for entry in stylist_result.unresolved_states]


@_preserve_function('validate_agent_request', 'fashion_recommendation_v2.schemas.orchestrator')
def validate_agent_request(request, versions):
    """Validate required downstream fields from their owning schemas, without defaults."""
    from pydantic import TypeAdapter
    from fashion_recommendation_v2.orchestrator_policy import ASSESSMENT_CONTRACTS
    contract = ASSESSMENT_CONTRACTS.get(versions.get('orchestrator'))
    if contract is None or not contract.strict_agent_inputs:
        return
    fields = {}
    if versions.get('stylist') in {'v5', 'v6'}:
        from fashion_recommendation_v2.schemas.stylist import StylistAgentInputV2_v2 as StylistAgentInputV2
        fields.update({key: StylistAgentInputV2.model_fields[key]
                       for key in ('personalization_mode', 'user_id')})
    if versions.get('ranking') in {'ranking_eval_v14', 'ranking_eval_v15'}:
        from fashion_recommendation_v2.schemas.ranking import RankingAgentInputV13
        fields['personalization_mode'] = RankingAgentInputV13.model_fields['personalization_mode']
    for name, field in fields.items():
        try:
            TypeAdapter(Annotated[field.annotation, *field.metadata] if field.metadata else field.annotation).validate_python(getattr(request, name))
        except ValueError as exc:
            raise ValueError(f"Orchestrator {versions.get('orchestrator')} requires explicit valid request.{name} for the configured agents") from exc


@_preserve_class('SourceSpan', 'fashion_recommendation_v2.schemas.orchestrator')
class SourceSpan(StrictBaseModel_base):
    """Exact Python string slice [start:end], using Unicode character offsets."""
    __qualname__ = 'SourceSpan'
    start: int = Field_base(ge=0)
    end: int = Field_base(ge=1)
    source_text: Text

    @model_validator(mode='after')
    def validate_range(self) -> Self:
        if self.end <= self.start:
            raise ValueError('Source span end must exceed start.')
        return self

    def validate_against(self, user_query: str) -> Self:
        if self.end > len(user_query) or user_query[self.start:self.end] != self.source_text:
            raise ValueError('Source span must exactly match the user query.')
        return self


@_preserve_class('AssessedState', 'fashion_recommendation_v2.schemas.orchestrator')
class AssessedState(StrictBaseModel_base):
    __qualname__ = 'AssessedState'
    state_id: Text
    description: Text
    resolution_agent: Literal_base['stylist_agent'] | None
    reason: Text
    evidence: list[SourceSpan] = Field_base(min_length=1)
    blocker: Literal_base['missing_reference', 'conflicting_constraints', 'unsupported_marketplace'] | None = None

    @model_validator(mode='after')
    def validate_route(self) -> Self:
        if (self.blocker is None) != (self.resolution_agent == 'stylist_agent'):
            raise ValueError('A state is either assigned to Stylist or an initial blocker.')
        return self


@_preserve_class('SemanticUnit', 'fashion_recommendation_v2.schemas.orchestrator')
class SemanticUnit(StrictBaseModel_base):
    """One indivisible meaning, including negation, OR and dependent modifiers."""
    __qualname__ = 'SemanticUnit'
    unit_id: Text
    kind: Literal_base['clear_condition', 'unresolved_condition', 'request_context']
    spans: list[SourceSpan] = Field_base(min_length=1)
    state_id: Text | None = None
    independently_removable: bool
    depends_on: list[Text] = Field_base(default_factory=list)


@_preserve_class('RequestAssessment', 'fashion_recommendation_v2.schemas.orchestrator')
class RequestAssessment(StrictBaseModel_base):
    """LLM output stored under agent_outputs, including all decision evidence."""
    __qualname__ = 'RequestAssessment'
    decision: Literal_base['proceed', 'blocked']
    goal: Text | None
    requested_count: Count | None
    count_source: Literal_base['explicit', 'default', 'unresolved']
    count_evidence: list[SourceSpan] = Field_base(default_factory=list)
    reason: Text
    unresolved_states: list[AssessedState] = Field_base(default_factory=list)
    semantic_units: list[SemanticUnit] = Field_base(default_factory=list)
    preference_category: str | None = None
    preference_attributes: list[Attribute] = Field_base(default_factory=list)
    use_title_keywords: bool = False
    relation_intent: RelationIntent | None = None

    @model_validator(mode='after')
    def validate_decision(self) -> Self:
        ids = [entry.state_id for entry in self.unresolved_states]
        if len(ids) != len(set(ids)):
            raise ValueError('Assessment state IDs must be unique.')
        blocked = any(entry.blocker is not None for entry in self.unresolved_states)
        if blocked != (self.decision == 'blocked'):
            raise ValueError('Blocked assessment requires an initial blocker; proceed forbids one.')
        if self.decision == 'proceed' and (self.goal is None or self.requested_count is None):
            raise ValueError('Proceed requires a goal and count.')
        if self.count_source == 'unresolved':
            if self.requested_count is not None or self.decision != 'blocked':
                raise ValueError('Unresolved count must remain null in a blocked assessment.')
        elif self.requested_count is None:
            raise ValueError('Explicit/default count must be present.')
        if self.count_source == 'default' and (self.requested_count != 5 or self.count_evidence):
            raise ValueError('Default count is 5 without explicit count evidence.')
        if self.count_source == 'explicit' and not self.count_evidence:
            raise ValueError('Explicit count requires source evidence.')
        return self

    def validate_against(self, user_query: str) -> Self:
        result = RequestAssessment.model_validate(self.model_dump())
        for span in result.count_evidence:
            span.validate_against(user_query)
        for entry in result.unresolved_states:
            for span in entry.evidence:
                span.validate_against(user_query)
        return result


@_preserve_class('RequestContext', 'fashion_recommendation_v2.schemas.orchestrator')
class RequestContext(StrictBaseModel_base):
    __qualname__ = 'RequestContext'
    personalization_mode: Literal_base['cold', 'warm'] | None = None
    request_id: Text
    session_id: Text
    user_query: Text
    current_date: date
    user_state: Literal_base['cold', 'warm', 'unknown'] = 'cold'
    mode: Literal_base['live', 'offline']
    product_source: Literal_base['ebay'] = 'ebay'
    preference_profile: PreferenceProfile | None = None
    usable_preference_profile: PreferenceProfile | None = None
    profile_lookup_status: Literal_base["not_requested", "not_found", "empty", "available", "failed"] = "not_found"
    profile_lookup_error: str | None = None
    user_id: Text | None = None
    original_user_query: Text | None = None
    parent_request_id: Text | None = None
    interaction_collection_enabled: bool = False
    profile_updates_enabled: bool = False
    reference_items: list[ReferenceItem] = Field_base(default_factory=list)

    @property
    def legacy_profile_lookup_status(self):
        return 'not_found' if self.personalization_mode is not None else self.profile_lookup_status

    @model_validator(mode='after')
    def validate_profile_context(self) -> Self:
        if self.personalization_mode is not None and (self.preference_profile is not None or self.usable_preference_profile is not None):
            raise ValueError('v2 personalization is Ranking-only; profiles must not enter other agents')
        for profile in (self.preference_profile, self.usable_preference_profile):
            if profile and self.user_id and profile.user_id != self.user_id:
                raise ValueError('Profile must belong to request user')
        if self.user_state == 'warm' and self.usable_preference_profile is None:
            raise ValueError('Warm requires usable request-specific preference evidence')
        if self.usable_preference_profile and self.preference_profile is None:
            raise ValueError('Usable view requires a stored snapshot')
        return self


@_preserve_class('PendingRequestState', 'fashion_recommendation_v2.schemas.orchestrator')
class PendingRequestState(RequestContext):
    """Before assessment or when an initial blocker prevents request confirmation."""
    __qualname__ = 'PendingRequestState'
    phase: Literal_base['pending'] = 'pending'
    goal: None = None
    requested_count: None = None


@_preserve_class('StructuredRequestAssessment', 'fashion_recommendation_v2.schemas.orchestrator')
class StructuredRequestAssessment_base(RequestAssessment):
    __qualname__ = 'StructuredRequestAssessment'
    semantic_units: list[SemanticUnit] = Field_base(min_length=1)
    _model_response: Any_base = PrivateAttr(default=None)
    _model_response_text: str | None = PrivateAttr(default=None)


@_preserve_class('AssessmentInput', 'fashion_recommendation_v2.schemas.orchestrator')
class AssessmentInput_base(PendingRequestState):
    __qualname__ = 'AssessmentInput'
    character_offsets: list[str]
    validation_feedback: list[str] = Field_base(default_factory=list)

@_preserve_class('RequestState', 'fashion_recommendation_v2.schemas.orchestrator')
class RequestState(RequestContext):
    __qualname__ = 'RequestState'
    phase: Literal_base['ready'] = 'ready'
    goal: Text
    requested_count: Count


@_preserve_class('UnresolvedState', 'fashion_recommendation_v2.schemas.orchestrator')
class UnresolvedState(StrictBaseModel_base):
    __qualname__ = 'UnresolvedState'
    state_id: Text
    description: Text
    resolution_agent: Literal_base['stylist_agent'] | None
    status: Literal_base['unresolved', 'resolved'] = 'unresolved'


@_preserve_class('ExecutionError', 'fashion_recommendation_v2.schemas.orchestrator')
class ExecutionError(StrictBaseModel_base):
    """Preserve every failed attempt, including Summary and fallback separately."""
    __qualname__ = 'ExecutionError'
    stage: Literal_base['request_assessment', 'planner', 'plan_validation', 'stylist',
                   'search', 'search_projection', 'relation', 'ranking', 'summary', 'blocked_summary', 'fallback_summary', 'state_validation']
    step_id: Text | None = None
    code: Text
    error_type: Text
    message: Text
    attempt: int = Field_base(ge=1)


@_preserve_class('ExecutionState', 'fashion_recommendation_v2.schemas.orchestrator')
class ExecutionState(StrictBaseModel_base):
    __qualname__ = 'ExecutionState'
    status: Literal_base['planning', 'executing', 'completed', 'blocked', 'failed'] = 'planning'
    execution_plan: ExecutionPlan | None = None
    current_step_id: Text | None = None
    blocked_at: Literal_base['request_assessment', 'stylist'] | None = None
    errors: list[ExecutionError] = Field_base(default_factory=list)

    @model_validator(mode='after')
    def validate_execution(self) -> Self:
        if self.execution_plan is not None:
            ids = [step.step_id for step in self.execution_plan.steps]
            if not ids or len(ids) != len(set(ids)):
                raise ValueError('Stored plan must have nonempty steps with unique IDs.')
        if (self.status == 'blocked') != (self.blocked_at is not None):
            raise ValueError('Only blocked execution must specify blocked_at.')
        if self.status == 'failed' and not self.errors:
            raise ValueError('Failed execution requires an error record.')
        if self.current_step_id is not None:
            if self.execution_plan is None or self.current_step_id not in {
                step.step_id for step in self.execution_plan.steps
            }:
                raise ValueError('Current step must reference the stored plan.')
        if self.status in ('completed', 'blocked') and self.current_step_id is not None:
            raise ValueError('Terminal successful/blocked execution has no active step.')
        return self


@_preserve_class('AgentOutputs', 'fashion_recommendation_v2.schemas.orchestrator')
class AgentOutputs(StrictBaseModel_base):
    __qualname__ = 'AgentOutputs'
    relation_result: None = Field_base(default=None, exclude=True)  # Read legacy null artifacts.
    request_assessment: RequestAssessment | None = None
    stylist_result: StylistResultV6 | StylistResultV5 | StylistResultV4 | StylistResultV3 | StylistResultV2 | StylistResult | None = None
    candidate_set: CandidateSet | None = None
    ralationRatio: RelationRatio | None = None
    final_ranking: FinalRanking | None = None
    recommendation_response: RecommendationResponse | None = None
    blocked_response: BlockedResponse | None = None
    fallback_response: BlockedResponse | None = None

    @property
    def usable_relation(self):
        return self.ralationRatio if self.ralationRatio and not self.ralationRatio.omitted else None


@_preserve_class('OrchestratorState', 'fashion_recommendation_v2.schemas.orchestrator')
class OrchestratorState(StrictBaseModel_base):
    __qualname__ = 'OrchestratorState'
    request: Annotated[PendingRequestState | RequestState, Field_base(discriminator='phase')]
    unresolved_states: list[UnresolvedState] = Field_base(default_factory=list)
    execution: ExecutionState = Field_base(default_factory=ExecutionState)
    agent_outputs: AgentOutputs = Field_base(default_factory=AgentOutputs)
    state_version: int = Field_base(default=1, ge=1)
    agent_versions: dict[str, str] = Field_base(default_factory=dict,
        description="Explicit producer versions; empty for historical snapshots before version recording.")

    @model_serializer(mode='wrap')
    def serialize_versions(self, handler):
        data = handler(self)
        if not self.agent_versions:
            data.pop('agent_versions', None)  # Preserve the historical code-state envelope.
        return data

    @model_validator(mode='after')
    def validate_snapshot(self) -> Self:
        outputs = self.agent_outputs
        assessment = outputs.request_assessment
        states = {entry.state_id: entry for entry in self.unresolved_states}
        if len(states) != len(self.unresolved_states):
            raise ValueError('State IDs must be unique.')
        if assessment is None:
            if states or isinstance(self.request, RequestState) or any(
                getattr(outputs, name) is not None for name in type(outputs).model_fields
            ) or self.execution.status not in ('planning', 'failed') or self.execution.execution_plan is not None:
                raise ValueError('Unassessed request cannot have confirmed state, plan or outputs.')
            return self
        from fashion_recommendation_v2.orchestrator_policy import ASSESSMENT_CONTRACTS
        contract = ASSESSMENT_CONTRACTS.get(self.agent_versions.get('orchestrator'))
        validate_agent_request(self.request, self.agent_versions)
        if contract is not None and contract.collected_validation:
            from fashion_recommendation_v2.orchestrator_validation import validate_segmentation
            validate_segmentation(assessment, self.request.user_query, version=self.agent_versions.get('orchestrator'))
        else:
            assessment.validate_against(self.request.user_query)
        if self.execution.execution_plan is not None:
            plan_ids = self.execution.execution_plan.unresolved_states
            if len(plan_ids) != len(set(plan_ids)) or set(plan_ids) != set(states):
                raise ValueError('Stored plan must preserve assessment state IDs.')
        expected = {entry.state_id: entry for entry in assessment.unresolved_states}
        if states.keys() != expected.keys():
            raise ValueError('State ledger must preserve all assessment state IDs.')
        for key, entry in states.items():
            original = expected[key]
            if (entry.description, entry.resolution_agent) != (original.description, original.resolution_agent):
                raise ValueError('State ledger must preserve assessment descriptions and routing.')
        if assessment.decision == 'proceed':
            if not isinstance(self.request, RequestState) or (
                self.request.goal, self.request.requested_count
            ) != (assessment.goal, assessment.requested_count):
                raise ValueError('Confirmed request must match the assessment.')
        else:
            if not isinstance(self.request, PendingRequestState) or self.execution.blocked_at != 'request_assessment':
                raise ValueError('Initial blocker must retain a pending request and blocked execution.')
            if self.execution.execution_plan is not None:
                raise ValueError('Initial blocking occurs before planning.')
        resolved = set()
        if outputs.stylist_result is not None:
            if assessment.decision != 'proceed' or not states:
                raise ValueError('Stylist requires a proceeding request with assigned states.')
            from fashion_recommendation_v2.stylist_context import stylist_context
            context = (stylist_context(self.request, assessment, include_similarity=self.agent_versions.get('stylist') in {'v5', 'v6'})
                if self.agent_versions.get('stylist') in {'v0', 'v1', 'v2', 'v3', 'v4', 'v5', 'v6'} or outputs.stylist_result.compatibility_guidance else {})
            if isinstance(outputs.stylist_result, StylistResultV2):
                from fashion_recommendation_v2.schemas.stylist import StylistAgentInputV2_v2 as StylistAgentInputV2
                status = outputs.stylist_result.personalization_context.profile_status
                stylist_input = StylistAgentInputV2(**context, user_request=self.request.user_query,
                    user_id=self.request.user_id, personalization_mode=self.request.personalization_mode,
                    profile_lookup_status='not_found' if status == 'not_requested' else status,
                    unresolved_states=[PlannerUnresolvedState(state_id=s.state_id, description=s.description,
                        resolution_agent=s.resolution_agent) for s in self.unresolved_states])
            else:
                stylist_input = StylistAgentInput(**context, user_request=self.request.user_query, preference_profile=self.request.preference_profile, profile_lookup_status=self.request.legacy_profile_lookup_status, unresolved_states=[
                    PlannerUnresolvedState(state_id=s.state_id, description=s.description,
                                           resolution_agent=s.resolution_agent) for s in self.unresolved_states
                ])
            outputs.stylist_result.validate_against(stylist_input)
            resolved = set(outputs.stylist_result.resolved_state_ids)
        if {key for key, entry in states.items() if entry.status == 'resolved'} != resolved:
            raise ValueError('Ledger status must match validated Stylist resolution IDs.')
        has_clear_condition = any(unit.kind == 'clear_condition' for unit in assessment.semantic_units)
        if self.execution.blocked_at == 'stylist':
            if outputs.stylist_result is None or resolved or has_clear_condition:
                raise ValueError('Stylist blocking requires zero resolved states and no clear conditions.')
        if (outputs.stylist_result is not None and not resolved and not has_clear_condition
                and self.execution.blocked_at != 'stylist'):
            raise ValueError('Zero Stylist resolutions with no clear conditions require blocked execution.')
        if self.execution.status == 'blocked':
            if any(value is not None for value in (outputs.candidate_set, outputs.final_ranking,
                                                   outputs.recommendation_response)):
                raise ValueError('Blocked requests cannot have search/ranking/recommendation outputs.')
            reasons = ([(s.state_id, s.reason) for s in assessment.unresolved_states if s.blocker]
                       if self.execution.blocked_at == 'request_assessment' else
                       [(s.state_id, s.reason) for s in outputs.stylist_result.unresolved_states])
            source = BlockedSummaryInput(user_request=self.request.user_query,
                blocked_at=self.execution.blocked_at,
                unresolved_states=[dict(state_id=key, reason=reason) for key, reason in reasons])
            for response in (outputs.blocked_response, outputs.fallback_response):
                if response is not None:
                    response.validate_against(source)
        elif outputs.blocked_response is not None or outputs.fallback_response is not None:
            raise ValueError('Blocked copy requires blocked execution.')
        if outputs.fallback_response is not None and not any(
            error.stage == 'blocked_summary' for error in self.execution.errors
        ):
            raise ValueError('Fallback copy requires a recorded blocked Summary failure.')
        if outputs.candidate_set is not None and states and outputs.stylist_result is None:
            raise ValueError('Assigned states must be processed before Search.')
        if outputs.ralationRatio is not None:
            from fashion_recommendation_v2.schemas.relation import RelationAgentInput
            if outputs.candidate_set is None or assessment.relation_intent is None:
                raise ValueError('Relation requires candidates and an assessed intent.')
            anchor = next((r.item for r in self.request.reference_items
                           if r.item.item_id == assessment.relation_intent.anchor_item_id), None)
            outputs.ralationRatio.validate_against(RelationAgentInput(candidate_set=outputs.candidate_set,
                intent=assessment.relation_intent, anchor_item=anchor,
                evaluation_version=outputs.ralationRatio.evaluation_version,
                anchor_search_analysis=outputs.ralationRatio.anchor_search_analysis))
        if outputs.final_ranking is not None and outputs.candidate_set is None:
            raise ValueError('Ranking output requires candidates.')
        if outputs.final_ranking is not None:
            personalization = outputs.final_ranking.personalization_v12 or outputs.final_ranking.personalization_v11
            from fashion_recommendation_v2.personalization_policy import effective_mode
            expected_mode = (effective_mode(self.request.personalization_mode, assessment.relation_intent)
                if outputs.final_ranking.scoring_policy_version in {'ranking_eval_v13', 'ranking_eval_v13_relation', 'ranking_eval_v14', 'ranking_eval_v14_relation', 'ranking_eval_v15', 'ranking_eval_v15_relation'} else self.request.personalization_mode)
            if personalization is not None and expected_mode != personalization['personalization_mode']:
                raise ValueError('Ranking personalization mode differs from the frozen request')
            outputs.final_ranking.validate_against(RankingAgentInput(
                candidate_set=outputs.candidate_set, user_request=self.request.user_query,
                requested_count=self.request.requested_count, preference_profile=self.request.usable_preference_profile,
                ralationRatio=outputs.usable_relation,
                **({'relation_intent': assessment.relation_intent} if contract is not None and contract.reuse_ranking_handoff else {}),
            ))
        if outputs.recommendation_response is not None and outputs.final_ranking is None:
            raise ValueError('Recommendation output requires ranking.')
        if outputs.recommendation_response is not None:
            outputs.recommendation_response.validate_against(SummaryAgentInput(
                user_request=self.request.user_query, candidate_set=outputs.candidate_set,
                final_ranking=outputs.final_ranking, preference_profile=self.request.usable_preference_profile,
                ralationRatio=outputs.usable_relation,
                interaction_collection_enabled=self.request.interaction_collection_enabled,
                profile_updates_enabled=self.request.profile_updates_enabled,
                omitted_conditions=(omitted_conditions(assessment, outputs.stylist_result)
                    if contract is not None and contract.restore_omitted_conditions else []),
            ))
        if self.execution.status in ('executing', 'completed') and self.execution.execution_plan is None:
            raise ValueError('Execution requires a plan.')
        if self.execution.status == 'completed':
            if outputs.recommendation_response is None or any(
                step.status != 'completed' for step in self.execution.execution_plan.steps
            ):
                raise ValueError('Completion requires a response and completed plan steps.')
        return self


# ---- orchestrator_v4 ----
"""v4 correction input and code diagnostics; assessment output is the shared contract."""
from typing import Any
from typing import Literal as Literal_v4
from pydantic import Field as Field_v4
from fashion_recommendation_v2.orchestrator_policy import ASSESSMENT_MAX_ATTEMPTS
from fashion_recommendation_v2.schemas.base import StrictBaseModel
AssessmentInput = AssessmentInput_base
StructuredRequestAssessment = StructuredRequestAssessment_base


@_preserve_class('ValidationIssue', 'fashion_recommendation_v2.schemas.orchestrator_v4')
class ValidationIssue_v4(StrictBaseModel):
    __qualname__ = 'ValidationIssue'
    error_id: str
    code: str
    path: str
    message: str | None = None
    unit_id: str | None = None
    state_id: str | None = None
    start: int | None = None
    end: int | None = None
    source_text: str | None = None
    actual_text: str | None = None
    referenced_id: str | None = None
    related_paths: list[str] = Field_v4(default_factory=list)
    related_unit_ids: list[str] = Field_v4(default_factory=list)
    schema_error_type: str | None = None


@_preserve_class('DeferredCheck', 'fashion_recommendation_v2.schemas.orchestrator_v4')
class DeferredCheck(StrictBaseModel):
    __qualname__ = 'DeferredCheck'
    check: str
    path: str
    reason: str
    prerequisite_error_ids: list[str] = Field_v4(min_length=1)


@_preserve_class('AssessmentValidationReport', 'fashion_recommendation_v2.schemas.orchestrator_v4')
class AssessmentValidationReport_v4(StrictBaseModel):
    __qualname__ = 'AssessmentValidationReport'
    errors: list[ValidationIssue_v4] = Field_v4(default_factory=list)
    deferred_checks: list[DeferredCheck] = Field_v4(default_factory=list)


@_preserve_class('PreviousAssessmentResponse', 'fashion_recommendation_v2.schemas.orchestrator_v4')
class PreviousAssessmentResponse(StrictBaseModel):
    __qualname__ = 'PreviousAssessmentResponse'
    model_response: Any = None
    model_response_text: str | None = None
    parsing_error: str | None = None


@_preserve_class('AssessmentAttempt', 'fashion_recommendation_v2.schemas.orchestrator_v4')
class AssessmentAttempt(StrictBaseModel):
    __qualname__ = 'AssessmentAttempt'
    attempt_id: str
    attempt: int = Field_v4(ge=1, le=ASSESSMENT_MAX_ATTEMPTS)
    stage: Literal_v4['generation', 'correction']
    correction_of: str | None = None


@_preserve_class('AssessmentInputV4', 'fashion_recommendation_v2.schemas.orchestrator_v4')
class AssessmentInputV4_v4(AssessmentInput):
    __qualname__ = 'AssessmentInputV4'
    validation_feedback: AssessmentValidationReport_v4 = Field_v4(default_factory=AssessmentValidationReport_v4)
    previous_response: PreviousAssessmentResponse | None = None
    assessment_attempt: AssessmentAttempt


# ---- orchestrator_v9 ----
"""v9 diagnostic input; assessment output remains the shared structured contract."""
from typing import Literal
from pydantic import Field
AssessmentInputV4 = AssessmentInputV4_v4
AssessmentValidationReport = AssessmentValidationReport_v4
ValidationIssue = ValidationIssue_v4


@_preserve_class('CoverageWarning', 'fashion_recommendation_v2.schemas.orchestrator_v9')
class CoverageWarning(ValidationIssue):
    __qualname__ = 'CoverageWarning'
    code: Literal['uncovered_terminal_period']
    action: Literal['record_only']
    reason: str


@_preserve_class('AssessmentValidationReportV9', 'fashion_recommendation_v2.schemas.orchestrator_v9')
class AssessmentValidationReportV9(AssessmentValidationReport):
    __qualname__ = 'AssessmentValidationReportV9'
    warnings: list[CoverageWarning] = Field(default_factory=list)


@_preserve_class('AssessmentInputV9', 'fashion_recommendation_v2.schemas.orchestrator_v9')
class AssessmentInputV9(AssessmentInputV4):
    __qualname__ = 'AssessmentInputV9'
    validation_feedback: AssessmentValidationReportV9 = Field(default_factory=AssessmentValidationReportV9)
