"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- stylist_context ----

"""Shared preparation and resolved-only projection; no agent or prompt dependencies."""

@_preserve_function('stylist_context', 'fashion_recommendation_v2.stylist_context')
def stylist_context(request, assessment, *, include_similarity=False):
    intent = assessment.relation_intent
    if not intent or (intent.relation_type != 'compatibility' and (not include_similarity)):
        return {}
    from fashion_recommendation_v2.relation.relation_evidence import packet
    from fashion_recommendation_v2.relation.relation_evidence import CATEGORY_REF
    from fashion_recommendation_v2.relation.relation_evidence import source_definition
    if intent.anchor_item_id:
        matches = [r for r in request.reference_items if r.item.item_id == intent.anchor_item_id and (intent.anchor_rank is None or r.rank == intent.anchor_rank)]
        if len(matches) != 1:
            raise ValueError('Stylist requires exactly one matching anchor ID/rank snapshot.')
        reference = matches[0]
        evidence = packet(reference.item, reference.search_analysis, 'anchor')
    else:
        evidence = dict(item_id=None, image_url=None, category=intent.anchor_category, facts=[dict(ref=CATEGORY_REF, attribute='category', attribute_key='category', value=intent.anchor_category, status='known', kind='metadata')], observations=[], limitations=[dict(kind='category_anchor', reason='Only confirmed category is supplied.')])
    evidence['source_definition'] = source_definition()
    return dict(original_user_request=request.original_user_query or request.user_query, relation_intent=intent.model_copy(deep=True), anchor_evidence=evidence)

@_preserve_function('project_stylist_result', 'fashion_recommendation_v2.stylist_context')
def project_stylist_result(result):
    """Keep source values; omit unresolved proposals and their associated prose together."""
    data = result.model_dump(mode='json')
    kept = [i for i, entry in enumerate(result.interpretations) if entry.state_id in result.resolved_state_ids or getattr(entry, 'origin', None) == 'preference']
    data['interpretations'] = [data['interpretations'][i] for i in kept]
    data['unresolved_states'] = []
    # Preserve full reports in original_stylist_resolution, never use them as search conditions.
    # Reports may include both unresolved and resolved proposals in free text.
    data['compatibility_guidance'] = []
    from fashion_recommendation_v2.schemas.stylist import StylistResult_base as StylistResult
    return type(result).model_validate(data)

@_preserve_function('scoped_stylist_input', 'fashion_recommendation_v2.stylist_context')
def scoped_stylist_input(request, assessment, assigned, *, profile_lookup_status='not_found'):
    """Project validated assessment spans, excluding request_context from v8 inputs."""
    from fashion_recommendation_v2.schemas.stylist import StylistAgentInputV8_stylist_v8 as StylistAgentInputV8
    from fashion_recommendation_v2.personalization_policy import effective_mode
    from fashion_recommendation_v2.orchestrator_quotes import quote_based
    from fashion_recommendation_v2.orchestrator_quotes import related_units
    states = {s.state_id: s for s in assessment.unresolved_states}
    texts = {}
    clear = []
    for unit in assessment.semantic_units:
        for span in unit.spans:
            span.validate_against(request.user_query)
            if unit.kind == 'clear_condition':
                clear.append(span.source_text)
    # Also accept an assigned relationship suffix with its own linked
    # Suffix matching excludes anchor-only overlap and a broader quote
    # neither the original relation quote nor state evidence is rewritten.
    # semantic-unit quote. The omitted prefix is anchor context;
    # that appends an unrelated target/condition after the relation.
    for state in assigned:
        if state.state_id not in states or states[state.state_id].resolution_agent != 'stylist_agent':
            raise ValueError('Stylist assignment must reference an assessed Stylist state.')
        allowed = [span for unit in assessment.semantic_units if unit.kind == 'unresolved_condition' and unit.state_id == state.state_id for span in unit.spans]
        evidence = states[state.state_id].evidence
        for span in evidence:
            span.validate_against(request.user_query)
            # A semantic unit may split one phrase into multiple token spans.
            # All non-whitespace evidence characters must belong to this state.
            if not quote_based(assessment) and any((not request.user_query[i].isspace() and (not any((a.start <= i < a.end for a in allowed))) for i in range(span.start, span.end))):
                raise ValueError('Stylist state evidence must belong to its unresolved semantic unit.')
        texts[state.state_id] = [span.source_text for span in evidence]
    context = stylist_context(request, assessment, include_similarity=True)
    context.pop('original_user_request', None)
    # Do not reintroduce excluded delegation through a relation's source quote.
    if assessment.relation_intent:
        quote = assessment.relation_intent.source_text
        if quote_based(assessment):
            if not quote or quote not in request.user_query:
                raise ValueError('Stylist relation source must quote the original request.')
            if assessment.relation_intent.relation_type == 'compatibility':
                # not invalidate an assigned state's relationship evidence.
                # v12 permits overlapping quotations. A broader context unit must
                assigned_ids = {state.state_id for state in assigned}
                linked_ids = {unit.state_id for unit in assessment.semantic_units if unit.kind == 'unresolved_condition' and unit.state_id in assigned_ids}
                full_quote_assigned = any((quote in text for sid in linked_ids for text in texts[sid]))
                short_quote_assigned = any((text and quote.endswith(text) and (text != quote) and (request.user_query.count(text) == 1) and (request.user_query.count(quote) == 1) and any((unit.kind == 'unresolved_condition' and unit.state_id == sid and any((span.source_text == text for span in unit.spans)) for unit in assessment.semantic_units)) for sid in linked_ids for text in texts[sid]))
                if not (full_quote_assigned or short_quote_assigned):
                    raise ValueError('Stylist relation source must belong to assigned state evidence.')
            elif any((u.kind == 'request_context' for u in related_units(assessment, quote))):
                raise ValueError('Stylist relation source must not include request_context.')
        else:
            excluded = [span for unit in assessment.semantic_units if unit.kind == 'request_context' for span in unit.spans]
            positions = [i for i in range(len(request.user_query)) if request.user_query.startswith(quote, i)]
            if not positions or any((any((i < span.end and span.start < i + len(quote) for span in excluded)) for i in positions)):
                # Known-reference similarity retains its separate routing policy.
                raise ValueError('Stylist relation source must not include request_context.')
    return StylistAgentInputV8(user_request='\n'.join((t for s in assigned for t in texts[s.state_id])), unresolved_states=[dict(state_id=s.state_id, description='\n'.join(texts[s.state_id]), resolution_agent='stylist_agent') for s in assigned], state_source_texts=texts, clear_condition_context=clear, user_id=request.user_id, personalization_mode=effective_mode(request.personalization_mode, assessment.relation_intent), profile_lookup_status=profile_lookup_status, **context)
