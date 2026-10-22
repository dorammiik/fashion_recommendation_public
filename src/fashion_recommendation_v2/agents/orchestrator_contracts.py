"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- orchestrator_contracts ----

"""Shared deterministic plan validation and search input projection."""
from fashion_recommendation_v2.stylist_context import stylist_context
from fashion_recommendation_v2.planner.planner_contracts import conditional_required_refs
from fashion_recommendation_v2.schemas.planner import ExecutionPlan
from fashion_recommendation_v2.orchestrator_policy import ORCHESTRATOR_V2_ASSESSMENT_MODEL
from fashion_recommendation_v2.orchestrator_policy import ASSESSMENT_CONTRACTS
from fashion_recommendation_v2.orchestrator_validation import validate_segmentation
from fashion_recommendation_v2.orchestrator_validation import validate_similarity_assessment
OUTPUTS = dict(stylist_agent='StylistResult', search_agent='CandidateSet', relation_agent='ralationRatio', ranking_agent='FinalRanking', summary_agent='RecommendationResponse')
REFS = dict(stylist_agent='agent_outputs.stylist_result', search_agent='agent_outputs.candidate_set', relation_agent='agent_outputs.ralationRatio', ranking_agent='agent_outputs.final_ranking')

@_preserve_function('validate_plan', 'fashion_recommendation_v2.agents.orchestrator_contracts')
def validate_plan(plan, unresolved_states=(), *, require_profile=False, require_relation=False):
    plan = ExecutionPlan.model_validate(plan.model_dump())
    steps = sorted(plan.steps, key=lambda step: step.order)
    expected_agents = list(OUTPUTS) if unresolved_states else list(OUTPUTS)[1:]
    if not require_relation:
        expected_agents.remove('relation_agent')
    expected_ids = {entry.state_id for entry in unresolved_states}
    if set(plan.unresolved_states) != expected_ids or len(plan.unresolved_states) != len(expected_ids):
        raise ValueError('Plan must preserve the orchestrator-provided unresolved state IDs.')
    if [s.agent for s in steps] != expected_agents:
        raise ValueError('Plan must contain exactly the scenario agents in dependency order.')
    if [s.order for s in steps] != list(range(1, len(steps) + 1)) or len({s.step_id for s in steps}) != len(steps):
        raise ValueError('Plan orders must be contiguous and step IDs unique.')
    available = {'request.user_query', 'request.requested_count', 'request.preference_profile'}
    completed = set()
    for index, step in enumerate(steps):
        if step.status != 'pending' or step.expected_output != OUTPUTS[step.agent]:
            raise ValueError('Plan status/output does not match the registered agent.')
        if not set(step.depends_on) <= completed:
            raise ValueError('Plan contains unknown, forward, or cyclic dependencies.')
        if index and steps[index - 1].step_id not in step.depends_on:
            raise ValueError('Each downstream step must depend on the preceding producer.')
        if not set(step.required_inputs) <= available:
            raise ValueError('Plan references unavailable inputs.')
        conditional = conditional_required_refs(step.agent, warm=require_profile, stylist=bool(unresolved_states), relation=require_relation)
        if 'agent_outputs.stylist_result' in conditional and 'agent_outputs.stylist_result' not in step.required_inputs:
            raise ValueError('Search must declare the Stylist output dependency.')
        if 'request.preference_profile' in conditional and 'request.preference_profile' not in step.required_inputs:
            raise ValueError('Warm plan must declare request.preference_profile.')
        needed = {'relation_agent': 'agent_outputs.candidate_set', 'ranking_agent': 'agent_outputs.candidate_set', 'summary_agent': 'agent_outputs.final_ranking'}.get(step.agent)
        if needed and needed not in step.required_inputs:
            raise ValueError(f'{step.agent} must declare {needed}.')
        if step.agent == 'summary_agent' and 'agent_outputs.candidate_set' not in step.required_inputs:
            raise ValueError('Summary must declare its CandidateSet input.')
        if 'agent_outputs.ralationRatio' in conditional and 'agent_outputs.ralationRatio' not in step.required_inputs:
            raise ValueError('Relation consumers must declare ralationRatio.')
        completed.add(step.step_id)
        if step.agent in REFS:
            available.add(REFS[step.agent])
    return steps

@_preserve_function('project_search_request', 'fashion_recommendation_v2.agents.orchestrator_contracts')
def project_search_request(request, assessment, stylist_result, *, contextual_audience=False, search_policy_version=None, orchestrator_version=None):
    """Delete entire unresolved units, never rewrite/translate user conditions."""
    from fashion_recommendation_v2.schemas.search.requirements.search_requirements import SearchAgentInput_legacy as SearchAgentInput
    from fashion_recommendation_v2.schemas.search.requirements.search_requirements import SimilarityReference
    from fashion_recommendation_v2.stylist_context import project_stylist_result
    from fashion_recommendation_v2.compatibility import ORCHESTRATOR_VERSION
    orchestrator_version = orchestrator_version or ORCHESTRATOR_VERSION
    modern_versions = {'v25', 'v26', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}
    assessment = validate_segmentation(assessment, request.user_query, version=orchestrator_version)
    validate_similarity_assessment(request, assessment)
    resolved = set(stylist_result.resolved_state_ids) if stylist_result else set()
    omitted = {s.state_id for s in assessment.unresolved_states} - resolved
    if assessment.unresolved_states and (not resolved) and (not any((unit.kind == 'clear_condition' for unit in assessment.semantic_units))):
        raise ValueError('Search requires a clear condition or a resolved state.')
    from fashion_recommendation_v2.orchestrator_quotes import quote_based
    from fashion_recommendation_v2.orchestrator_quotes import retained_query
    mask = set()
    for unit in assessment.semantic_units:
        if unit.state_id in omitted:
            if not unit.independently_removable:
                raise ValueError('Unsafe omission.')
            if not quote_based(assessment):
                for span in unit.spans:
                    mask.update(range(span.start, span.end))
    # Whitespace boundaries prevent accidental concatenation of retained words.
    query = retained_query(request.user_query, assessment, omitted) if quote_based(assessment) else ''.join((' ' if i in mask else char for i, char in enumerate(request.user_query))).strip()
    if not query:
        raise ValueError('Search projection is empty.')
    projection = None
    if stylist_result:
        projection = project_stylist_result(stylist_result)
    reference = None
    from fashion_recommendation_v2.schemas.search.requirements.search_requirements_context import AudienceContextV1
    from fashion_recommendation_v2.schemas.search.requirements.search_requirements_context import AudienceReferenceV1
    audience_reference = None
    if assessment.relation_intent and assessment.relation_intent.anchor_item_id:
        anchor = next((r.item for r in request.reference_items if r.item.item_id == assessment.relation_intent.anchor_item_id))
        anchor_analysis = next((r.search_analysis for r in request.reference_items if r.item.item_id == anchor.item_id)) if search_policy_version in modern_versions - {'v25'} else None
        audience_reference = AudienceReferenceV1.from_item(anchor, anchor_analysis)
    if assessment.relation_intent and assessment.relation_intent.relation_type == 'similarity':
        anchor = next((r.item for r in request.reference_items if r.item.item_id == assessment.relation_intent.anchor_item_id))
        reference = SimilarityReference.from_item(anchor, request.original_user_query or request.user_query, anchor_analysis)
    input_schema, provenance = (SearchAgentInput, {})
    if search_policy_version in modern_versions:
        from fashion_recommendation_v2.schemas.search.requirements.search_requirements import SearchAgentInputV25_v25 as SearchAgentInputV25
        input_schema = SearchAgentInputV25
        contextual_audience = True
        provenance = dict(original_user_query=request.original_user_query or request.user_query, original_stylist_resolution=stylist_result.model_copy(deep=True) if stylist_result else None)
    if search_policy_version in {'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
        from fashion_recommendation_v2.schemas.search.requirements.search_requirements import SearchAgentInputV37_v37 as SearchAgentInputV37
        input_schema = SearchAgentInputV37
        provenance['relation_intent'] = assessment.relation_intent
    intent = assessment.relation_intent
    contract = ASSESSMENT_CONTRACTS.get(orchestrator_version)
    if contract is not None and contract.compose_search_query and (search_policy_version in modern_versions) and intent and (intent.relation_type == 'compatibility') and (intent.source_text in query) and projection and projection.interpretations:
        from fashion_recommendation_v2.query_composition import compose_search_query
        context = stylist_context(request, assessment)
        composition = compose_search_query(retained_user_query=query, relation_intent=intent, anchor_evidence=context['anchor_evidence'], stylist_resolution=projection)
        provenance.update(search_query_composition=composition, relation_intent=intent)
        query = composition.effective_query
    if search_policy_version in {'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
        from fashion_recommendation_v2.schemas.search.requirements.search_requirements import SearchAgentInputV47_v47 as SearchAgentInputV47
        input_schema = SearchAgentInputV47
    elif search_policy_version == 'v46':
        from fashion_recommendation_v2.schemas.search.requirements.search_requirements import SearchAgentInputV46_v46 as SearchAgentInputV46
        input_schema = SearchAgentInputV46
    if search_policy_version in {'v58', 'v59', 'v60', 'v61'}:
        from fashion_recommendation_v2.schemas.search.requirements.search_requirements import SearchAgentInputV58_search_requirements_v58 as SearchAgentInputV58
        from fashion_recommendation_v2.schemas.search.requirements.search_requirements import search_stylist_resolution_v58_search_requirements_v58 as search_stylist_resolution_v58
        input_schema = SearchAgentInputV58
        provenance.pop('original_stylist_resolution', None)
        projection = search_stylist_resolution_v58(stylist_result)
    source = input_schema(request_id=request.request_id, user_query=query, **provenance, goal=f'{query}\n최종 추천 개수: {request.requested_count}개', current_date=request.current_date, requested_count=request.requested_count, stylist_resolution=projection, similarity_reference=reference, audience_context_v1=AudienceContextV1(user_query=request.original_user_query or request.user_query, reference=audience_reference) if contextual_audience else None, preference_profile=request.usable_preference_profile.model_copy(deep=True) if request.usable_preference_profile else None)
    if search_policy_version in {'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
        # Keep the caller's validation context aligned with Search's prepared
        # input, including category anchors introduced in v48. v50 deliberately
        # shares the v49 wire contract; resolve through the release registry.
        from fashion_recommendation_v2.search.contracts import search_schemas
        source = search_schemas(search_policy_version).prepare_input(source)
    if search_policy_version in {'v57', 'v58', 'v59', 'v60', 'v61'}:
        from fashion_recommendation_v2.schemas.search.requirements.search_requirements import RequirementExtractionScopeV57_search_requirements_v57 as RequirementExtractionScopeV57
        units = []
        for unit in assessment.semantic_units:
            role = 'omitted_unresolved' if unit.state_id in omitted else 'stylist_resolved' if unit.state_id in resolved else 'direct_user' if unit.kind == 'clear_condition' else 'context_only'
            units.append(dict(unit_id=unit.unit_id, state_id=unit.state_id, role=role, spans=[s.model_dump() for s in unit.spans]))
        # Direct extraction has its own authoritative span projection, not string deletion.
        # Keep transport/provenance queries intact for relation and citation consumers.
        if quote_based(assessment):
            from fashion_recommendation_v2.schemas.search.requirements.search_requirements import RequirementQuoteScope_search_requirements_v57 as RequirementQuoteScope
            source.requirement_extraction_scope = RequirementQuoteScope(source_text=request.user_query, direct_user_text='\n'.join((span['source_text'] for u in units if u['role'] == 'direct_user' for span in u['spans'])), units=units)
        else:
            direct_positions = {i for u in units if u['role'] == 'direct_user' for span in u['spans'] for i in range(span['start'], span['end'])}
            source.requirement_extraction_scope = RequirementExtractionScopeV57(source_text=request.user_query, direct_user_text=''.join((c if i in direct_positions else ' ' for i, c in enumerate(request.user_query))).strip(), units=units)
    return source
# Shared with saved-state validation; keep the historical import available.
from fashion_recommendation_v2.schemas.orchestrator import omitted_conditions
