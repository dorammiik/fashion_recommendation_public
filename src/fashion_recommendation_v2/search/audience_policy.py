"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- audience_policy ----

"""Code authority for product-audience defaults and precedence (no LLM dependencies)."""
from types import MappingProxyType
import re
DEFAULTS = MappingProxyType({'skirt': 'women', 'dress': 'women', 'high_heels': 'women', 'tuxedo': 'men'})
PRODUCT_WORDS = MappingProxyType({'skirt': r'스커트|치마|\bskirts?\b', 'dress': r'원피스|드레스|\bdress(?:es)?\b', 'high_heels': r'하이힐|\bhigh[ -]heels?\b|\bstilettos?\b', 'tuxedo': r'턱시도|\btuxedos?\b'})
PRECEDENCE = ('explicit_request', 'anchor', 'product_default', 'none')

@_preserve_function('policy_definition', 'fashion_recommendation_v2.search.audience_policy')
def policy_definition(*, version=None):
    result = dict(product_defaults=dict(DEFAULTS), precedence=list(PRECEDENCE), explicit_unrestricted_overrides=True, requires_explicit_gender_word_for_default=False, applies_to='positively requested target or paired garment; same wearer', excludes='style adjectives, appearance, negated/unrelated products, unresolved conflicting defaults')
    if version in {'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
        result['category_anchor_default'] = 'After explicit user audience and actual anchor metadata, combine target defaults with confirmed relation_intent.anchor_category; conflicting defaults fail. Preserve category and input provenance.'
    return result

@_preserve_function('dress_skirt_diversity_exempt', 'fashion_recommendation_v2.search.audience_policy')
def dress_skirt_diversity_exempt(product_types):
    """v26 ordinary exemption, derived from positive canonical target types only.

    Head garments qualify, not a dress-shoe/accessory mentioning a garment.
    This never creates a gender constraint or changes explicit-audience priority.
    """
    return bool(product_types) and all((re.search(r'(?:^| )(?:dress(?:es)?|skirt(?:s)?(?: set(?:s)?)?)$', value.casefold().replace('_', ' ').replace('-', ' ').strip()) for value in product_types))

@_preserve_function('resolve_audience_target', 'fashion_recommendation_v2.search.audience_policy')
def resolve_audience_target(context, requirements, interpretation):
    """Interpretation is model-owned; values and ordering are code-owned."""
    explicit = [r for r in requirements.requirements if r.source == 'user' and r.attribute == 'gender']
    reference_gender = set(context.reference.gender) if context.reference else set()
    known_anchor = next(iter(reference_gender)) if reference_gender in ({'women'}, {'men'}) else None
    available = {'explicit_request': bool(explicit), 'anchor': bool(known_anchor), 'product_default': interpretation.basis == 'product_default', 'none': True}
    selected = next((basis for basis in PRECEDENCE if available[basis]))
    if interpretation.basis != selected:
        if selected == 'explicit_request':
            raise ValueError('Explicit requested audience, including unrestricted/unisex, overrides every default.')
        if interpretation.basis == 'explicit_request':
            raise ValueError('An explicit audience decision requires its preserved user gender requirement.')
        if selected == 'anchor':
            raise ValueError('The known anchor product audience takes precedence over product defaults.')
        raise ValueError('Anchor audience requires one known women/men product label in supplied metadata.')
    if selected == 'explicit_request':
        if any((r.source_text not in context.user_query for r in explicit)):
            raise ValueError('Explicit audience must quote the original request, not inherited product facts.')
        return None
    if selected == 'anchor':
        return known_anchor
    if selected == 'product_default':
        anchor_products = category_default_keys(getattr(context, 'anchor_category', None))
        if interpretation.product_type not in anchor_products and (not re.search(PRODUCT_WORDS[interpretation.product_type], interpretation.source_text, re.I)):
            raise ValueError('Default product needs matching exact request evidence; no style or appearance inference.')
        return DEFAULTS[interpretation.product_type]
    return None

@_preserve_function('_metadata_audience_context_v30', 'fashion_recommendation_v2.search.audience_policy')
def _metadata_audience_context_v30(source):
    """Separate execution context from fixed inputs, using actual anchor facts.

    A similarity reference can supply metadata even when an older saved input
    omitted audience_context_v1.reference. No prose/default is used as metadata.
    """
    context = source.audience_context_v1
    reference = source.similarity_reference
    if context is None or context.reference is not None or reference is None:
        return context
    values = {v for key in ('gender', 'detail.gender') for v in reference.attributes.get(key, [])}
    if values not in ({'women'}, {'men'}):
        return context
    data = context.model_dump(mode='json')
    data['reference'] = dict(item_id=reference.item_id, title=next(iter(reference.attributes.get('title', [])), reference.item_id), gender=sorted(values))
    return type(context).model_validate(data)

@_preserve_function('category_default_keys', 'fashion_recommendation_v2.search.audience_policy')
def category_default_keys(category):
    if not category:
        return []
    value = category.casefold().replace('_', ' ').replace('-', ' ').strip()
    endings = {'skirt': r'(?:스커트|치마|\bskirts?)$', 'dress': r'(?:원피스|드레스|\bdress(?:es)?)$', 'high_heels': r'(?:하이힐|\bhigh heels?|\bstilettos?)$', 'tuxedo': r'(?:턱시도|\btuxedos?)$'}
    return [key for key, pattern in endings.items() if re.search(pattern, value)]

@_preserve_function('audience_context_v30', 'fashion_recommendation_v2.search.audience_policy')
def audience_context_v30(source):
    context = _metadata_audience_context_v30(source)
    intent = getattr(source, 'relation_intent', None)
    if context is not None and getattr(source, 'requirements_source_version', None) in {'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v59', 'v60', 'v61'} and (intent is not None) and intent.anchor_category and (not intent.anchor_item_id):
        return source.category_anchor_context(context)
    return context

@_preserve_function('derive_audience_v30', 'fashion_recommendation_v2.search.audience_policy')
def derive_audience_v30(source, conditions):
    """Choose available evidence in policy order; never trust a proposed basis.

    Conditions have already passed role/polarity/source validation. Only a head
    garment can activate a default; dress shoes and tuxedo-print tops cannot.
    """
    context = audience_context_v30(source)
    if context is None:
        raise ValueError('v30 requires the prepared audience context.')

    def decision(basis, quote, reason, product=None):
        return dict(basis=basis, product_type=product, source_text=quote, reason=reason)
    explicit = [c for c in conditions if c.source == 'user' and c.role == 'target' and (c.attribute == 'gender')]
    if explicit:
        choices = []
        for c in explicit:
            if c.polarity == 'negative':
                raise ValueError('Cannot derive an explicit audience from a negative gender condition.')
            vals = c.value if isinstance(c.value, list) else [c.value]
            choices.append(set(vals))
        if len(choices) > 1 and (not set.intersection(*choices)):
            raise ValueError('Conflicting explicit audience conditions require clarification.')
        return decision('explicit_request', explicit[0].source_text, 'Code policy: explicit requested audience overrides anchor and defaults.')
    supplied_gender = {v for key in ('gender', 'detail.gender') for v in (source.similarity_reference.attributes.get(key, []) if source.similarity_reference else []) if v in {'women', 'men'}}
    gender = set(context.reference.gender) if context.reference else set()
    if len(supplied_gender) > 1 or gender == {'women', 'men'} or (gender in ({'women'}, {'men'}) and supplied_gender and (gender != supplied_gender)):
        raise ValueError('Conflicting actual anchor audience metadata requires clarification.')
    if gender in ({'women'}, {'men'}):
        return decision('anchor', context.user_query, 'Code policy: audience_context_v1.reference.gender identifies the paired product audience.')
    matches = []
    for c in conditions:
        if c.source != 'user' or c.attribute != 'product_type' or c.polarity != 'positive':
            continue
        values = c.value if isinstance(c.value, list) else [c.value]
        products = []
        for value in values:
            value = value.casefold().replace('_', ' ').replace('-', ' ').strip()
            for product, suffix in {'skirt': r'skirts?(?: sets?)?', 'dress': r'dress(?:es)?', 'high_heels': r'high heels?', 'tuxedo': r'tuxedos?'}.items():
                if re.search(r'(?:^| )' + suffix + r'$', value):
                    products.append(product)
                    break
        # This must be identical for one OR row and split allowed-alternative
        # Unknown defaults do not erase an explicitly named dress/skirt context.
        # rows. Opposing known defaults still fail below instead of guessing.
        for product in products:
            evidence = re.search(PRODUCT_WORDS[product], context.user_query, re.I)
            if evidence and re.search(PRODUCT_WORDS[product], c.source_text, re.I):
                matches.append((product, evidence.group()))
    anchor_products = category_default_keys(getattr(context, 'anchor_category', None))
    for product in anchor_products:
        # The quote remains actual user text. The decision context separately
        # preserves the confirmed category and its exact upstream source path.
        matches.append((product, context.user_query))
    if len({DEFAULTS[p] for p, _ in matches}) > 1:
        raise ValueError('Conflicting positive garment defaults require clarification.')
    if matches:
        product, quote = matches[0]
        return decision('product_default', quote, 'Code policy: default includes relation_intent.anchor_category=' + repr(context.anchor_category) if anchor_products else 'Code policy: positively requested target/paired garment default; no explicit override.', product)
    return decision('none', context.user_query, 'Code policy: no supported audience restriction.')
GENDER_ALIASES = {'men': 'men', "men's": 'men', 'mens': 'men', 'women': 'women', "women's": 'women', 'womens': 'women', 'unisex': 'unisex', 'unisex adults': 'unisex', 'unisex adult': 'unisex'}

@_preserve_function('canonical_gender', 'fashion_recommendation_v2.search.audience_policy')
def canonical_gender(value):
    # Preserve list/OR types: only a scalar exact alias can be normalized.
    return GENDER_ALIASES.get(value.strip().casefold().replace('’', "'"), value) if isinstance(value, str) else value
