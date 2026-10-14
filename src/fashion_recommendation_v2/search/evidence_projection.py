"""Evidence-only product projections shared by downstream consumers.

Identity/commerce stay on the retrieved record. Observed semantics live in
search_analysis. No requirement satisfaction, Q, V or ranking score becomes a fact.
"""
from fashion_recommendation_v2.module_compat import import_module as _role_module
from fashion_recommendation_v2.schemas.stylist import StylistDetailValue_base as StylistDetailValue


def fact_key(fact):
    return 'detail.' + fact.value.key if isinstance(fact.value, StylistDetailValue) else fact.attribute


def validate_product_facts(analysis, item):
    from fashion_recommendation_v2.search.product_sources import present_field
    from fashion_recommendation_v2.search.condition_semantics import METADATA_ONLY_FACTS
    facts = analysis.product_facts_v26
    if facts is None:
        raise ValueError('v26 requires explicit product_facts_v26 (empty when unknown).')
    existing = {a.attribute for a in analysis.attributes}
    keys = [fact_key(f) for f in facts]
    if len(keys) != len(set(keys)) or set(keys) & existing:
        raise ValueError('Product facts must not duplicate each other or the eight attribute dimensions.')
    for fact in facts:
        if any(c.attribute in {fact.attribute, fact_key(fact)} for c in analysis.conflicts):
            raise ValueError('An unresolved conflicting product fact must remain unknown/omitted.')
        if any(not present_field(item, p, None) for p in fact.evidence_fields):
            raise ValueError(f'{fact_key(fact)} cites absent product metadata.')
        if any(e.image_url != item.image_url for e in fact.image_evidence):
            raise ValueError(f'{fact_key(fact)} cites another product image.')
        if fact_key(fact) in METADATA_ONLY_FACTS and not fact.evidence_fields:
            raise ValueError(f'{fact.attribute} needs metadata evidence, not visual inference.')


def semantic_facts(analysis):
    """Conflicts remain available to callers, but are never confirmed facts."""
    if analysis is None:
        return []
    if analysis.evaluation_policy in {'v36', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
        from fashion_recommendation_v2.search.product_evaluation import semantic_entries as entries
        return [f for _, f in entries(analysis)]
    disputed = {c.attribute for c in analysis.conflicts}
    return [f for f in [*analysis.known_attributes, *(analysis.product_facts_v26 or [])]
            if f.attribute not in disputed and fact_key(f) not in disputed]


def semantic_entries(analysis):
    """Return fixed paths in the original search_analysis, never invented aliases."""
    if analysis.evaluation_policy in {'v36', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
        from fashion_recommendation_v2.search.product_evaluation import semantic_entries as entries
        return entries(analysis)
    usable = semantic_facts(analysis)
    return [(f'search_analysis.{collection}.{index}', feature)
            for collection in ('attributes', 'product_facts_v26')
            for index, feature in enumerate(getattr(analysis, collection) or [])
            if feature in usable]


def semantic_values(analysis):
    return {fact_key(f): (list(f.value.values) if isinstance(f.value, StylistDetailValue)
            else list(f.value) if isinstance(f.value, list) else [f.value])
            for f in semantic_facts(analysis)}


def semantic_projection(analysis):
    if analysis is None:
        return None
    def text_evidence(value):
        data = value.model_dump(mode='json', exclude={'fixed_by_requirement_ids', 'group', 'image_evidence'})
        data['image_observations'] = [e.observation for e in value.image_evidence]
        return data
    data = dict(item_id=analysis.item_id, facts=[text_evidence(f) for f in semantic_facts(analysis)],
        conflicts=[text_evidence(c) for c in getattr(analysis, 'conflicts', [])])
    if analysis.evaluation_policy in {'v36', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
        data['consistency_observations'] = [dict(source_path=f'search_analysis.attributes.{i}',
            attribute=row.attribute, metadata=row.metadata.model_dump(mode='json'),
            image_observation=row.image_observation.model_dump(mode='json') if row.image_observation else None,
            comparison=row.metadata_image_consistency.model_dump(mode='json'),
            code_validation=row.code_validation.model_dump(mode='json'))
            for i, row in enumerate(analysis.attributes)
            if row.metadata_image_consistency.status not in {'consistent', 'metadata_missing', 'not_applicable'}]
    return data


def validate_analysis_identity(item, analysis):
    if analysis is not None and (analysis.item_id != item.item_id or analysis.image_url != item.image_url):
        raise ValueError('Search analysis must belong to the exact product and image.')
    if getattr(item, 'record_version', None) == 'search_product_v26' and analysis is None:
        raise ValueError('v26 product semantics require search_analysis.')
