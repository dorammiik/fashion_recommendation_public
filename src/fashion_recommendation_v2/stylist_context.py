"""Shared preparation and resolved-only projection; no agent or prompt dependencies."""
from fashion_recommendation_v2.module_compat import import_module as _role_module

def stylist_context(request, assessment, *, include_similarity=False):
    intent = assessment.relation_intent
    if not intent or (intent.relation_type != 'compatibility' and not include_similarity):
        return {}
    from fashion_recommendation_v2.relation.relation_evidence import packet
    from fashion_recommendation_v2.relation.relation_evidence import CATEGORY_REF
    from fashion_recommendation_v2.relation.relation_evidence import source_definition
    if intent.anchor_item_id:
        matches = [r for r in request.reference_items if r.item.item_id == intent.anchor_item_id
                   and (intent.anchor_rank is None or r.rank == intent.anchor_rank)]
        if len(matches) != 1:
            raise ValueError('Stylist requires exactly one matching anchor ID/rank snapshot.')
        reference = matches[0]
        evidence = packet(reference.item, reference.search_analysis, 'anchor')
    else:
        evidence = dict(item_id=None, image_url=None, category=intent.anchor_category,
            facts=[dict(ref=CATEGORY_REF, attribute='category', attribute_key='category',
                value=intent.anchor_category, status='known', kind='metadata')], observations=[],
            limitations=[dict(kind='category_anchor', reason='Only confirmed category is supplied.')])
    evidence['source_definition'] = source_definition()
    return dict(original_user_request=request.original_user_query or request.user_query,
                relation_intent=intent.model_copy(deep=True), anchor_evidence=evidence)



def project_stylist_result(result):
    """Keep source values; omit unresolved proposals and their associated prose together."""
    data = result.model_dump(mode='json')
    kept = [i for i, entry in enumerate(result.interpretations) if entry.state_id in result.resolved_state_ids or getattr(entry, 'origin', None) == 'preference']
    data['interpretations'] = [data['interpretations'][i] for i in kept]
    data['unresolved_states'] = []
    # Reports may include both unresolved and resolved proposals in free text.
    # Preserve full reports in original_stylist_resolution, never use them as search conditions.
    data['compatibility_guidance'] = []
    from fashion_recommendation_v2.schemas.stylist import StylistResult_base as StylistResult
    return type(result).model_validate(data)


