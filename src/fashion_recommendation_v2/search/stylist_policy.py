"""Role-consolidated implementation; service contracts and behavior are preserved."""
from __future__ import annotations
from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function

# ---- stylist_policy_v47 ----
"""Shared v47 scope and explicit-user precedence; no model or agent imports."""
from fashion_recommendation_v2.search.condition_semantics import provenance_dimension_v30 as dimension

SEARCH_ATTRIBUTES = frozenset({'product_type', 'gender', 'color', 'sleeve_length', 'brand', 'occasion', 'theme'})

SEARCH_ATTRIBUTES_V50 = SEARCH_ATTRIBUTES | {'pattern', 'fit'}

SEMANTICS = """
For positive, restricted target conditions, assign search scope to hard conditions
in APPLICATION_RULES.hard_search_attributes. Other hard conditions remain item.
For positive, restricted soft conditions from user or stylist, the dimensions in
APPLICATION_RULES.soft_search_attributes also require search scope. Other soft
conditions retain the existing model scope decision. Category is the product_type
dimension for this policy, never permission to rename a preserved Stylist field.
Negatives, exclusions and unrestricted conditions stay item. Kind and scope are
independent: a searchable Stylist proposal stays soft and cannot reject a candidate
for non-fulfilment. Both scopes still receive per-product judgments.

For each same-dimension Stylist / hard-user pair, classify the actual value/range
relationship in stylist_user_comparisons. Refinement means EVERY proposed OR option
is within the user's allowed range (top -> shirts OR T-shirts). Compatible means
the proposals can coexist without violating the mandatory condition. Conflict
means the proposal would contradict that mandatory range (black only -> ivory).
Consider negation, ranges and all OR options, not only attribute names. Never
declare conflict merely because two rows share a dimension. Preserve refinements
and compatible proposals as soft. Only actual conflicts give user precedence.
For mixed OR proposals containing conflicting options, report conflict for the
whole original proposal: never silently trim, split or rewrite its original list.
Comparisons cover exactly all such pairs; no invented IDs, missing pairs or duplicates.
Keep category/product_type soft when it is a preserved Stylist refinement; the
user's mandatory garment boundary stays hard; optional user types remain soft. Do not replace the user's broad boundary
with one preferred subtype. All originals and reasons remain reviewable.
"""


@_preserve_function('pair_key', 'fashion_recommendation_v2.search.stylist_policy_v47')
def pair_key(comparison):
    return comparison.stylist_requirement_id, comparison.user_requirement_id


@_preserve_function('expected_pairs', 'fashion_recommendation_v2.search.stylist_policy_v47')
def expected_pairs(stylist, users):
    return {(s.requirement_id, u.requirement_id) for s in stylist for u in users
            if dimension(s.attribute, s.value) == dimension(u.attribute, u.value)}


@_preserve_function('validate_comparisons', 'fashion_recommendation_v2.search.stylist_policy_v47')
def validate_comparisons(comparisons, pairs):
    keys = [pair_key(c) for c in comparisons]
    if set(keys) != pairs or len(keys) != len(pairs):
        raise ValueError('Stylist comparisons must cover exactly the same-dimension hard-user pairs.')
    return {pair_key(c) for c in comparisons if c.relationship == 'conflict'}


@_preserve_function('source_stylist_conditions', 'fashion_recommendation_v2.search.stylist_policy_v47')
def source_stylist_conditions(source):
    """Rebuild only the code-attached inventory from resolved originals, not prose."""
    from types import SimpleNamespace
    unique = []
    for entry in source.stylist_resolution.interpretations if source.stylist_resolution else []:
        data = {key: getattr(entry, key) for key in ('attribute', 'value', 'source_text')}
        from fashion_recommendation_v2.stylist_personalization import condition_provenance
        provenance = condition_provenance(source.stylist_resolution, entry)
        if provenance is not None:
            data['stylist_provenance'] = provenance
        if data not in unique:
            unique.append(data)
    return [SimpleNamespace(requirement_id=f'stylist_{i:03d}', source='stylist',
            role='target', polarity='positive', **data) for i, data in enumerate(unique, 1)]


@_preserve_function('validate_resolved_stylist', 'fashion_recommendation_v2.search.stylist_policy_v47')
def validate_resolved_stylist(source, result):
    originals = source_stylist_conditions(source)
    users = [r for r in result.requirements if r.source == 'user' and r.kind == 'hard']
    policy = result.condition_routing_v37.stylist_policy_v47 if result.condition_routing_v37 else None
    records = policy.comparisons if policy else None
    if records is None:
        raise ValueError('Missing v47 Stylist precedence decisions.')
    conflicts = validate_comparisons(records, expected_pairs(originals, users))
    suppressed = {sid for sid, _ in conflicts}
    expected = {r.requirement_id: r for r in originals if r.requirement_id not in suppressed}
    actual = [r for r in result.requirements if r.source == 'stylist']
    if {r.requirement_id for r in actual} != set(expected) or len(actual) != len(expected):
        raise ValueError('Each nonconflicting resolved Stylist original must remain exactly once.')
    for row in actual:
        original = expected[row.requirement_id]
        provenance = row.stylist_provenance.model_dump(mode='json') if row.stylist_provenance else None
        if provenance != getattr(original, 'stylist_provenance', None):
            raise ValueError('Stylist preference provenance must be preserved exactly.')
        if row.kind != 'soft' or any(getattr(row, f) != getattr(original, f)
                                    for f in ('attribute', 'value', 'source_text')):
            raise ValueError('Stylist attribute/value/OR/source_text and soft kind are immutable.')


@_preserve_function('validate_scopes', 'fashion_recommendation_v2.search.stylist_policy_v47')
def validate_scopes(result, *, search_attributes=SEARCH_ATTRIBUTES):
    policy = result.condition_routing_v37.stylist_policy_v47 if result.condition_routing_v37 else None
    polarities = policy.polarities if policy else None
    if polarities is None or set(polarities) != {r.requirement_id for r in result.requirements}:
        raise ValueError('Missing v47 condition polarity provenance.')
    for row in result.requirements:
        polarity = polarities[row.requirement_id]
        expected = None
        if polarity in {'negative', 'unrestricted'} or row.unrestricted or row.attribute == 'avoid_product_type':
            expected = 'item'
        elif row.kind == 'hard':
            expected = 'search' if dimension(row.attribute, row.value) in search_attributes else 'item'
        elif row.source in {'user', 'stylist'} and dimension(row.attribute, row.value) in search_attributes:
            expected = 'search'
        if expected and row.evaluation_scope != expected:
            raise ValueError(f'{row.requirement_id}: v47 requires {expected} scope.')
