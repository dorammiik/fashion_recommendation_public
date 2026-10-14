"""Role-consolidated implementation; service contracts and behavior are preserved."""
from __future__ import annotations
from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function

# ---- requirement_sources ----
"""v25 field-source authority shared by prompt guidance and code validation."""
from dataclasses import dataclass
from dataclasses import asdict
from copy import deepcopy
import json
import re
from fashion_recommendation_v2.search.semantic_validation import semantic_failure
from fashion_recommendation_v2.search.semantic_validation import semantic_only


@_preserve_class('FieldSource', 'fashion_recommendation_v2.search.requirement_sources')
@dataclass(frozen=True)
class FieldSource:
    __qualname__ = 'FieldSource'
    field: str
    paths: tuple[str, ...]
    operation: str = 'exact_contiguous_quote_in_all'


@_preserve_function('source_rules', 'fashion_recommendation_v2.search.requirement_sources')
def source_rules(source):
    user_paths = ('user_query', 'similarity_reference.user_query') if source.similarity_reference else ('user_query',)
    if (getattr(source, 'search_query_composition', None) is not None
            and getattr(source, 'requirements_source_version', None) not in {'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}):
        from fashion_recommendation_v2.query_composition import COMPOSED_USER_SOURCE_PATHS
        user_paths = COMPOSED_USER_SOURCE_PATHS
    return {
        'relation': FieldSource('relation_conditions[].source_text', ('user_query',),
            'exact_contiguous_quote; preserve confirmed relation_intent including original source_text and anchor'),
        'user': FieldSource('requirements[source=user].source_text', user_paths),
        'user_gender': FieldSource('requirements[source=user,attribute=gender].source_text',
                                  tuple(dict.fromkeys((*user_paths, 'original_user_query')))),
        'diversity': FieldSource('gender_diversity_policy.source_texts (model)', ('user_query',)),
        'audience': FieldSource('audience_interpretation.source_text', ('audience_context_v1.user_query',)),
        'context': FieldSource('requirements[source=context].source_text', ('audience_context_v1.user_query',)),
        'context_diversity': FieldSource('gender_diversity_policy.source_texts (contextual_audience)', ('audience_context_v1.user_query',)),
        'stylist': FieldSource('requirements[source=stylist]', ('stylist_resolution.interpretations',),
                              ('exact_attribute_value_source_text; soft; only_actual_hard_user_conflicts_override'
                               if getattr(source, 'requirements_source_version', None) in {'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'} else
                               'exact_attribute_value_source_text; soft; explicit_same_attribute_hard_override')),
        'reference': FieldSource('requirements[source=reference].source_text', ('similarity_reference.attributes',),
                                'exact_contiguous_quote_in_any_known_attribute; soft'),
        'alternative': FieldSource('product_type_alternatives.source_text (code)', user_paths),
    }


@_preserve_function('source_documents', 'fashion_recommendation_v2.search.requirement_sources')
def source_documents(source):
    def dump(value):
        return value.model_dump(mode='json') if value is not None else None
    documents = {'user_query': source.user_query, 'original_user_query': source.original_user_query,
        'stylist_resolution': dump(source.stylist_resolution),
        'original_stylist_resolution': dump(source.original_stylist_resolution),
        'audience_context_v1': dump(source.audience_context_v1), 'similarity_reference': dump(source.similarity_reference)}
    if getattr(source, 'search_query_composition', None) is not None:
        documents['search_query_composition'] = dump(source.search_query_composition)
    from fashion_recommendation_v2.stylist_personalization import search_provenance_view
    return search_provenance_view(documents)


@_preserve_function('field_source_contract', 'fashion_recommendation_v2.search.requirement_sources')
def field_source_contract(source):
    return dict(revision='field-sources-v25', documents=source_documents(source),
        field_sources={key: asdict(rule) for key, rule in source_rules(source).items()},
        document_roles={'original_user_query': 'actual user message; provenance, not permission to restore omitted clauses',
            'user_query': 'searchable projected/expanded request; not a replacement for actual user words',
            'stylist_resolution': 'immutable supplied resolved projection',
            'original_stylist_resolution': 'immutable complete original; omitted entries are not new Search conditions'})


@_preserve_function('_at', 'fashion_recommendation_v2.search.requirement_sources')
def _at(documents, path):
    current = documents
    for key in path.split('.'):
        current = current[key]
    return current


@_preserve_function('validate_field_sources', 'fashion_recommendation_v2.search.requirement_sources')
def validate_field_sources(source, output, interpretation=None, *, observe_semantics=False):
    if getattr(source, 'requirements_source_version', None) in {'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
        from fashion_recommendation_v2.search.requirement_sources import validate_source_meaning
        validate_source_meaning(source, output.requirements, quote_rules=source_rules(source))
        routing = getattr(output, 'condition_routing_v37', None)
        if routing is not None:
            expected = source.relation_intent
            relations = routing.relation_conditions
            if len(relations) != int(expected is not None) or any(
                    row.intent != expected or not row.source_text.strip() or any(
                        row.source_text not in _at(source_documents(source), path)
                        for path in source_rules(source)['relation'].paths) for row in relations):
                raise ValueError('Relation clause must preserve confirmed intent and quote searchable user_query.')
    from fashion_recommendation_v2.query_composition import validate_composed_conditions
    validate_composed_conditions(source, output.requirements)
    rules, documents = source_rules(source), source_documents(source)
    checks = []
    def quote(key, field, value):
        for path in rules[key].paths:
            text = _at(documents, path)
            if not value.strip() or value not in text:
                message = json.dumps(dict(code='source_mismatch', field=field, rejected_value=value,
                    required_source=path, allowed_source_text=text,
                    required_change='Use one exact contiguous quote from the designated document; do not rename fields or change documents.'), ensure_ascii=False)
                if observe_semantics:
                    semantic_failure('source_meaning', message)
                else:
                    raise ValueError(message)
        checks.append(field)
    for r in output.requirements:
        field = f'requirements[{r.requirement_id}].source_text'
        if r.source == 'user':
            quote('user_gender' if r.attribute == 'gender' else 'user', field, r.source_text)
        elif r.source == 'context':
            quote('context', field, r.source_text)
        elif r.source == 'reference':
            reference = _at(documents, rules['reference'].paths[0]) if source.similarity_reference else {}
            if r.kind != 'soft':
                raise ValueError(f'{field}: must quote a supplied similarity_reference.attributes fact and remain soft.')
            if not r.source_text.strip() or not any(
                    r.source_text in fact for values in reference.values() for fact in values):
                message = f'{field}: must quote a supplied similarity_reference.attributes fact and remain soft.'
                if observe_semantics:
                    semantic_failure('source_meaning', message, requirement_id=r.requirement_id)
                else:
                    raise ValueError(message)
            checks.append(field)
        elif r.source == 'stylist':
            entries = _at(documents, rules['stylist'].paths[0]) if source.stylist_resolution else []
            value = r.model_dump(mode='json')
            if r.kind != 'soft' or not any(all(value[key] == entry[key]
                    for key in ('attribute', 'value', 'source_text')) for entry in entries):
                raise ValueError(f'{field}: immutable stylist_resolution.interpretations copy required.')
            if getattr(source.stylist_resolution, 'contract_version', None) in {'stylist-v2', 'stylist-v3', 'stylist-v4', 'stylist-v5', 'stylist-v6'}:
                from fashion_recommendation_v2.stylist_personalization import condition_provenance
                actual = r.stylist_provenance.model_dump(mode='json') if r.stylist_provenance else None
                if not any(all(value[k] == e.model_dump(mode='json')[k] for k in ('attribute', 'value', 'source_text'))
                           and actual == condition_provenance(source.stylist_resolution, e)
                           for e in source.stylist_resolution.interpretations):
                    raise ValueError('Stylist profile provenance changed during Search binding.')
            checks.append(field)
    key = 'context_diversity' if output.gender_diversity_policy.exemption == 'contextual_audience' else 'diversity'
    for i, text in enumerate(output.gender_diversity_policy.source_texts):
        quote(key, f'gender_diversity_policy.source_texts[{i}]', text)
    if interpretation is not None:
        quote('audience', 'audience_interpretation.source_text', interpretation.source_text)
    for i, alternative in enumerate(getattr(output, 'product_type_alternatives', [])):
        quote('alternative', f'product_type_alternatives[{i}].source_text', alternative.source_text)
    return checks


# Only these bilingual equivalents may recover a misplaced user quotation.
# The prompt and the repair code consume this same registry. Unknown vocabulary
# is preserved when its quote is valid, but cannot justify a source repair.
RECOVERY_TERMS_V30 = {
    'product_type': {'top': ['상의'], 'tops': ['상의'], 'shirt': ['셔츠'], 'dress': ['원피스', '드레스'],
                     'skirt': ['스커트', '치마'], 'skirt_set': ['스커트 세트'],
                     'two-piece': ['투피스'], 'two piece': ['투피스']},
    'gender': {'women': ['여성용', '여자 옷', '여성복'], 'men': ['남성용', '남자 옷', '남성복']},
    'pattern': {'floral': ['꽃무늬'], 'small floral': ['잔꽃무늬']},
    'color': {'navy': ['네이비'], 'black': ['검정', '검은색'], 'white': ['흰색']},
}

# These identify a supplied reference fact in expanded prose. In particular,
# 'maxi' is NOT an alias of 'long': only the source's long fact is carried over.
REFERENCE_QUOTE_TERMS_V30 = {
    'color': {'multicolored': ['멀티컬러']},
    'pattern': {'floral': ['꽃무늬']},
    'sleeve_length': {'sleeveless': ['민소매']},
    'dress_length': {'long': ['긴 길이', '긴 맥시 길이', '롱 길이']},
    'slit': {'double front slit': ['더블 프런트 슬릿']},
    'neckline': {'round neckline': ['라운드넥'], 'keyhole opening': ['키홀']},
    'shoulder_exposure': {'partial shoulder exposure': ['어깨 일부 노출']},
}
ALTERNATIVE_ACCEPTANCE_V30 = r'(?:도|것도)\s*(?:괜찮|좋|가능)|\b(?:also acceptable|also okay|is fine too)\b'
UNRESTRICTED_V30 = r'상관없|아무거나|무관|제한\s*없|\b(?:any|unrestricted|does not matter)\b'
NEGATIVE_V30 = r'제외|말고|빼고|싫|별로|아니|않|\b(?:no|not|without)\b'


@_preserve_function('recovery_contract_v30', 'fashion_recommendation_v2.search.requirement_sources')
def recovery_contract_v30():
    """One recovery authority for structuring instructions and executable joins."""
    return dict(user_quote_terms=deepcopy(RECOVERY_TERMS_V30),
        reference_quote_terms=deepcopy(REFERENCE_QUOTE_TERMS_V30),
        allowed_alternative_pattern=ALTERNATIVE_ACCEPTANCE_V30,
        unrestricted_pattern=UNRESTRICTED_V30, negative_pattern=NEGATIVE_V30,
        stylist='Only resolved originals; matching dimension, complete values and overlapping exact source clauses. Never merge a different explicit condition.',
        reference='Match the attribute AND each value to supplied facts. Expanded-only user prose is inherited; retain authoritative facts, not extra inferred precision.',
        duplicates='Validate IDs before merging; preserve raw responses and log retained IDs/source paths.',
        otherwise='Stop on unknown/contradictory evidence; never fabricate a quote or restore omitted clauses.')


@_preserve_function('condition_values_v30', 'fashion_recommendation_v2.search.requirement_sources')
def condition_values_v30(condition):
    value = condition.value
    return list(value.values) if hasattr(value, 'key') else list(value) if isinstance(value, list) else [value]


@_preserve_function('_contains_term', 'fashion_recommendation_v2.search.requirement_sources')
def _contains_term(text, term):
    pattern = re.escape(term)
    if term.isascii():
        pattern = r'(?<!\w)' + pattern + r'(?!\w)'
    return bool(re.search(pattern, text, re.I))


@_preserve_function('user_quote_supported_v30', 'fashion_recommendation_v2.search.requirement_sources')
def user_quote_supported_v30(source, condition):
    key = 'user_gender' if condition.attribute == 'gender' else 'user'
    docs = source_documents(source)
    return bool(condition.source_text.strip()) and all(
        condition.source_text in _at(docs, path) for path in source_rules(source)[key].paths)


@_preserve_function('resolved_stylist_duplicate_v30', 'fashion_recommendation_v2.search.requirement_sources')
def resolved_stylist_duplicate_v30(source, condition):
    from fashion_recommendation_v2.search.condition_semantics import provenance_dimension_v30
    if condition.source != 'user' or condition.role != 'target' or condition.polarity != 'positive':
        return None
    if not source.stylist_resolution or not user_quote_supported_v30(source, condition):
        return None
    matches = []
    for entry in source.stylist_resolution.interpretations:
        if (provenance_dimension_v30(condition.attribute, condition.value) == provenance_dimension_v30(entry.attribute, entry.value)
                and condition_values_v30(condition) == condition_values_v30(entry)
                and entry.source_text is not None and entry.source_text in source.user_query
                and (entry.source_text in condition.source_text or condition.source_text in entry.source_text)):
            matches.append(entry)
    # Duplicate identical originals are handled by the existing code attachment.
    unique = {json.dumps(e.model_dump(mode='json', include={'attribute','value','source_text'}), sort_keys=True): e for e in matches}
    return next(iter(unique.values())) if len(unique) == 1 else None


@_preserve_function('reference_facts_v30', 'fashion_recommendation_v2.search.requirement_sources')
def reference_facts_v30(source, condition):
    """Return same-dimension known facts, keeping their exact paths and values."""
    from types import SimpleNamespace
    from fashion_recommendation_v2.search.condition_semantics import provenance_dimension_v30
    dimension = provenance_dimension_v30(condition.attribute, condition.value)
    result = []
    for key, values in (source.similarity_reference.attributes.items() if source.similarity_reference else []):
        for index, value in enumerate(values):
            if key.startswith('detail.'):
                attr, shaped = 'detail', SimpleNamespace(key=key[7:], values=[value])
            else:
                attr, shaped = key, value
            if value.casefold() not in {'unknown', 'unobserved', 'not visible', ''} and provenance_dimension_v30(attr, shaped) == dimension:
                result.append(dict(value=value, path=f'similarity_reference.attributes.{key}[{index}]'))
    return result


@_preserve_function('validate_reference_binding_v30', 'fashion_recommendation_v2.search.requirement_sources')
def validate_reference_binding_v30(source, condition):
    facts = reference_facts_v30(source, condition)
    values = condition_values_v30(condition)
    if (not values or any(v not in [f['value'] for f in facts] for v in values)
            or not condition.source_text.strip()
            or not any(condition.source_text in f['value'] for f in facts if f['value'] in values)):
        semantic_failure('source_meaning', f'{condition.requirement_id}: reference attribute/value/source is not supported by the same supplied facts.',
                         condition=condition.model_dump(mode='json'))
    return [f for f in facts if f['value'] in values]


@_preserve_function('reference_quote_projection_v30', 'fashion_recommendation_v2.search.requirement_sources')
def reference_quote_projection_v30(source, condition):
    """Repair a misplaced quote only when all values have same-dimension facts."""
    facts = reference_facts_v30(source, condition)
    values = condition_values_v30(condition)
    if not values or any(v not in [f['value'] for f in facts] for v in values):
        return condition, []  # The strict binding check supplies the error.
    selected = [f for f in facts if f['value'] in values]
    if any(condition.source_text in f['value'] for f in selected):
        return condition, []
    documents = source_documents(source)
    supplied = [documents['user_query'], documents['original_user_query'],
        (documents.get('audience_context_v1') or {}).get('user_query'),
        (documents.get('similarity_reference') or {}).get('user_query')]
    supplied.extend(value for values in (source.similarity_reference.attributes.values() if source.similarity_reference else []) for value in values)
    if not any(condition.source_text in text for text in supplied if isinstance(text, str)):
        return condition, []
    return condition.model_copy(update={'source_text': selected[0]['value']}), [f['path'] for f in selected]


@_preserve_function('projected_reference_binding_v30', 'fashion_recommendation_v2.search.requirement_sources')
def projected_reference_binding_v30(source, condition):
    """Bind inherited expansion to original facts; never manufacture user intent."""
    from fashion_recommendation_v2.search.condition_semantics import provenance_dimension_v30
    if (condition.source != 'user' or not source.similarity_reference
            or condition.role != 'target' or condition.polarity != 'positive'
            or user_quote_supported_v30(source, condition)
            or condition.source_text in source.original_user_query
            or condition.attribute in {'product_type', 'avoid_product_type', 'price'}):
        return []
    dimension = provenance_dimension_v30(condition.attribute, condition.value)
    terms = REFERENCE_QUOTE_TERMS_V30.get(dimension, {})
    supplied = reference_facts_v30(source, condition)
    values = condition_values_v30(condition)
    if condition.source_text not in source.user_query:
        # The quote itself may be a literal reference fact with the wrong
        # source label. Verify its dimension and the ENTIRE OR value set.
        if (all(v in [f['value'] for f in supplied] for v in values)
                and any(condition.source_text in f['value'] for f in supplied if f['value'] in values)):
            return [f for f in supplied if f['value'] in values]
        return []
    facts = [f for f in supplied if any(
        _contains_term(condition.source_text, t) for t in [f['value'], *terms.get(f['value'], [])])]
    if re.search(NEGATIVE_V30, condition.source_text, re.I):
        return []
    # When the model split a compound quotation, prefer the fully supported
    # values of that condition. Otherwise retain only facts actually evidenced
    # by this expanded clause (e.g. long, never invented maxi).
    if values and all(v in [f['value'] for f in facts] for v in values):
        facts = [f for f in facts if f['value'] in values]
    return facts


@_preserve_function('accepted_product_alternative_v30', 'fashion_recommendation_v2.search.requirement_sources')
def accepted_product_alternative_v30(source, condition):
    if (condition.attribute != 'product_type' or condition.source != 'user'
            or condition.role != 'target' or condition.polarity != 'unrestricted'
            or not user_quote_supported_v30(source, condition)):
        return False
    quote = condition.source_text
    if (not re.search(ALTERNATIVE_ACCEPTANCE_V30, quote, re.I)
            or re.search(UNRESTRICTED_V30, quote, re.I) or re.search(NEGATIVE_V30, quote, re.I)):
        return False
    return all(isinstance(v, str) and any(_contains_term(quote, term) for term in
        [v, *RECOVERY_TERMS_V30['product_type'].get(v, [])]) for v in condition_values_v30(condition))


@_preserve_function('product_alternative_span_v30', 'fashion_recommendation_v2.search.requirement_sources')
def product_alternative_span_v30(source, conditions):
    """One exact source span for explicitly allowed target alternatives only."""
    if len(conditions) < 2:
        return None
    query = source.user_query
    positions = []
    for c in conditions:
        # Repeated clauses need explicit disambiguation, never index guessing.
        if not user_quote_supported_v30(source, c) or query.count(c.source_text) != 1:
            return None
        start = query.index(c.source_text)
        positions.append((start, start + len(c.source_text)))
    ordered = sorted(zip(positions, conditions), key=lambda entry: entry[0])
    if not all(accepted_product_alternative_v30(source, c.model_copy(update={'polarity': 'unrestricted'}))
               for _, c in ordered[1:]):
        return None
    span = query[min(p[0] for p in positions):max(p[1] for p in positions)]
    candidate = conditions[0].model_copy(update={'source_text': span})
    return span if user_quote_supported_v30(source, candidate) else None


@_preserve_function('recover_condition_quote_v30', 'fashion_recommendation_v2.search.requirement_sources')
@semantic_only('source_meaning', fallback=lambda source, condition: (condition.source_text, []))
def recover_condition_quote_v30(source, condition):
    """A verified projection only: no invented excerpts or resurrected clauses."""
    rules, documents = source_rules(source), source_documents(source)
    if condition.source == 'reference':
        # Keep the historical reference rule. No cross-attribute guessing.
        facts = source.similarity_reference.attributes if source.similarity_reference else {}
        if any(condition.source_text in fact for values in facts.values() for fact in values):
            return condition.source_text, list(rules['reference'].paths)
        raise ValueError(f'{condition.requirement_id}: cannot recover reference source evidence.')
    key = 'user_gender' if condition.attribute == 'gender' else 'user'
    paths = rules[key].paths
    texts = [_at(documents, path) for path in paths]
    if all(condition.source_text in text for text in texts):
        return condition.source_text, list(paths)
    # Recovery must originate in another supplied source document, not hallucinated text.
    supplied = [documents.get('user_query'), documents.get('original_user_query'),
                (documents.get('audience_context_v1') or {}).get('user_query'),
                (documents.get('similarity_reference') or {}).get('user_query')]
    if condition.polarity != 'positive' or not any(
            condition.source_text in text for text in supplied if isinstance(text, str)):
        raise ValueError(f'{condition.requirement_id}: source evidence cannot be recovered without guessing.')
    values = condition.value if isinstance(condition.value, list) else [condition.value]
    if len(values) != 1 or not isinstance(values[0], str):
        raise ValueError(f'{condition.requirement_id}: OR/structured source repair requires original evidence.')
    value = values[0]
    terms = [value, *RECOVERY_TERMS_V30.get(condition.attribute, {}).get(value, [])]
    candidates = set()
    for term in terms:
        pattern = re.escape(term)
        if term.isascii():
            pattern = r'(?<!\w)' + pattern + r'(?!\w)'
        for match in re.finditer(pattern, texts[0], re.I):
            quote = match.group()
            vicinity = texts[0][max(0, match.start()-10):match.end()+12]
            if re.search(r'제외|말고|빼고|싫|별로|아니|않|\b(?:no|not|without)\b', vicinity, re.I):
                continue  # A bare keyword cannot prove positive intent here.
            if all(quote in text for text in texts):
                candidates.add(quote)
    if len(candidates) != 1:
        raise ValueError(f'{condition.requirement_id}: no unique supported source repair.')
    return candidates.pop(), list(paths)


# ---- requirement_sources_v46 ----
"""v46 source meaning, separate from the shared exact-quotation rules."""

SOURCE_DEFINITIONS = {
    'user': dict(meaning='A condition explicitly requested by the actual user.',
                 paths=['original_user_query']),
    'reference': dict(meaning='Known facts inherited from the similarity reference product.',
                      paths=['similarity_reference.attributes']),
    'stylist': dict(meaning='Resolved target proposals supplied by Stylist; code attaches originals once.',
                    paths=['stylist_resolution.interpretations']),
}


@_preserve_function('compatibility', 'fashion_recommendation_v2.search.requirement_sources_v46')
def compatibility(source):
    return bool(source.relation_intent and source.relation_intent.relation_type == 'compatibility')


@_preserve_function('validate_source_meaning', 'fashion_recommendation_v2.search.requirement_sources_v46')
def validate_source_meaning(source, conditions, *, quote_rules):
    """Do not repair responses or let expanded wording manufacture user provenance."""
    for condition in conditions:
        if compatibility(source) and getattr(condition, 'role', 'target') != 'target':
            raise ValueError(f'{condition.requirement_id}: compatibility anchor facts are context, not product conditions.')
        if condition.source == 'user':
            # Quotation membership in user_query is checked independently. This
            # check establishes actual-user provenance, including uncomposed eval inputs.
            if not condition.source_text.strip() or any(
                    condition.source_text not in getattr(source, path)
                    for path in SOURCE_DEFINITIONS['user']['paths']):
                raise ValueError(f'{condition.requirement_id}: expanded prose is not an actual user condition.')
            rule = quote_rules['user_gender' if condition.attribute == 'gender' else 'user']
            for path in rule.paths:
                document = source
                for key in path.split('.'):
                    document = getattr(document, key)
                if condition.source_text not in document:
                    raise ValueError(f'{condition.requirement_id}: user quotation is absent from {path}; '
                                     'never restore omitted original-only conditions.')
        elif condition.source == 'reference' and (compatibility(source) or not source.similarity_reference):
            raise ValueError(f'{condition.requirement_id}: reference conditions require similarity product facts.')
