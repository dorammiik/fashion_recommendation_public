"""Compatibility preparation shared by orchestration and styling, without agent imports."""
from fashion_recommendation_v2.module_compat import import_module as _role_module
from copy import deepcopy

ORCHESTRATOR_VERSION = 'v1'
STYLIST_VERSION = 'v1'


def validate_compatibility_assessment(request, assessment):
    intent = assessment.relation_intent
    if assessment.decision != 'proceed' or not intent or intent.relation_type != 'compatibility':
        return
    # Enforce routing against supplied semantic spans, not case IDs or Korean keywords.
    starts = [i for i in range(len(request.user_query)) if request.user_query.startswith(intent.source_text, i)]
    assigned = {s.state_id for s in assessment.unresolved_states if s.resolution_agent == 'stylist_agent'}
    spans = [s for u in assessment.semantic_units if u.state_id in assigned for s in u.spans]
    if not any(max(start, span.start) < min(start + len(intent.source_text), span.end)
               for start in starts for span in spans):
        raise ValueError('Compatibility requires a Stylist unresolved state for the relationship phrase; '
                         'a resolved anchor does not resolve target styling conditions.')


def validate_stylist_compatibility(source, result, criteria, *, profile_indices=frozenset()):
    compatibility = source.relation_intent and source.relation_intent.relation_type == 'compatibility'
    rows = result.compatibility_guidance
    if not compatibility:
        if rows:
            raise ValueError('Compatibility guidance requires a confirmed compatibility intent.')
        return
    if len(rows) != len(criteria) or {r.criterion for r in rows} != set(criteria):
        raise ValueError('Compatibility guidance must cover each of the five criteria exactly once.')
    definitions = source.anchor_evidence['source_definition']
    CATEGORY_REF = definitions['category_anchor_ref']
    facts = {f['ref']: f for f in source.anchor_evidence.get('facts', [])}
    used = set()
    for row in rows:
        if len(set(row.anchor_evidence_refs)) != len(row.anchor_evidence_refs):
            raise ValueError('Duplicate Stylist anchor reference.')
        for ref in row.anchor_evidence_refs:
            fact = facts.get(ref)
            if fact is None or fact['status'] != 'known':
                raise ValueError('Stylist must cite a supplied known anchor observation.')
            if ref == CATEGORY_REF and row.criterion != 'category_pairing':
                raise ValueError('Category-only anchor has no other observed features.')
            if fact['kind'] == 'search_image_observation' and (
                fact['attribute'] in definitions['metadata_only_attributes'] or row.criterion in definitions['metadata_only_facets']):
                raise ValueError('Metadata-only evidence cannot use image observations.')
        if not row.anchor_evidence_refs and not row.limitations:
            raise ValueError('Missing anchor evidence requires an explicit limitation.')
        if len(set(row.interpretation_indices)) != len(row.interpretation_indices):
            raise ValueError('Duplicate interpretation index.')
        for index in row.interpretation_indices:
            if index >= len(result.interpretations):
                raise ValueError('Guidance references a missing interpretation.')
            used.add(index)
    if used & profile_indices:
        raise ValueError('Profile-grounded interpretations must not be connected to compatibility guidance.')
    if used != set(range(len(result.interpretations))) - profile_indices:
        raise ValueError('Every proposed interpretation must be connected to compatibility guidance.')
    if any(not i.search_text for i in result.interpretations):
        raise ValueError('Compatibility interpretations require target search_text.')


def response_record(response=None, error=None):
    """Snapshot received payload before validation; absence remains explicit."""
    snapshot = getattr(error, 'response_snapshot', None) if error else None
    if snapshot is not None:
        return deepcopy(snapshot)
    raw = getattr(response, '_model_response', None)
    if raw is None and hasattr(response, 'model_dump'):
        raw = response.model_dump(mode='json', exclude_unset=True)
    elif raw is None and isinstance(response, (dict, list, str, int, float, bool)):
        raw = response
    return dict(model_response=deepcopy(raw), model_response_text=getattr(response, '_model_response_text', None))
