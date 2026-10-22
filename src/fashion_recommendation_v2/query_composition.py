"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- query_composition ----

"""Deterministic composition and provenance enforcement; no model calls or agent imports."""
import json
from fashion_recommendation_v2.schemas.query_composition import SearchQueryComposition
from fashion_recommendation_v2.schemas.query_composition import SearchQuerySegment
COMPOSED_USER_SOURCE_PATHS = ('search_query_composition.retained_user_query', 'original_user_query')

@_preserve_function('compose_search_query', 'fashion_recommendation_v2.query_composition')
def compose_search_query(*, retained_user_query, relation_intent, anchor_evidence, stylist_resolution):
    """Render only validated, resolved inputs. Keep OR values and observations intact."""
    if relation_intent.relation_type != 'compatibility' or relation_intent.source_text not in retained_user_query:
        raise ValueError('Composition requires a retained, confirmed compatibility clause.')
    if not stylist_resolution or not stylist_resolution.interpretations:
        raise ValueError('Composition requires resolved Stylist interpretations.')
    if any((i.state_id not in stylist_resolution.resolved_state_ids and getattr(i, 'origin', None) != 'preference' for i in stylist_resolution.interpretations)):
        raise ValueError('Unresolved Stylist interpretations cannot enter effective_query.')
    if anchor_evidence.get('item_id') != relation_intent.anchor_item_id or anchor_evidence.get('category') != relation_intent.anchor_category:
        raise ValueError('Composition anchor must match the confirmed intent.')
    parts = [(retained_user_query, 'user', ['retained_user_query'])]
    if relation_intent.anchor_category:
        description = f'함께 입을 기준 카테고리: {relation_intent.anchor_category}.'
        refs = [anchor_evidence['source_definition']['category_anchor_ref']]
    else:
        marker = f'이전 추천 {relation_intent.anchor_rank}번, ' if relation_intent.anchor_rank else ''
        description = f'함께 입을 기준 상품({marker}ID={relation_intent.anchor_item_id}).'
        refs = ['relation_intent.anchor_item_id']
        for fact in anchor_evidence['facts']:
            if fact['status'] != 'known':
                continue
            observation = fact['value']
            value = observation.get('value') if isinstance(observation, dict) else observation
            description += f" {fact['attribute_key']}={json.dumps(value, ensure_ascii=False)} ({fact['ref']})."
            refs.append(fact['ref'])
        # Conflicting/insufficient observations stay explicit, never silently reconciled.
        if anchor_evidence.get('limitations'):
            description += ' 관찰 제한: ' + json.dumps(anchor_evidence['limitations'], ensure_ascii=False)
    parts.append((description, 'anchor', refs))
    for index, interpretation in enumerate(stylist_resolution.interpretations):
        value = interpretation.model_dump(mode='json')['value']
        sentence = interpretation.search_text or f'{interpretation.attribute}={json.dumps(value, ensure_ascii=False)}'
        text = f'추천 대상의 Stylist 제안(soft, 리스트 값은 OR 대안): {sentence} [구조화 원값: {interpretation.attribute}={json.dumps(value, ensure_ascii=False)}]'
        parts.append((text, 'stylist', [f'stylist_resolution.interpretations.{index}']))
    segments, offset = ([], 0)
    for text, role, refs in parts:
        segments.append(SearchQuerySegment(role=role, text=text, start=offset, end=offset + len(text), source_refs=refs))
        offset += len(text) + 1
    return SearchQueryComposition(effective_query='\n'.join((p[0] for p in parts)), retained_user_query=retained_user_query, relation_intent=relation_intent, segments=segments, anchor_evidence=anchor_evidence, resolved_state_ids=stylist_resolution.resolved_state_ids)

@_preserve_function('validate_composed_input', 'fashion_recommendation_v2.query_composition')
def validate_composed_input(source):
    composition = getattr(source, 'search_query_composition', None)
    if composition is None:
        return
    if source.user_query != composition.effective_query or source.relation_intent != composition.relation_intent:
        raise ValueError('Search must preserve the composed effective_query and confirmed intent.')
    expected = compose_search_query(retained_user_query=composition.retained_user_query, relation_intent=source.relation_intent, anchor_evidence=composition.anchor_evidence, stylist_resolution=source.stylist_resolution)
    if composition != expected:
        raise ValueError('Composition differs from the preserved resolved Stylist/anchor inputs.')

@_preserve_function('validate_composed_conditions', 'fashion_recommendation_v2.query_composition')
def validate_composed_conditions(source, conditions):
    """Check before recovery/suppression so generated prose cannot become user constraints."""
    composition = getattr(source, 'search_query_composition', None)
    if composition is None:
        return
    validate_composed_input(source)
    texts = []
    for path in COMPOSED_USER_SOURCE_PATHS:
        value = source
        for field in path.split('.'):
            value = getattr(value, field)
        texts.append(value)
    for condition in conditions:
        if condition.source == 'user' and (not condition.source_text.strip() or any((condition.source_text not in text for text in texts))):
            raise ValueError(f'{condition.requirement_id}: composed Stylist/anchor prose is not a user condition; quote retained actual user words and preserve structured Stylist provenance.')
