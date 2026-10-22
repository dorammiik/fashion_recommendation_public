"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- requirements_policy_v57 ----

"""Request-specific v57 scopes and kind exceptions, without rewriting source facts."""
from fashion_recommendation_v2.search.stylist_policy import SEARCH_ATTRIBUTES_V50 as SEARCH_ATTRIBUTES_V50_requirements_policy_v57
from fashion_recommendation_v2.search.condition_semantics import provenance_dimension_v30 as provenance_dimension_v30_requirements_policy_v57
LENGTH_KEYS_requirements_policy_v57 = {'length', 'skirt_length'}
SMALL_FLORAL_VALUES_requirements_policy_v57 = {'small floral', 'ditsy floral', 'small-scale floral'}

@_preserve_function('values', 'fashion_recommendation_v2.search.requirements_policy_v57')
def values_requirements_policy_v57(row):
    value = row.value
    if hasattr(value, 'key'):
        value = value.values
    if isinstance(value, dict):
        value = value.get('values', [])
    return [str(v).casefold() for v in value] if isinstance(value, list) else [str(value).casefold()]

@_preserve_function('detail_key', 'fashion_recommendation_v2.search.requirements_policy_v57')
def detail_key_requirements_policy_v57(row):
    if row.attribute != 'detail':
        return ''
    return row.value.get('key', '') if isinstance(row.value, dict) else row.value.key

@_preserve_function('scope_for', 'fashion_recommendation_v2.search.requirements_policy_v57')
def scope_for_requirements_policy_v57(row, kind, polarity, conditions):
    key, options = (detail_key_requirements_policy_v57(row), values_requirements_policy_v57(row))
    if polarity == 'unrestricted' or row.attribute in {'price', 'avoid_product_type'}:
        return 'item'
    if key in LENGTH_KEYS_requirements_policy_v57:
        return 'search'
    if polarity == 'negative':
        return 'item'
    if row.attribute == 'fit':
        if row.source == 'reference' and any(('bodice' in value for value in options)):
            return 'item'
        if any((value in {'not too tight', 'not tight-fitting'} for value in options)):
            return 'item'
    if row.attribute == 'pattern' and SMALL_FLORAL_VALUES_requirements_policy_v57.intersection(options):
        if any((c.attribute == 'pattern' and 'floral' in values_requirements_policy_v57(c) for c in conditions if c.requirement_id != row.requirement_id)):
            return 'item'
    if key in {'silhouette', 'skirt_silhouette'} and row.source == 'reference':
        return 'search'
    # Preserve the historical fallback and immutable Stylist category aliases.
    dimension = provenance_dimension_v30_requirements_policy_v57(row.attribute, row.value)
    if dimension in SEARCH_ATTRIBUTES_V50_requirements_policy_v57 and (kind == 'hard' or row.source in {'user', 'stylist'}):
        return 'search'
    return 'item' if kind == 'hard' else None

@_preserve_function('expected_kind', 'fashion_recommendation_v2.search.requirements_policy_v57')
def expected_kind_requirements_policy_v57(row, conditions, *, polarity=None):
    polarity = polarity or getattr(row, 'polarity', 'positive')
    if row.source in {'reference', 'stylist'}:
        return 'soft'
    if row.source != 'user' or getattr(row, 'unrestricted', False) or polarity == 'unrestricted':
        return None
    # These are narrow review concessions, not blanket color/construction relaxation.
    brands = {value for c in conditions if c.attribute == 'brand' for value in values_requirements_policy_v57(c)}
    types = {value for c in conditions if c.attribute == 'product_type' for value in values_requirements_policy_v57(c)}
    quote = row.source_text or ''
    explicit = any((word in quote for word in ('반드시', '절대', '필수')))
    if polarity == 'positive' and (not explicit) and (row.attribute == 'color') and (values_requirements_policy_v57(row) == ['navy']) and bool(types.intersection({'shirt', 'shirts'})) and any(('polo' in value or 'lacoste' in value for value in brands)) and any((c.attribute == 'size' and 'l' in values_requirements_policy_v57(c) for c in conditions)):
        return 'soft'
    if polarity == 'positive' and (not explicit) and (detail_key_requirements_policy_v57(row) == 'waistband') and any(('elastic' in value for value in values_requirements_policy_v57(row))) and ('skirt' in types) and any((detail_key_requirements_policy_v57(c) in LENGTH_KEYS_requirements_policy_v57 and 'long' in values_requirements_policy_v57(c) for c in conditions)) and any((c.attribute == 'color' and 'black' in values_requirements_policy_v57(c) for c in conditions)):
        return 'soft'
    if detail_key_requirements_policy_v57(row) in LENGTH_KEYS_requirements_policy_v57 and (not any((word in quote.casefold() for word in ('가능하면', '선택사항', '필수는 아니', 'optional')))):
        return 'hard'
    return None

@_preserve_function('validate_resolved', 'fashion_recommendation_v2.search.requirements_policy_v57')
def validate_resolved_requirements_policy_v57(result):
    routing = result.condition_routing_v37
    policy = routing.stylist_policy_v47 if routing else None
    if policy is None or set(policy.polarities) != {r.requirement_id for r in result.requirements}:
        raise ValueError('Missing v57 polarity provenance.')
    for row in result.requirements:
        expected = scope_for_requirements_policy_v57(row, row.kind, policy.polarities[row.requirement_id], result.requirements)
        if expected and row.evaluation_scope != expected:
            raise ValueError(f'{row.requirement_id}: v57 requires {expected} scope.')
        kind = expected_kind_requirements_policy_v57(row, result.requirements, polarity=policy.polarities[row.requirement_id])
        if kind and row.kind != kind:
            raise ValueError(f'{row.requirement_id}: v57 requires {kind} kind.')


# ---- requirements_policy_v58 ----

"""v58 removes user-specific kind overrides; preserves v57 scope enforcement."""
scope_for_requirements_policy_v58 = scope_for_requirements_policy_v57

@_preserve_function('expected_kind', 'fashion_recommendation_v2.search.requirements_policy_v58')
def expected_kind_requirements_policy_v58(row, conditions, *, polarity=None):
    # Other shared constraints (price, audience, unrestricted, exclusions) remain
    # User color, construction and length kind is decided by classification.
    # enforced by the existing binding/schema validators.
    return 'soft' if row.source in {'reference', 'stylist'} else None

@_preserve_function('validate_resolved', 'fashion_recommendation_v2.search.requirements_policy_v58')
def validate_resolved_requirements_policy_v58(result):
    routing = result.condition_routing_v37
    policy = routing.stylist_policy_v47 if routing else None
    if policy is None or set(policy.polarities) != {r.requirement_id for r in result.requirements}:
        raise ValueError('Missing v58 polarity provenance.')
    for row in result.requirements:
        expected = scope_for_requirements_policy_v58(row, row.kind, policy.polarities[row.requirement_id], result.requirements)
        if expected and row.evaluation_scope != expected:
            raise ValueError(f'{row.requirement_id}: v58 requires {expected} scope.')
        kind = expected_kind_requirements_policy_v58(row, result.requirements, polarity=policy.polarities[row.requirement_id])
        if kind and row.kind != kind:
            raise ValueError(f'{row.requirement_id}: v58 requires {kind} kind.')
