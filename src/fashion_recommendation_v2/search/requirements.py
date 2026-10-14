"""Role-consolidated implementation; service contracts and behavior are preserved."""
from __future__ import annotations
from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function

# ---- requirements_v26 ----
"""Code-owned assembly and validation for the v26 two-stage requirement contract."""
from copy import deepcopy as deepcopy_v26
import json
from uuid import uuid4

from fashion_recommendation_v2.schemas.search.requirements.search_requirements import StylistConditionV26
from fashion_recommendation_v2.schemas.search.requirements.search_requirements import GenderDiversityPolicy_legacy as GenderDiversityPolicy
from fashion_recommendation_v2.schemas.search.requirements.search_requirements import RequirementsExtractionV8_legacy as RequirementsExtractionV8
from fashion_recommendation_v2.schemas.search.requirements.search_requirements import ProductTypeAlternative
from fashion_recommendation_v2.schemas.search.requirements.search_requirements_context import AudienceInterpretationV1 as AudienceInterpretationV1_v26
from fashion_recommendation_v2.schemas.search.requirements.search_requirements_context import CONTEXT_REQUIREMENT_ID
from fashion_recommendation_v2.schemas.search.requirements.search_requirements_context import decide_audience
from fashion_recommendation_v2.schemas.search.requirements.search_requirements import apply_audience_decision_v24 as apply_audience_decision
from fashion_recommendation_v2.search.requirement_sources import source_documents
from fashion_recommendation_v2.search.requirement_sources import source_rules as source_rules_v26
from fashion_recommendation_v2.search.requirement_sources import _at
from fashion_recommendation_v2.search.planning_rules import core_attributes as core_attributes_v26
from fashion_recommendation_v2.search.audience_policy import dress_skirt_diversity_exempt


@_preserve_function('source_contract', 'fashion_recommendation_v2.search.requirements_v26')
def source_contract_v26(source):
    """Reuse the authority for existing input paths; expose only model-owned v26 fields."""
    rules = source_rules_v26(source)
    return dict(revision='field-sources-v26', documents=source_documents(source), fields={
        'conditions[source=user].source_text': list(rules['user'].paths),
        'conditions[source=user,attribute=gender].source_text': list(rules['user_gender'].paths),
        'conditions[source=reference].source_text': list(rules['reference'].paths),
        'relation_conditions[].source_text': list(rules['relation'].paths),
        'audience_interpretation.source_text': list(rules['audience'].paths),
        'code_attached_stylist': list(rules['stylist'].paths)},
        operations={'user_and_audience': 'exact_contiguous_quote_in_all_listed_documents',
                    'reference': 'exact_contiguous_quote_in_any_known_attribute_value',
                    'stylist': 'code copies attribute/value/source_text and OR types exactly; '
                        'Stylist v2 preference-only entries preserve null source_text and their frozen interpretation/evidence provenance; '
                        'never fabricate a user quote; optional search_text renders those same soft target alternatives; '
                        'never extract additional user/anchor conditions from it',
                    'relation': rules['relation'].operation,
                    'composition': 'effective_query combines source segments; only retained actual user words '
                        'can be source=user. Anchor observations stay contextual, not target conditions. '
                        'Code attaches structured Stylist conditions as target/soft; do not extract sentence copies.'},
        provenance_only=['original_user_query', 'original_stylist_resolution'],
        diversity='No model-authored diversity evidence. Code derives it from preserved conditions/context.')


@_preserve_function('structure_and_sources', 'fashion_recommendation_v2.search.requirements_v26')
def structure_and_sources_v26(source, structure, *, observe_semantics=False, observe_reference_roles=False):
    """Validate all independently checkable conditions together; never repair text."""
    from fashion_recommendation_v2.query_composition import validate_composed_conditions
    validate_composed_conditions(source, structure.conditions)
    contract = source_contract_v26(source)
    documents, fields = contract['documents'], contract['fields']
    errors = []
    source_errors = []
    reference_forbidden = {'price'} if getattr(source, 'requirements_source_version', None) in {'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'} else {'price', 'product_type'}
    def check_quote(field, quote, paths):
        for path in paths:
            value = _at(documents, path)
            if not quote.strip() or quote not in value:
                error = dict(field=field, code='source_mismatch', value=quote, required_source=path)
                errors.append(error)
                source_errors.append(error)
    conditions = [c.model_copy(deep=True) for c in structure.conditions]
    ids = [c.requirement_id for c in conditions]
    if len(ids) != len(set(ids)):
        errors.append(dict(field='conditions', code='duplicate_condition_id'))
    for c in conditions:
        prefix = f'conditions[{c.requirement_id}]'
        if c.requirement_id == CONTEXT_REQUIREMENT_ID or c.requirement_id.startswith('stylist_'):
            errors.append(dict(field=prefix, code='code_owned_id'))
        if c.source == 'reference':
            facts = (_at(documents, fields['conditions[source=reference].source_text'][0])
                     if documents.get('similarity_reference') else {})
            if (not c.source_text.strip() or not any(c.source_text in v for vs in facts.values() for v in vs)
                    or c.role != 'target' or c.polarity != 'positive' or c.attribute in reference_forbidden):
                error = dict(field=prefix, code='invalid_reference_condition')
                errors.append(error)
                if (c.role == 'target' or observe_reference_roles) and c.polarity == 'positive' and c.attribute not in reference_forbidden:
                    source_errors.append(error)
        else:
            key = 'conditions[source=user,attribute=gender].source_text' if c.attribute == 'gender' else 'conditions[source=user].source_text'
            check_quote(prefix + '.source_text', c.source_text, fields[key])
        if c.attribute == 'avoid_product_type' and c.polarity != 'negative':
            errors.append(dict(field=prefix, code='avoid_requires_negative'))
        if c.attribute == 'product_type' and c.polarity != 'positive':
            errors.append(dict(field=prefix, code='product_type_requires_positive_use_avoid_for_dislikes'))
    if sum(c.attribute == 'price' and c.role == 'target' for c in conditions) > 1:
        errors.append(dict(field='conditions', code='combine_price_bounds'))
    check_quote('audience_interpretation.source_text', structure.audience_interpretation.source_text,
        fields['audience_interpretation.source_text'])
    if errors:
        if observe_semantics:
            from fashion_recommendation_v2.search.semantic_validation import semantic_failure
            from fashion_recommendation_v2.search.semantic_validation import record_only
            if record_only():
                for error in source_errors:
                    semantic_failure('source_meaning', json.dumps(error, ensure_ascii=False))
                errors = [e for e in errors if e not in source_errors]
    if errors:
        raise ValueError(json.dumps({'stage': 'structure_validation', 'errors': errors}, ensure_ascii=False))
    # Stylist is not model output: attach its original values without normalization.
    seen = set()
    stylist_entries = (_at(documents, fields['code_attached_stylist'][0])
                       if documents.get('stylist_resolution') else [])
    for entry in stylist_entries:
        original = {k: deepcopy_v26(entry[k]) for k in ('attribute', 'value', 'source_text')}
        from fashion_recommendation_v2.stylist_personalization import condition_provenance
        if getattr(source.stylist_resolution, 'contract_version', None) in {'stylist-v2', 'stylist-v3', 'stylist-v4', 'stylist-v5', 'stylist-v6'}:
            from fashion_recommendation_v2.schemas.stylist import StylistInterpretationV2_v2 as StylistInterpretationV2
            from fashion_recommendation_v2.schemas.stylist import StylistInterpretationV3_v3 as StylistInterpretationV3
            row_schema = StylistInterpretationV3 if source.stylist_resolution.contract_version in {'stylist-v3', 'stylist-v4', 'stylist-v5', 'stylist-v6'} else StylistInterpretationV2
            original['stylist_provenance'] = condition_provenance(source.stylist_resolution,
                row_schema.model_validate(entry))
        identity = json.dumps(original, ensure_ascii=False, sort_keys=True)
        if identity in seen:
            continue  # Preserve original input; match existing exact-copy deduplication policy.
        seen.add(identity)
        conditions.append(StylistConditionV26(requirement_id=f'stylist_{len(seen):03d}',
            source='stylist', role='target', polarity='positive', **deepcopy_v26(original)))
    if not any(c.role == 'target' for c in conditions):
        raise ValueError('No target conditions remain after structuring.')
    return conditions


@_preserve_function('dimension', 'fashion_recommendation_v2.search.requirements_v26')
def dimension_v26(condition):
    return (condition.attribute, condition.value.key if condition.attribute == 'detail' else None)


@_preserve_function('bind_applications', 'fashion_recommendation_v2.search.requirements_v26')
def bind_applications_v26(source, structure, conditions, applications, *, dimension_key=None, user_avoid_kind='soft',
                      scope_rules=None, stylist_conflicts=None):
    """Join ID-only labels. Keep every condition value and quote byte-for-byte."""
    before = [c.model_dump(mode='json') for c in conditions]
    dimension_key = dimension_v26 if dimension_key is None else dimension_key
    labels = {}
    for group, entries, user in [('user_applications', applications.user_applications, True),
                                  ('preserved_applications', applications.preserved_applications, False)]:
        expected = {c.requirement_id for c in conditions if c.role == 'target' and (c.source == 'user') == user}
        ids = [a.requirement_id for a in entries]
        if len(ids) != len(set(ids)) or set(ids) != expected:
            raise ValueError(f'{group}: IDs must cover exactly the original target conditions once; no omissions, duplicates or new IDs.')
        labels.update({a.requirement_id: a for a in entries})
    rows, suppressed = [], []
    for c in conditions:
        if c.role == 'anchor':
            suppressed.append(dict(requirement_id=c.requirement_id, reason='anchor_context_not_target_constraint'))
            continue
        label = labels[c.requirement_id]
        kind = label.kind if c.source == 'user' else 'soft'
        scope = label.evaluation_scope
        # Invalid classification terminates. Do not silently rewrite labels or original meaning.
        if c.polarity == 'unrestricted' and (kind, scope) != ('soft', 'item'):
            raise ValueError(f'{c.requirement_id}: unrestricted conditions require soft/item.')
        if not (scope_rules or {}).get('independent_product_type_source_kind', False) and c.attribute == 'product_type' and (kind, scope) != ('hard', 'search') and not (
                scope_rules is not None and kind == 'soft' and scope == 'search'):
            raise ValueError(f'{c.requirement_id}: target product_type requires hard/search.')
        if c.attribute == 'price' and (kind, scope) != ('hard', 'item'):
            raise ValueError(f'{c.requirement_id}: price requires hard/item.')
        if c.attribute == 'gender' and c.source == 'user' and c.polarity == 'positive' and (kind, scope) != ('hard', 'search'):
            raise ValueError(f'{c.requirement_id}: explicit product audience requires hard/search.')
        avoid_kind = user_avoid_kind if c.source == 'user' else 'soft'
        if c.attribute == 'avoid_product_type' and (kind, scope) != (avoid_kind, 'item'):
            raise ValueError(f'{c.requirement_id}: product dislikes require {avoid_kind}/item.')
        if c.polarity == 'negative' and scope != 'item':
            raise ValueError(f'{c.requirement_id}: negative conditions must remain item-only.')
        expected_scope = ('search' if c.attribute in (scope_rules['hard_search_attributes']
                          if scope_rules else core_attributes_v26('v26')) else 'item')
        if scope_rules and c.polarity in {'negative', 'unrestricted'}:
            expected_scope = scope_rules['negative_scope']
        if kind == 'hard' and scope != expected_scope:
            raise ValueError(f'{c.requirement_id}: hard condition has the wrong scope.')
        original = c.model_dump(mode='json', include={'requirement_id', 'attribute', 'value', 'source', 'source_text'})
        if getattr(c, 'stylist_provenance', None) is not None:
            original['stylist_provenance'] = c.stylist_provenance.model_dump(mode='json')
        rows.append({**deepcopy_v26(original), 'kind': kind, 'evaluation_scope': scope,
                     'unrestricted': c.polarity == 'unrestricted'})
    by_id = {c.requirement_id: c for c in conditions}
    users = [r for r in rows if r['source'] == 'user']
    retained = []
    for row in rows:
        c = by_id[row['requirement_id']]
        overrides = [u for u in users if dimension_key(by_id[u['requirement_id']]) == dimension_key(c)
            and ((row['source'] == 'stylist' and u['kind'] == 'hard' and
                  (stylist_conflicts is None or (c.requirement_id, u['requirement_id']) in stylist_conflicts))
                 or (row['source'] == 'reference' and u['value'] != row['value']))]
        if overrides:
            suppressed.append(dict(requirement_id=c.requirement_id, reason='explicit_user_precedence',
                overridden_by=[u['requirement_id'] for u in overrides]))
        else:
            retained.append(row)
    inventory = [ProductTypeAlternative(requirement_id=r['requirement_id'], value=v, source_text=r['source_text'])
        for r in retained if r['attribute'] == 'product_type'
        for v in (r['value'] if isinstance(r['value'], list) else [r['value']])]
    types = list(dict.fromkeys(a.value for a in inventory))
    explicit = [r for r in retained if r['source'] == 'user' and r['attribute'] == 'gender']
    dress_or_skirt = dress_skirt_diversity_exempt(types)
    exemption = 'explicit_user_gender' if explicit else 'dress_or_skirt_product_type' if dress_or_skirt else None
    quotes = ([r['source_text'] for r in explicit] if explicit else [a.source_text for a in inventory]) or [source.user_query]
    policy = GenderDiversityPolicy(required=exemption is None, exemption=exemption,
        interpreted_product_types=types, source_texts=list(dict.fromkeys(quotes)),
        reason='Code-derived from preserved explicit audience and positive target product alternatives.')
    output = RequirementsExtractionV8(requirements=retained, product_type_alternatives=inventory,
        gender_diversity_policy=policy)
    interpretation = AudienceInterpretationV1_v26.model_validate(structure.audience_interpretation.model_dump())
    decision = decide_audience(source.audience_context_v1, output, interpretation)
    resolved = apply_audience_decision(output, decision, requirements_id='requirements_' + uuid4().hex)
    from fashion_recommendation_v2.search.condition_semantics import bind_condition_contract
    resolved.condition_contract_v26 = bind_condition_contract(resolved)
    assert_preserved(conditions, resolved)
    if before != [c.model_dump(mode='json') for c in conditions]:
        raise ValueError('Condition inventory mutated during application binding.')
    return resolved, dict(suppressed_conditions=suppressed,
        application_reasons={key: value.reason for key, value in labels.items()})


@_preserve_function('assert_preserved', 'fashion_recommendation_v2.search.requirements_v26')
def assert_preserved(conditions, resolved):
    by_id = {c.requirement_id: c.model_dump(mode='json') for c in conditions}
    for r in resolved.requirements:
        if r.source == 'context':
            continue  # Code-owned audience is a separately derived condition.
        raw = r.model_dump(mode='json')
        if r.requirement_id not in by_id or any(raw[k] != by_id[r.requirement_id][k]
                for k in ('attribute', 'value', 'source', 'source_text')):
            raise ValueError(f'Original condition changed: {r.requirement_id}')


# ---- requirements_v30 ----
"""Executable projections for recoverable requirement errors, without LLM repair."""
from copy import deepcopy as deepcopy_v30
from types import SimpleNamespace
from typing import get_args

from fashion_recommendation_v2.schemas.price import PriceConstraint
from fashion_recommendation_v2.schemas.stylist import StylistDetailValue_base as StylistDetailValue
from fashion_recommendation_v2.schemas.search.requirements.search_requirements import AttributeV30
from fashion_recommendation_v2.schemas.search.requirements.search_requirements import RequirementsClassificationV26
from fashion_recommendation_v2.schemas.search.requirements.search_requirements_context import AudienceInterpretationV1
structure_and_sources = structure_and_sources_v26
bind_applications = bind_applications_v26
original_source_contract = source_contract_v26
from fashion_recommendation_v2.search.audience_policy import derive_audience_v30
from fashion_recommendation_v2.search.audience_policy import audience_context_v30
from fashion_recommendation_v2.search.requirement_sources import recover_condition_quote_v30
from fashion_recommendation_v2.search.requirement_sources import RECOVERY_TERMS_V30
from fashion_recommendation_v2.search.requirement_sources import recovery_contract_v30
from fashion_recommendation_v2.search.requirement_sources import resolved_stylist_duplicate_v30
from fashion_recommendation_v2.search.requirement_sources import validate_reference_binding_v30
from fashion_recommendation_v2.search.requirement_sources import projected_reference_binding_v30
from fashion_recommendation_v2.search.requirement_sources import accepted_product_alternative_v30
from fashion_recommendation_v2.search.requirement_sources import condition_values_v30
from fashion_recommendation_v2.search.requirement_sources import product_alternative_span_v30
from fashion_recommendation_v2.search.requirement_sources import reference_quote_projection_v30
from fashion_recommendation_v2.search.condition_semantics import ATTRIBUTE_ALIASES_V30
from fashion_recommendation_v2.search.condition_semantics import provenance_dimension_v30
from fashion_recommendation_v2.search.planning_rules import core_attributes
from fashion_recommendation_v2.search.semantic_validation import semantic_failure as semantic_failure_v30

# These are semantic identities, not fuzzy string substitutions. Native lists
# remain lists (OR); an object's values list remains a list in a native projection.
NATIVE_ATTRIBUTES = frozenset(get_args(AttributeV30)) - {'detail', 'price', 'category'}
ATTRIBUTE_ALIASES = dict(ATTRIBUTE_ALIASES_V30)


@_preserve_function('source_contract', 'fashion_recommendation_v2.search.requirements_v30')
def source_contract_v30(source):
    contract = original_source_contract(source)
    contract['revision'] = 'field-sources-v30'
    contract['recovery'] = dict(raw_response='immutable', **recovery_contract_v30())
    contract['audience_metadata_sources'] = ['audience_context_v1.reference', 'similarity_reference.attributes.gender',
                                           'similarity_reference.attributes.detail.gender']
    return contract


@_preserve_function('execution_source', 'fashion_recommendation_v2.search.requirements_v30')
def execution_source(source):
    """Code-derived context only; the fixed model input and original stay intact."""
    return source.model_copy(update={'audience_context_v1': audience_context_v30(source)}, deep=True)


@_preserve_function('semantic_key', 'fashion_recommendation_v2.search.requirements_v30')
def semantic_key(attribute, value=None):
    return provenance_dimension_v30(attribute, value)


@_preserve_function('dimension', 'fashion_recommendation_v2.search.requirements_v30')
def dimension(condition):
    return semantic_key(condition.attribute, condition.value)


@_preserve_function('application_rules', 'fashion_recommendation_v2.search.requirements_v30')
def application_rules_v30():
    return dict(hard_search_attributes=sorted(core_attributes('v30')),
        other_hard_scope='item', negative_scope='item', unrestricted=['soft', 'item'],
        target_product_type=['hard', 'search'], price=['hard', 'item'],
        positive_explicit_gender=['hard', 'search'], avoid_product_type=['soft', 'item'],
        preserved_kind='soft', scope_recovery='code corrects scope; never changes kind',
        aliases=ATTRIBUTE_ALIASES, native_attributes=sorted(NATIVE_ATTRIBUTES),
        source_recovery_terms=RECOVERY_TERMS_V30)


@_preserve_function('note', 'fashion_recommendation_v2.search.requirements_v30')
def note(notes, code, rid, before, after, *, paths=()):
    if before != after:
        notes.append(dict(code=code, requirement_id=rid, original=deepcopy_v30(before),
                          derived=deepcopy_v30(after), source_paths=list(paths)))


@_preserve_function('project_condition', 'fashion_recommendation_v2.search.requirements_v30')
def project_condition(condition, notes):
    """Validate the executable shape, preserving the received condition separately."""
    raw = condition.model_dump(mode='json')
    c = condition.model_copy(deep=True)
    value = c.value
    if isinstance(value, PriceConstraint):
        if c.attribute != 'price':
            raise ValueError(f'{c.requirement_id}: price object conflicts with its attribute.')
    elif c.attribute == 'price':
        raise ValueError(f'{c.requirement_id}: price requires its original currency and structured bounds.')
    elif isinstance(value, StylistDetailValue):
        key = ATTRIBUTE_ALIASES.get(value.key, value.key)
        attribute = ATTRIBUTE_ALIASES.get(c.attribute, c.attribute)
        if c.attribute != 'detail' and key != attribute:
            semantic_failure_v30('attribute_meaning', f'{c.requirement_id}: attribute and detail key have conflicting meanings.',
                             condition=raw)
            return c  # B preserves the proposal; no guessed correction of its meaning.
        if key == 'price':
            raise ValueError(f'{c.requirement_id}: price requires its original structured currency and bounds.')
        if key in NATIVE_ATTRIBUTES and (c.attribute != 'detail' or value.key in ATTRIBUTE_ALIASES):
            c = c.model_copy(update={'attribute': key, 'value': deepcopy_v30(value.values)})
        elif c.attribute != 'detail':
            raise ValueError(f'{c.requirement_id}: unregistered detail shape cannot be repaired.')
        elif value.key in ATTRIBUTE_ALIASES:
            c = c.model_copy(update={'value': value.model_copy(update={'key': key})})
    elif c.attribute == 'detail':
        raise ValueError(f'{c.requirement_id}: a detail without its key cannot be reconstructed.')
    elif c.attribute in ATTRIBUTE_ALIASES:
        c = c.model_copy(update={'attribute': ATTRIBUTE_ALIASES[c.attribute]})
    if isinstance(c.value, list) and (not c.value or len(set(c.value)) != len(c.value)):
        raise ValueError(f'{c.requirement_id}: OR alternatives must be nonempty and unique.')
    note(notes, 'registered_attribute_projection', c.requirement_id, raw, c.model_dump(mode='json'))
    return c


@_preserve_function('prepare_structure', 'fashion_recommendation_v2.search.requirements_v30')
def prepare_structure_v30(source, structure, *, observe_reference_roles=False):
    from fashion_recommendation_v2.query_composition import validate_composed_conditions
    validate_composed_conditions(source, structure.conditions)
    notes, projected, suppressed = [], [], []
    originals = [c.model_dump(mode='json') for c in structure.conditions]
    try:
        ids = [c.requirement_id for c in structure.conditions]
        if len(set(ids)) != len(ids):
            raise ValueError('duplicate_condition_id: validate original IDs before any source recovery.')
        if any(rid == 'context_audience_v1' or rid.startswith('stylist_') for rid in ids):
            raise ValueError('code_owned_id: model conditions cannot reuse reserved IDs.')
        shaped = []
        for original in structure.conditions:
            c = project_condition(original, notes)
            if c.source == 'reference':
                derived, paths = reference_quote_projection_v30(source, c)
                note(notes, 'verified_reference_quote', c.requirement_id, c.source_text, derived.source_text, paths=paths)
                c = derived
            shaped.append(c)
        # Verify all reference copies before using them to absorb an expanded
        # duplicate; mere quote presence in an unrelated fact cannot prove it.
        references = [c for c in shaped if c.source == 'reference']
        for c in references:
            validate_reference_binding_v30(source, c)
        def suppress(c, code, retained_ids, paths):
            row = dict(requirement_id=c.requirement_id, reason=code,
                retained_condition_ids=retained_ids, source_paths=paths)
            suppressed.append(row)
            note(notes, code, c.requirement_id, c.model_dump(mode='json'), row, paths=paths)
        for c in shaped:
            stylist = resolved_stylist_duplicate_v30(source, c)
            if stylist is not None:
                # Attach the original once through structure_and_sources, not
                # through the model's copy. Bind its generated ID below.
                suppress(c, 'resolved_stylist_duplicate', [], ['stylist_resolution.interpretations'])
                suppressed[-1]['stylist_original'] = stylist.model_dump(mode='json', include={'attribute','value','source_text'})
                continue
            facts = projected_reference_binding_v30(source, c)
            if facts:
                fact_values = list(dict.fromkeys(f['value'] for f in facts))
                covered = [r for r in references if dimension(r) == dimension(c)
                    and set(condition_values_v30(r)) <= set(fact_values)]
                # A preserved OR row may cover a split projected detail. Keep
                # that row whole; never split or rewrite its OR structure.
                covered += [r for r in references if dimension(r) == dimension(c)
                    and set(fact_values) <= set(condition_values_v30(r)) and r not in covered]
                paths = list(dict.fromkeys(f['path'] for f in facts))
                if set(fact_values) <= {v for r in covered for v in condition_values_v30(r)}:
                    suppress(c, 'inherited_reference_duplicate', [r.requirement_id for r in covered], paths)
                    continue
                # Missing reference copy: carry the source's facts under the
                # original condition ID, not the expansion's extra precision.
                if isinstance(c.value, StylistDetailValue):
                    value = c.value.model_copy(update={'values': fact_values})
                elif isinstance(c.value, list) or len(fact_values) != 1:
                    value = fact_values
                else:
                    value = fact_values[0]
                derived = c.model_copy(update={'source': 'reference', 'source_text': fact_values[0], 'value': value})
                validate_reference_binding_v30(source, derived)
                note(notes, 'verified_reference_source', c.requirement_id, c.model_dump(mode='json'),
                     derived.model_dump(mode='json'), paths=paths)
                c = derived
            if c.source == 'reference' and c.attribute == 'product_type':
                matches = [r for r in shaped if r.source == 'user' and r.role == 'target'
                    and r.attribute == 'product_type' and r.polarity == 'positive'
                    and set(condition_values_v30(c)) <= set(condition_values_v30(r))]
                if matches and c.role == 'target' and c.polarity == 'positive':
                    suppress(c, 'reference_target_type_duplicate', [r.requirement_id for r in matches],
                        [f['path'] for f in validate_reference_binding_v30(source, c)])
                    continue
            if accepted_product_alternative_v30(source, c):
                note(notes, 'accepted_product_alternative', c.requirement_id, c.polarity, 'positive', paths=('user_query',))
                c = c.model_copy(update={'polarity': 'positive'})
            quote, paths = recover_condition_quote_v30(source, c)
            note(notes, 'verified_source_projection', c.requirement_id, c.source_text, quote, paths=paths)
            projected.append(c.model_copy(update={'source_text': quote}))
        targets = [c for c in projected if c.source == 'user' and c.attribute == 'product_type'
                   and c.role == 'target' and c.polarity == 'positive']
        span = product_alternative_span_v30(source, targets)
        if span:
            # Existing planning/evaluation treats a single value list as OR.
            # Separate hard product rows would incorrectly mean dress AND set.
            values = list(dict.fromkeys(v for c in targets for v in condition_values_v30(c)))
            merged = targets[0].model_copy(update={'value': values, 'source_text': span})
            note(notes, 'accepted_target_or_group', merged.requirement_id,
                 [c.model_dump(mode='json') for c in targets], merged.model_dump(mode='json'), paths=('user_query',))
            for c in targets[1:]:
                suppress(c, 'accepted_target_or_member', [merged.requirement_id], ['user_query'])
            projected = [merged if c.requirement_id == merged.requirement_id else c
                         for c in projected if c not in targets[1:]]
        unique = []
        for c in projected:
            explicit = [r for r in projected if c.source == 'reference' and r.source == 'user'
                        and r.role == 'target' and r.polarity == 'positive' and dimension(r) == dimension(c)
                        and condition_values_v30(r) == condition_values_v30(c)]
            if explicit:
                suppress(c, 'explicit_reference_duplicate', [r.requirement_id for r in explicit], ['user_query'])
            else:
                unique.append(c)
        projected = unique
        audience = AudienceInterpretationV1.model_validate(derive_audience_v30(source, projected))
        execution_context = audience_context_v30(source)
        category_context = hasattr(execution_context, 'anchor_category')
        note(notes, 'category_anchor_audience_context' if category_context else 'verified_anchor_metadata',
             None, source.audience_context_v1.model_dump(mode='json'),
             execution_context.model_dump(mode='json'),
             paths=('relation_intent.anchor_category',) if category_context else ('similarity_reference',))
        note(notes, 'code_audience_policy', None,
             structure.audience_interpretation.model_dump(mode='json', exclude={'reason'}),
             audience.model_dump(mode='json', exclude={'reason'}), paths=('audience_context_v1', 'user_query') + (('relation_intent.anchor_category',) if category_context else ()))
        effective_structure = SimpleNamespace(conditions=projected, audience_interpretation=audience)
        conditions = structure_and_sources(source, effective_structure, observe_semantics=True,
                                            observe_reference_roles=observe_reference_roles)
        for row in suppressed:
            if 'stylist_original' in row:
                row['retained_condition_ids'] = [c.requirement_id for c in conditions if c.source == 'stylist'
                    and c.model_dump(mode='json', include={'attribute','value','source_text'}) == row['stylist_original']]
        # Follow duplicate aliases to actual retained IDs (a reference copy can
        # itself be covered by an explicit user condition). Cycles/dangling
        # references must never make a condition silently disappear.
        kept_ids = {c.requirement_id for c in conditions}
        aliases = {row['requirement_id']: row['retained_condition_ids'] for row in suppressed}
        def retained(rid, seen):
            if rid in kept_ids:
                return [rid]
            if rid in seen or not aliases.get(rid):
                raise ValueError('Recovered duplicate has no retained authoritative condition.')
            return [target for alias in aliases[rid] for target in retained(alias, seen | {rid})]
        for row in suppressed:
            row['retained_condition_ids'] = list(dict.fromkeys(retained(row['requirement_id'], set())))
            for recovery in notes:
                if recovery['requirement_id'] == row['requirement_id'] and recovery['code'] == row['reason']:
                    recovery['derived'] = deepcopy_v30(row)
        return effective_structure, conditions, dict(recoveries=notes,
            original_conditions=originals, suppressed_conditions=suppressed,
            conditions=[c.model_dump(mode='json') for c in conditions],
            audience_context=execution_context.model_dump(mode='json'),
            audience_interpretation=audience.model_dump(mode='json'))
    except Exception as exc:
        exc.code_derived = dict(recoveries=notes, original_conditions=originals,
            conditions=[c.model_dump(mode='json') for c in projected], suppressed_conditions=suppressed)
        raise


@_preserve_function('finalize_conditions', 'fashion_recommendation_v2.search.requirements_v30')
def finalize_conditions_v30(source, structure, conditions, applications, *, rules=None, stylist_conflicts=None):
    # Only application labels are projected here; stage-one condition objects
    # (including raw Stylist OR values and quotes) are never rewritten.
    before = [c.model_dump(mode='json') for c in conditions]
    labels = applications.model_dump(mode='json')
    by_id = {c.requirement_id: c for c in conditions}
    notes = []
    rules = application_rules_v30() if rules is None else rules
    for group, user in [('user_applications', True), ('preserved_applications', False)]:
        expected = {c.requirement_id for c in conditions if c.role == 'target' and (c.source == 'user') == user}
        actual = [r['requirement_id'] for r in labels[group]]
        if len(actual) != len(set(actual)) or set(actual) != expected:
            raise ValueError(f'{group}: exact original target ID coverage required before application recovery.')
    for group in ('user_applications', 'preserved_applications'):
        for row in labels[group]:
            c = by_id.get(row['requirement_id'])
            if c is None:
                raise ValueError('Classification references an unknown condition ID.')
            kind = row.get('kind', 'soft')
            scope = row['evaluation_scope']
            if c.polarity in {'negative', 'unrestricted'} or c.attribute == 'avoid_product_type':
                scope = rules['negative_scope']
            elif kind == 'hard':
                scope = 'search' if c.attribute in rules['hard_search_attributes'] else rules['other_hard_scope']
            elif c.source in {'user', 'stylist'} and dimension(c) in rules.get('soft_search_attributes', ()):
                scope = 'search'
            note(notes, 'code_application_scope', c.requirement_id, row['evaluation_scope'], scope)
            row['evaluation_scope'] = scope
    try:
        # A soft re-interpretation of the exact same Stylist source clause must
        # not replace its original OR values. Keep hard explicit overrides; do
        # not confuse overlapping words or a separate user clause with a copy.
        duplicate_ids, duplicates = set(), []
        for row in labels['user_applications']:
            c = by_id[row['requirement_id']]
            matches = [s for s in conditions if s.source == 'stylist' and dimension(s) == dimension(c)
                       and s.source_text == c.source_text]
            if row['kind'] == 'soft' and c.polarity == 'positive' and len(matches) == 1:
                duplicate_ids.add(c.requirement_id)
                recovery = dict(requirement_id=c.requirement_id, reason='soft_stylist_reinterpretation',
                    retained_condition_ids=[matches[0].requirement_id], source_paths=['stylist_resolution.interpretations'])
                duplicates.append(recovery)
                note(notes, recovery['reason'], c.requirement_id, c.model_dump(mode='json'), recovery,
                     paths=recovery['source_paths'])
        effective_conditions = [c for c in conditions if c.requirement_id not in duplicate_ids]
        labels['user_applications'] = [r for r in labels['user_applications'] if r['requirement_id'] not in duplicate_ids]
        derived_labels = RequirementsClassificationV26.model_validate(labels)
        resolved, details = bind_applications(execution_source(source), structure, effective_conditions, derived_labels,
            dimension_key=dimension, user_avoid_kind=rules['avoid_product_type'][0],
            **(dict(scope_rules=rules, stylist_conflicts=stylist_conflicts) if 'soft_search_attributes' in rules else {}))
        details['suppressed_conditions'].extend(duplicates)
        if before != [c.model_dump(mode='json') for c in conditions]:
            raise ValueError('Original inventory mutated while binding v30 applications.')
        return resolved, dict(**details, recoveries=notes,
            applications=labels, resolved_requirements=resolved.model_dump(mode='json'))
    except Exception as exc:
        exc.code_derived = dict(recoveries=notes, applications=labels)
        raise


@_preserve_function('requirements_semantics', 'fashion_recommendation_v2.search.requirements_v30')
def requirements_semantics_v30():
    return """
Structure every explicit searchable condition, positive/negative/unrestricted
meaning, OR alternatives, and target/paired-anchor roles. Keep IDs, value types
and exact quotations. A paired garment is context, not a target constraint.
For 롱스커트와 입을 상의, structure top as target and skirt as paired anchor.
Less feminine is a style preference, never an instruction to find menswear.
Use English fashion values but preserve source quotations and identifiers.
Do not combine negatives with positive product-type alternatives. A genuinely
ambiguous two-piece remains ambiguous; dislike of pants alone is not a ban.
Use user_query to find searchable clauses, not to assign every expanded fact to
the user. With similarity_reference, only clauses also in its user_query are new
user intent; expanded-only descriptions belong to the supplied reference facts.
Use only projected user_query and resolved context. Original-only omitted
clauses and unresolved Stylist interpretations must not reappear as conditions.
Stylist conditions are attached by code from stylist_resolution; never emit a
Stylist copy, convert its attribute/value/OR type, or relabel it as user input.
With similarity_reference, new explicit intent is user; inherited known facts
are reference and soft, including all known design details. Ignore unknown facts,
seller operations, prior price budgets and previous ranking explanations.
Reference quotations must come from supplied facts. User quotes follow SOURCE_RULES.
An allowed alternative ('투피스도 괜찮다') is a positive product alternative,
not unrestricted. Put all allowed target product types in ONE OR value list.
Do not narrow an ambiguous two-piece to a skirt set from dislike of pants.
Inherited product type is context, not an additional soft reference condition;
the explicit requested target already supplies its hard condition.
hard means mandatory eligibility; soft means negotiable preference. A stated
brand restriction is hard, '가능하면' is soft. Do not promote inherited conditions.
Apply APPLICATION_RULES. Code determines mandatory scope, audience precedence,
and both diversity fields from one retained product-type inventory. An invalid
scope never weakens hard into soft. A wrong kind or ambiguous evidence stops.
Audience is product context. Only actual audience_context_v1.reference.gender
or similarity_reference.attributes gender metadata supports anchor audience;
a mentioned skirt uses the registered product default instead. One OR list and
separate allowed-alternative rows use the same positive-garment defaults.
Code ignores unsupported proposed policy fields and derives them from verified
inputs. No gender words are required to apply a supported garment default.
Original model_response is immutable. CODE_DERIVED conditions explain registered
shape/source projections; they retain their original IDs. Classification returns
only ID-linked kind/scope/reason, never replacement attributes, values or quotes.
No audit, regenerated extraction, marketplace query or filter generation here.
"""


# ---- requirements_v31 ----
"""Verified execution-only role projection; raw model and source facts stay intact."""
from copy import deepcopy as deepcopy_v31
prepare_v30 = prepare_structure_v30
finalize_conditions_v31 = finalize_conditions_v30
from fashion_recommendation_v2.search.reference_roles import target_role_evidence
from fashion_recommendation_v2.search.semantic_validation import semantic_failure
from fashion_recommendation_v2.search.semantic_validation import observed
from fashion_recommendation_v2.search.semantic_validation import experiment_records


@_preserve_function('prepare_structure', 'fashion_recommendation_v2.search.requirements_v31')
@observed('requirements')
def prepare_structure_v31(source, structure, *, version='v31'):
    projected = structure.model_copy(deep=True)
    recoveries = []
    for condition in projected.conditions:
        if condition.source != 'reference' or condition.role != 'anchor':
            continue
        before = condition.model_dump(mode='json')
        facts = target_role_evidence(source, condition)
        diagnostic = dict(requirement_id=condition.requirement_id, actual_role='anchor',
            expected_role='target', source='reference', original_condition=before,
            source_paths=[f['path'] for f in facts],
            instruction='Preserve attribute/value/source/source_text/OR; change only role when similarity binding is proven.')
        if facts:
            condition.role = 'target'
            recoveries.append(dict(code='verified_reference_target_role', **diagnostic,
                                   derived_condition=condition.model_dump(mode='json')))
        else:
            semantic_failure('source_meaning',
                f'{condition.requirement_id}: reference/anchor is unresolved. Similarity target role requires matching '
                'attribute, every value and quote in supplied similarity_reference. No automatic promotion; '
                'condition remains context-only and must not be silently treated as a searched preference.', **diagnostic)
    try:
        effective, conditions, derived = prepare_v30(source, projected, observe_reference_roles=True)
    except Exception as exc:
        if hasattr(exc, 'code_derived'):
            exc.code_derived['original_conditions'] = [c.model_dump(mode='json') for c in structure.conditions]
            exc.code_derived['recoveries'] = recoveries + exc.code_derived.get('recoveries', [])
        raise
    derived['original_conditions'] = [c.model_dump(mode='json') for c in structure.conditions]
    derived['recoveries'] = recoveries + derived['recoveries']
    return effective, conditions, deepcopy_v31(derived)


@_preserve_function('validate_consumed_sources', 'fashion_recommendation_v2.search.requirements_v31')
@observed('consumer_sources')
def validate_consumed_sources(source, requirements, *, version='v31'):
    """Consumers must not turn a recorded source warning back into a blocker."""
    from fashion_recommendation_v2.search.requirement_sources import validate_field_sources
    start = len(experiment_records())
    validate_field_sources(source, requirements, observe_semantics=True)
    return deepcopy_v31(experiment_records()[start:])


# ---- requirements_v35 ----
"""v35 target garment semantics; source projection and scope recovery stay frozen."""
previous_rules_v35 = application_rules_v30
bind_conditions = finalize_conditions_v30
source_contract_v35 = source_contract_v30
prepare_structure_v35 = prepare_structure_v31


@_preserve_function('application_rules', 'fashion_recommendation_v2.search.requirements_v35')
def application_rules_v35():
    return {**previous_rules_v35(), 'avoid_product_type': ['hard', 'item'],
            'target_product_details': 'explicit user garment identity/shape/construction/length: hard; use scope rules'}


@_preserve_function('finalize_conditions', 'fashion_recommendation_v2.search.requirements_v35')
def finalize_conditions_v35(source, structure, conditions, applications):
    return bind_conditions(source, structure, conditions, applications, rules=application_rules_v35())


@_preserve_function('requirements_semantics', 'fashion_recommendation_v2.search.requirements_v35')
def requirements_semantics():
    return """
Structure every explicit searchable condition, its positive/negative/unrestricted
meaning, OR alternatives and target/paired-anchor role. Preserve IDs, value types
and exact quotations. A paired garment is context, not a target constraint:
롱스커트와 입을 상의 means a target top and a paired skirt anchor.
Use English fashion values; preserve source quotations and identifiers.
Use projected user_query and resolved context only. Original-only omitted clauses
and unresolved Stylist interpretations must not reappear. User_query expansions
do not make reference or Stylist facts user instructions. With similarity_reference,
only clauses in its user_query are new user intent; inherited known facts are
reference/soft, including design details. Ignore unknown reference facts, seller
operations, previous budgets and ranking explanations. Quote supplied reference facts.
Code attaches Stylist conditions from stylist_resolution: never emit copies or
rewrite attribute/value/source_text, OR type, or source as user.

hard is mandatory eligibility; soft is negotiable preference. The user's specified
target product type, excluded product types, and details defining the requested
garment's shape/construction/length are hard. Polite desire or dislike phrasing
(~였으면 좋겠다, ~는 별로다) does not make these product-defining constraints soft.
Examples: a long skirt, cropped jacket, sleeveless top, closed neckline, or avoiding
trousers define eligible garments. Keep the actual detail in its native attribute
or detail.key; do not fold it into product_type or invent an unspoken constraint.
This is a general garment-identity rule, not a rule for a particular case/product.
Color, pattern, styling/mood and occasion preferences are not automatically hard
merely because they describe a product. Explicit mandatory restrictions are hard;
truly negotiable preferences are soft. Explicitly unrestricted details stay soft/item.
Do not promote inherited reference/Stylist preferences or paired-anchor properties.
Less feminine is style, not an instruction to find menswear.
Put all permitted positive target types in ONE OR list. '투피스도 괜찮다' is an
allowed alternative, not unrestricted. Keep an ambiguous two-piece ambiguous:
record a trousers exclusion separately, without silently narrowing two-piece to
skirt set or changing OR values. Evaluate that exclusion against actual items.
Inherited product type is context, not another soft condition; the requested
target already supplies its hard condition. Negative conditions stay item-only.

Apply APPLICATION_RULES. Code owns scope, audience precedence, and diversity fields
from the retained positive product-type inventory. Invalid scope never weakens kind.
Audience is product context. Only audience_context_v1.reference.gender or actual
similarity_reference gender metadata supports anchor audience; a mentioned skirt
uses the registered product default. One OR list and separate alternatives use the
same defaults; gender words need not occur in the query. Code ignores unsupported
proposed audience policy and derives final policy from verified inputs.
Raw model_response is immutable. CODE_DERIVED projections keep condition IDs.
Classification returns ID-linked kind/scope/reason, not replacement facts or quotes.
No audit, regenerated extraction, marketplace query or filter generation here.
"""


# ---- requirements_v37 ----
"""v37 condition routing; product facts and raw responses remain unchanged."""
from copy import deepcopy
prepare_products = prepare_structure_v31
bind_products_v37 = finalize_conditions_v35
from fashion_recommendation_v2.schemas.search.requirements.search_requirements import RequirementsClassificationV30_v30 as RequirementsClassificationV30
from fashion_recommendation_v2.schemas.condition_routing import ConditionRoutingV37
from fashion_recommendation_v2.schemas.condition_routing import ConditionAssignment
from fashion_recommendation_v2.schemas.condition_routing import product_condition_owner


SEMANTICS_v37 = """
Structure product conditions and relationship clauses in separate inventories.
Product conditions preserve source/role/polarity, exact quote, attribute/value/OR
types. Only use projected user_query and resolved Stylist context. Never revive
omitted clauses from original-only fields. Code attaches Stylist entries; do not
duplicate them. New user intent comes from the actual current request, not expanded
reference prose. Reference facts are soft, role target when used for similarity.
Paired garment facts are role anchor and do not constrain the target garment.
Use English fashion values but retain original quotations. Put permitted target
types in one OR list; keep negatives separate and ambiguous two-piece ambiguous.
Do not infer menswear from 'less feminine'. Apply the supplied audience policy.

relation_conditions must preserve the supplied relation_intent exactly. Never
select a new anchor, change its rank/ID/category or relationship type. Quote only
the relationship clause from searchable user_query, including composed/expanded wording.
The relation clause quote need not occur in original_user_query. Keep intent.source_text
and every confirmed anchor field unchanged; this exception never reclassifies Stylist
or anchor observations as user product conditions.
Its target is search_target; it has no hard/soft or search/item label.
No supplied intent means no relationship clause; do not guess an unresolved anchor.

Classify every target product ID and relationship ID exactly once in assignments.
Relationship clauses and inherited reference similarity facts belong to relation.
Explicit user product requests and resolved Stylist preferences belong to ranking.
Ownership is independent of eligibility: hard products remain Search admission
constraints; only ranking-owned soft products contribute to Ranking R.

Product type, excluded type and explicit garment identity/construction/length are
hard. For compatibility/similarity, additionally specified product conditions are
hard unless the user clearly allows compromise or states an optional preference.
Polite '~였으면 좋겠다' alone does not soften a constraint. '편한 분위기면 좋겠어'
is a negotiable style preference, but '반드시 편한 스타일' is mandatory.
Inherited reference facts are never promoted to hard. Unrestricted conditions
remain unrestricted. With no relation request, preserve normal hard/soft rules:
mandatory brand/gender/price and garment identity versus negotiable styling.
Color and pattern preferences are not automatically hard merely because they
describe a product. When the user supplies two nested conditions describing the
same facet, classify the broader condition as hard and its narrower refinement
as soft. Preserve both condition IDs, values, types, sources and quotations;
do not merge them or invent an additional condition. This broad/narrow rule takes
precedence over the general product-condition hard default for such pairs.
Example: '꽃무늬 드레스 ... 잔꽃무늬였으면 좋겠고, 스커트 길이는 길었으면 좋겠어':
'꽃무늬' (floral) is the broad hard pattern; '잔꽃무늬' (small floral) is the
narrow soft pattern preference. The long skirt length is a separate facet and
remains hard. Do not treat unrelated conditions or alternatives in an OR list as
a broad/narrow pair, or promote inherited reference/Stylist facts through this rule.
Apply supplied APPLICATION_RULES for scope. Do not change facts while classifying.
'Similar but longer' retains a relative-to-anchor requirement, never absolute long.
List those product IDs in relative_requirement_ids; use [] for absolute requests.
Missing anchor length cannot prove it met. Search enforces the hard condition;
Relation still compares full similarity including length. No facet is excluded.
No extra audit, correction, search, image or ownership call is introduced here.
"""


@_preserve_function('prepare_structure', 'fashion_recommendation_v2.search.requirements_v37')
def prepare_structure_v37(source, output):
    relations = deepcopy(output.relation_conditions)
    expected = source.relation_intent
    if len(relations) != int(expected is not None):
        raise ValueError('Confirmed relation intent must have exactly one relationship clause.')
    ids = [c.requirement_id for c in output.conditions] + [r.requirement_id for r in relations]
    if len(ids) != len(set(ids)):
        raise ValueError('Product and relation condition IDs must be distinct.')
    for row in relations:
        from fashion_recommendation_v2.search.requirement_sources import source_rules
        from fashion_recommendation_v2.search.requirement_sources import source_documents
        from fashion_recommendation_v2.search.requirement_sources import _at
        rule = source_rules(source)['relation']
        if row.intent != expected or not row.source_text.strip() or any(
                row.source_text not in _at(source_documents(source), path) for path in rule.paths):
            raise ValueError('Relation clause must preserve confirmed intent and quote searchable user_query.')
    structure, conditions, derived = prepare_products(source, output)
    structure.relation_conditions = relations
    if not set(output.relative_requirement_ids) <= {c.requirement_id for c in conditions if c.role == 'target'}:
        raise ValueError('Relative comparison references a missing target product condition.')
    if output.relative_requirement_ids and expected is None:
        raise ValueError('Relative comparison requires a confirmed anchor intent.')
    structure.relative_requirement_ids = list(output.relative_requirement_ids)
    derived['relation_conditions'] = [r.model_dump(mode='json') for r in relations]
    return structure, conditions, derived


@_preserve_function('finalize_conditions', 'fashion_recommendation_v2.search.requirements_v37')
def finalize_conditions_v37(source, structure, conditions, output, *, product_binder=None):
    owners = {a.requirement_id: a.owner for a in output.assignments}
    expected = {c.requirement_id for c in conditions if c.role == 'target'} | {r.requirement_id for r in structure.relation_conditions}
    if len(owners) != len(output.assignments) or set(owners) != expected:
        raise ValueError('Exact scoring-owner coverage required.')
    for condition in conditions:
        if condition.role == 'target' and owners[condition.requirement_id] != product_condition_owner(condition.source):
            raise ValueError(f'{condition.requirement_id}: ownership contradicts authoritative condition source.')
    if any(owners[r.requirement_id] != 'relation' for r in structure.relation_conditions):
        raise ValueError('Relationship clauses must be assigned to Relation.')
    products = RequirementsClassificationV30.model_validate(output.model_dump(exclude={'assignments'}))
    result, derived = (product_binder or bind_products_v37)(source, structure, conditions, products)
    # Audience conditions are code-generated eligibility requirements, not reference preferences.
    routing = ConditionRoutingV37(relation_conditions=structure.relation_conditions,
        relative_requirement_ids=structure.relative_requirement_ids,
        anchor_comparison=(dict(item_id=source.similarity_reference.item_id,
            source='similarity_reference.attributes', attributes=deepcopy(source.similarity_reference.attributes))
            if source.similarity_reference and source.relation_intent and
               source.similarity_reference.item_id == source.relation_intent.anchor_item_id else {}),
        assignments=[ConditionAssignment(requirement_id=r.requirement_id,
            owner=owners.get(r.requirement_id, 'ranking')) for r in result.requirements] +
            [ConditionAssignment(requirement_id=r.requirement_id, owner='relation') for r in structure.relation_conditions])
    result.condition_routing_v37 = routing
    derived['condition_routing_v37'] = routing.model_dump(mode='json')
    return result, derived


@_preserve_function('ranking_condition_ids', 'fashion_recommendation_v2.search.requirements_v37')
def ranking_condition_ids(requirements):
    routing = requirements.condition_routing_v37
    if routing is None:
        raise ValueError('Search v37 requires validated condition routing.')
    requirements.__class__.model_validate(requirements.model_dump(mode='json'))
    owners = {r.requirement_id: r.owner for r in routing.assignments}
    return {r.requirement_id for r in requirements.requirements if r.kind == 'soft' and owners[r.requirement_id] == 'ranking'}


# ---- requirements_v40 ----
"""v40 role semantics; reuse unchanged provenance and routing mechanics."""
prepare_structure_v40 = prepare_structure_v37
finalize_conditions_v40 = finalize_conditions_v37

SEMANTICS_v40 = """
Structure product conditions and relationship clauses in separate inventories.
Product conditions preserve source/role/polarity, exact quote, attribute/value/OR
types. Only use projected user_query and resolved Stylist context. Never revive
omitted clauses from original-only fields. Code attaches Stylist entries; do not
duplicate them. New user intent comes from the actual current request, not expanded
reference prose. Reference facts are soft, role target when used for similarity.
Paired garment facts are role anchor and do not constrain the target garment.
Use English fashion values but retain original quotations. Put permitted target
types in one OR list; keep negatives separate and ambiguous two-piece ambiguous.
Do not infer menswear from 'less feminine'. Apply the supplied audience policy.

relation_conditions must preserve the supplied relation_intent exactly. Never
select a new anchor, change its rank/ID/category or relationship type. Quote only
the relationship clause from searchable user_query, including composed/expanded wording.
The relation clause quote need not occur in original_user_query. Keep intent.source_text
and every confirmed anchor field unchanged; this exception never reclassifies Stylist
or anchor observations as user product conditions.
Its target is search_target; it has no hard/soft or search/item label.
No supplied intent means no relationship clause; do not guess an unresolved anchor.

Classify every target product ID and relationship ID exactly once in assignments.
Relationship clauses and inherited reference similarity facts belong to relation.
Explicit user product requests and resolved Stylist preferences belong to ranking.
Ownership is independent of eligibility: hard products remain Search admission
constraints; only ranking-owned soft products contribute to Ranking R.

Product type, excluded type and explicit garment identity/construction/length are
hard. For compatibility/similarity, additionally specified product conditions are
hard unless the user clearly allows compromise or states an optional preference.
Polite '~였으면 좋겠다' alone does not soften a constraint. '편한 분위기면 좋겠어'
is a negotiable style preference, but '반드시 편한 스타일' is mandatory.
Inherited reference facts are never promoted to hard. Unrestricted conditions
remain unrestricted. With no relation request, preserve normal hard/soft rules:
mandatory brand/gender/price and garment identity versus negotiable styling.
Explicit current-user color requests default to hard, like product type and garment
length. Fit degree or wearing-feel preferences default to soft: “너무 달라붙지 않는”
and “너무 타이트하지 않은” are soft/item. This takes precedence over treating an
explicit garment shape or a negative expression as hard, including compatibility
requests. Only an explicit non-negotiable statement such as “반드시”, “절대”, or
“해당하면 제외” makes that fit preference hard. Polarity and kind are independent:
negative tight-fitting and positive not-too-tight preserve the same preference.
Never remove negation, change source_text/value/OR types, or broaden this exception
to garment construction/length. Reference and preserved Stylist source rules remain.
Example: “검정 롱스커트 찾아줘. 허리 밴딩이고 너무 달라붙지 않는 걸로.”:
skirt/color black/long length/elastic waistband are hard; not-too-tight fit is soft.
Pattern preferences are not automatically hard merely because they describe a product.
When the user supplies two nested conditions describing the
same facet, classify the broader condition as hard and its narrower refinement
as soft. Preserve both condition IDs, values, types, sources and quotations;
do not merge them or invent an additional condition. This broad/narrow rule takes
precedence over the general product-condition hard default for such pairs.
Example: '꽃무늬 드레스 ... 잔꽃무늬였으면 좋겠고, 스커트 길이는 길었으면 좋겠어':
'꽃무늬' (floral) is the broad hard pattern; '잔꽃무늬' (small floral) is the
narrow soft pattern preference. The long skirt length is a separate facet and
remains hard. Do not treat unrelated conditions or alternatives in an OR list as
a broad/narrow pair, or promote inherited reference/Stylist facts through this rule.
Apply supplied APPLICATION_RULES for scope. Do not change facts while classifying.
'Similar but longer' retains a relative-to-anchor requirement, never absolute long.
List those product IDs in relative_requirement_ids; use [] for absolute requests.
Missing anchor length cannot prove it met. Search enforces the hard condition;
Relation still compares full similarity including length. No facet is excluded.
No extra audit, correction, search, image or ownership call is introduced here.
"""


@_preserve_function('application_rules', 'fashion_recommendation_v2.search.requirements_v40')
def application_rules_v40():
    from fashion_recommendation_v2.search.requirements import application_rules_v35 as previous
    return {**previous(), 'target_product_details':
        'explicit user garment identity/construction/length: hard; fit degree/feel: soft unless explicitly non-negotiable; polarity independent',
        'explicit_user_color_default': 'hard',
        'fit_degree_default': 'soft; explicit non-negotiable fit is hard'}


# ---- requirements_v45 ----
"""v45 preserves classification, provenance and routing; clarifies product identity."""
PREVIOUS_SEMANTICS = SEMANTICS_v40
application_rules_v45 = application_rules_v40
prepare_structure_v45 = prepare_structure_v40
finalize_conditions_v45 = finalize_conditions_v40
from fashion_recommendation_v2.search.product_identity import PRODUCT_IDENTITY_RULES as PRODUCT_IDENTITY_RULES_v45

SEMANTICS_v45 = PREVIOUS_SEMANTICS + '\n' + PRODUCT_IDENTITY_RULES_v45


# ---- requirements_v46 ----
"""v46 target-only compatibility and source-preserving requirements assembly."""
application_rules_v46 = application_rules_v45
previous_structure = prepare_structure_v37
previous_finalize_v46 = finalize_conditions_v37
from fashion_recommendation_v2.search.requirement_sources import compatibility
from fashion_recommendation_v2.search.requirement_sources import validate_source_meaning
from fashion_recommendation_v2.search.requirement_sources import source_rules


@_preserve_function('prepare_structure', 'fashion_recommendation_v2.search.requirements_v46')
def prepare_structure_v46(source, output):
    if compatibility(source):
        # Reject an invalid proposal intact; never hide its anchor rows in a rewritten response.
        for condition in output.conditions:
            if condition.role == 'anchor' or condition.source == 'reference':
                raise ValueError(f'{condition.requirement_id}: compatibility anchor facts are context, not product conditions.')
    structure, conditions, derived = previous_structure(source, output)
    try:
        validate_source_meaning(source, conditions, quote_rules=source_rules(source))
    except ValueError as exc:
        exc.code_derived = derived
        raise
    return structure, conditions, derived


@_preserve_function('finalize_conditions', 'fashion_recommendation_v2.search.requirements_v46')
def finalize_conditions_v46(source, structure, conditions, output):
    validate_source_meaning(source, conditions, quote_rules=source_rules(source))
    return previous_finalize_v46(source, structure, conditions, output)


SEMANTICS_v46 = """
Structure product conditions and relationship clauses in separate inventories.
Product conditions preserve source/role/polarity, exact quote, attribute/value/OR
types. Only use projected user_query and resolved Stylist context. Never revive
omitted clauses from original-only fields. Code attaches Stylist entries; do not
duplicate them. New user intent comes from the actual current request, not expanded
reference prose. Reference facts are soft, role target when used for similarity.
For compatibility, do not emit any anchor product condition. Preserve the confirmed
relationship separately; anchor facts remain in existing item/observation context
for Relation. Only target conditions enter product search and evaluation.
Source means where the CONDITION originated, not which agent relayed a sentence.
Follow SOURCE_DEFINITIONS to distinguish actual user requests, inherited similarity
facts and resolved Stylist proposals. Membership in user_query alone is never proof
of user origin. When the user explicitly specifies ivory/relaxed fit, keep source=user;
when Stylist proposes them, reuse its originals once, without sentence-derived copies.
Quotation membership and source meaning are independent checks. Original-only omitted
conditions remain omitted, even if they are valid actual user words.
Use English fashion values but retain original quotations. Put permitted target
types in one OR list; keep negatives separate and ambiguous two-piece ambiguous.
Do not infer menswear from 'less feminine'. Apply the supplied audience policy.

relation_conditions must preserve the supplied relation_intent exactly. Never
select a new anchor, change its rank/ID/category or relationship type. Quote only
the relationship clause from searchable user_query, including composed/expanded wording.
The relation clause quote need not occur in original_user_query. Keep intent.source_text
and every confirmed anchor field unchanged; this exception never reclassifies Stylist
or anchor observations as user product conditions.
Its target is search_target; it has no hard/soft or search/item label.
No supplied intent means no relationship clause; do not guess an unresolved anchor.

Classify every target product ID and relationship ID exactly once in assignments.
Relationship clauses and inherited reference similarity facts belong to relation.
Explicit user product requests and resolved Stylist preferences belong to ranking.
Ownership is independent of eligibility: hard products remain Search admission
constraints; only ranking-owned soft products contribute to Ranking R.

Product type, excluded type and explicit garment identity/construction/length are
hard. For compatibility/similarity, additionally specified product conditions are
hard unless the user clearly allows compromise or states an optional preference.
Polite '~였으면 좋겠다' alone does not soften a constraint. '편한 분위기면 좋겠어'
is a negotiable style preference, but '반드시 편한 스타일' is mandatory.
Inherited reference facts are never promoted to hard. Unrestricted conditions
remain unrestricted. With no relation request, preserve normal hard/soft rules:
mandatory brand/gender/price and garment identity versus negotiable styling.
Explicit current-user color requests default to hard, like product type and garment
length. Fit degree or wearing-feel preferences default to soft: “너무 달라붙지 않는”
and “너무 타이트하지 않은” are soft/item. This takes precedence over treating an
explicit garment shape or a negative expression as hard, including compatibility
requests. Only an explicit non-negotiable statement such as “반드시”, “절대”, or
“해당하면 제외” makes that fit preference hard. Polarity and kind are independent:
negative tight-fitting and positive not-too-tight preserve the same preference.
Never remove negation, change source_text/value/OR types, or broaden this exception
to garment construction/length. Reference and preserved Stylist source rules remain.
Example: “검정 롱스커트 찾아줘. 허리 밴딩이고 너무 달라붙지 않는 걸로.”:
skirt/color black/long length/elastic waistband are hard; not-too-tight fit is soft.
Pattern preferences are not automatically hard merely because they describe a product.
When the user supplies two nested conditions describing the
same facet, classify the broader condition as hard and its narrower refinement
as soft. Preserve both condition IDs, values, types, sources and quotations;
do not merge them or invent an additional condition. This broad/narrow rule takes
precedence over the general product-condition hard default for such pairs.
Example: '꽃무늬 드레스 ... 잔꽃무늬였으면 좋겠고, 스커트 길이는 길었으면 좋겠어':
'꽃무늬' (floral) is the broad hard pattern; '잔꽃무늬' (small floral) is the
narrow soft pattern preference. The long skirt length is a separate facet and
remains hard. Do not treat unrelated conditions or alternatives in an OR list as
a broad/narrow pair, or promote inherited reference/Stylist facts through this rule.
Apply supplied APPLICATION_RULES for scope. Do not change facts while classifying.
'Similar but longer' retains a relative-to-anchor requirement, never absolute long.
List those product IDs in relative_requirement_ids; use [] for absolute requests.
Missing anchor length cannot prove it met. Search enforces the hard condition;
Relation still compares full similarity including length. No facet is excluded.
No extra audit, correction, search, image or ownership call is introduced here.
"""

from fashion_recommendation_v2.search.product_identity import PRODUCT_IDENTITY_RULES as PRODUCT_IDENTITY_RULES_v46
SEMANTICS_v46 += "\n" + PRODUCT_IDENTITY_RULES_v46


# ---- requirements_v47 ----
"""v47 binding: preserve compatible Stylist refinements and searchable preferences."""
from functools import partial
prepare_structure_v47 = prepare_structure_v46
previous_rules_v47 = application_rules_v45
bind_products = finalize_conditions_v30
bind_routing = finalize_conditions_v37
from fashion_recommendation_v2.search.stylist_policy import SEARCH_ATTRIBUTES
from fashion_recommendation_v2.search.stylist_policy import expected_pairs
from fashion_recommendation_v2.search.stylist_policy import validate_comparisons
from fashion_recommendation_v2.search.stylist_policy import validate_resolved_stylist
from fashion_recommendation_v2.search.stylist_policy import validate_scopes


@_preserve_function('application_rules', 'fashion_recommendation_v2.search.requirements_v47')
def application_rules_v47():
    return {**previous_rules_v47(), 'hard_search_attributes': sorted(SEARCH_ATTRIBUTES),
            'soft_search_attributes': sorted(SEARCH_ATTRIBUTES),
            'target_product_type': 'determine source from evidence and kind from meaning; reference and Stylist stay soft',
            'independent_product_type_source_kind': True,
            'stylist_precedence': 'only actual conflict, not same dimension; retain compatible refinements'}


@_preserve_function('finalize_conditions', 'fashion_recommendation_v2.search.requirements_v47')
def finalize_conditions_v47(source, structure, conditions, output, *, rules=None, search_attributes=SEARCH_ATTRIBUTES):
    hard_ids = {r.requirement_id for r in output.user_applications if r.kind == 'hard'}
    stylist = [c for c in conditions if c.source == 'stylist' and c.role == 'target']
    users = [c for c in conditions if c.source == 'user' and c.requirement_id in hard_ids]
    conflicts = validate_comparisons(output.stylist_user_comparisons, expected_pairs(stylist, users))
    # The original response is never changed. This is a typed code projection into
    # the unchanged product/routing binder, with an explicit new precedence policy.
    from fashion_recommendation_v2.schemas.search.requirements.search_requirements import classification_schema_v37 as classification_schema
    projected = classification_schema(conditions, relation_conditions=structure.relation_conditions).model_validate(
        output.model_dump(exclude={'stylist_user_comparisons'}))
    result, derived = bind_routing(source, structure, conditions, projected,
        product_binder=partial(bind_products, rules=application_rules_v47() if rules is None else rules, stylist_conflicts=conflicts))
    from fashion_recommendation_v2.schemas.stylist_condition_policy import StylistPolicyV47
    by_id = {c.requirement_id: c.polarity for c in conditions}
    result.condition_routing_v37.stylist_policy_v47 = StylistPolicyV47(
        comparisons=[r.model_copy(deep=True) for r in output.stylist_user_comparisons],
        polarities={r.requirement_id: by_id.get(r.requirement_id, 'positive') for r in result.requirements})
    validate_resolved_stylist(source, result)
    validate_scopes(result, search_attributes=search_attributes)
    derived['condition_routing_v37'] = result.condition_routing_v37.model_dump(mode='json')
    derived['resolved_requirements'] = result.model_dump(mode='json')
    return result, derived


# Standalone semantic contract: no runtime rewriting of historical prompts.
SEMANTICS = """
Structure product conditions and relationship clauses in separate inventories.
Product conditions preserve source/role/polarity, exact quote, attribute/value/OR
types. Only use projected user_query and resolved Stylist context. Never revive
omitted clauses from original-only fields. Code attaches Stylist entries; do not
duplicate them. New user intent comes from the actual current request, not expanded
reference prose. Reference facts are soft, role target when used for similarity.
For compatibility, do not emit any anchor product condition. Preserve the confirmed
relationship separately; anchor facts remain in existing item/observation context
for Relation. Only target conditions enter product search and evaluation.
Source means where the CONDITION originated, not which agent relayed a sentence.
Follow SOURCE_DEFINITIONS to distinguish actual user requests, inherited similarity
facts and resolved Stylist proposals. Membership in user_query alone is never proof
of user origin. When the user explicitly specifies ivory/relaxed fit, keep source=user;
when Stylist proposes them, reuse its originals once, without sentence-derived copies.
Quotation membership and source meaning are independent checks. Original-only omitted
conditions remain omitted, even if they are valid actual user words.
Use English fashion values but retain original quotations. Put permitted target
types in one OR list; keep negatives separate and ambiguous two-piece ambiguous.
Do not infer menswear from 'less feminine'. Apply the supplied audience policy.

relation_conditions must preserve the supplied relation_intent exactly. Never
select a new anchor, change its rank/ID/category or relationship type. Quote only
the relationship clause from searchable user_query, including composed/expanded wording.
The relation clause quote need not occur in original_user_query. Keep intent.source_text
and every confirmed anchor field unchanged; this exception never reclassifies Stylist
or anchor observations as user product conditions.
Its target is search_target; it has no hard/soft or search/item label.
No supplied intent means no relationship clause; do not guess an unresolved anchor.

Classify every target product ID and relationship ID exactly once in assignments.
Relationship clauses and inherited reference similarity facts belong to relation.
Explicit user product requests and resolved Stylist preferences belong to ranking.
Ownership is independent of eligibility: hard products remain Search admission
constraints; only ranking-owned soft products contribute to Ranking R.

Product type does not force source=user or kind=hard. Determine its source from
SOURCE_DEFINITIONS, regardless of whether it is broad, specific, or an additional
condition. A reference product_type is allowed with supplied supporting facts and
remains soft; it need not refine a user product_type. User product-type conditions
follow the ordinary mandatory/optional meaning rules. Preserved Stylist types remain
soft. Excluded type and explicit garment identity/construction/length remain hard. For compatibility/similarity, additionally specified product conditions are
hard unless the user clearly allows compromise or states an optional preference.
Polite '~였으면 좋겠다' alone does not soften a constraint. '편한 분위기면 좋겠어'
is a negotiable style preference, but '반드시 편한 스타일' is mandatory.
Inherited reference facts are never promoted to hard. Unrestricted conditions
remain unrestricted. With no relation request, preserve normal hard/soft rules:
mandatory brand/gender/price and garment identity versus negotiable styling.
Explicit current-user color requests and garment length default to hard. Fit degree or wearing-feel preferences default to soft: “너무 달라붙지 않는”
and “너무 타이트하지 않은” are soft/item. This takes precedence over treating an
explicit garment shape or a negative expression as hard, including compatibility
requests. Only an explicit non-negotiable statement such as “반드시”, “절대”, or
“해당하면 제외” makes that fit preference hard. Polarity and kind are independent:
negative tight-fitting and positive not-too-tight preserve the same preference.
Never remove negation, change source_text/value/OR types, or broaden this exception
to garment construction/length. Reference and preserved Stylist source rules remain.
Example: “검정 롱스커트 찾아줘. 허리 밴딩이고 너무 달라붙지 않는 걸로.”:
skirt/color black/long length/elastic waistband are hard; not-too-tight fit is soft.
Pattern preferences are not automatically hard merely because they describe a product.
When the user supplies two nested conditions describing the
same facet, classify the broader condition as hard and its narrower refinement
as soft. Preserve both condition IDs, values, types, sources and quotations;
do not merge them or invent an additional condition. This broad/narrow rule takes
precedence over the general product-condition hard default for such pairs.
Example: '꽃무늬 드레스 ... 잔꽃무늬였으면 좋겠고, 스커트 길이는 길었으면 좋겠어':
'꽃무늬' (floral) is the broad hard pattern; '잔꽃무늬' (small floral) is the
narrow soft pattern preference. The long skirt length is a separate facet and
remains hard. Do not treat unrelated conditions or alternatives in an OR list as
a broad/narrow pair, or promote inherited reference/Stylist facts through this rule.
Apply supplied APPLICATION_RULES for scope. Do not change facts while classifying.
'Similar but longer' retains a relative-to-anchor requirement, never absolute long.
List those product IDs in relative_requirement_ids; use [] for absolute requests.
Missing anchor length cannot prove it met. Search enforces the hard condition;
Relation still compares full similarity including length. No facet is excluded.
No extra audit, correction, search, image or ownership call is introduced here.
"""

from fashion_recommendation_v2.search.product_identity import PRODUCT_IDENTITY_RULES
from fashion_recommendation_v2.search.stylist_policy import SEMANTICS as STYLIST_SEMANTICS
SEMANTICS += "\n" + PRODUCT_IDENTITY_RULES + "\n" + STYLIST_SEMANTICS


# ---- requirements_v48 ----
"""v48 shares v47 assembly; audience selection is versioned in audience_policy."""
prepare_structure_v48 = prepare_structure_v47
finalize_conditions_v48 = finalize_conditions_v47
application_rules_v48 = application_rules_v47


# ---- requirements_v49 ----
"""v49 keeps v48 provenance, audience, classification and immutable projections."""
previous_finalize = finalize_conditions_v48
application_rules_v49 = application_rules_v48
previous_prepare_v49 = prepare_structure_v48
from fashion_recommendation_v2.schemas.search.requirements.search_requirements import check_detail_shapes


@_preserve_function('prepare_structure', 'fashion_recommendation_v2.search.requirements_v49')
def prepare_structure_v49(source, structure):
    check_detail_shapes(structure.model_dump(mode='json'))
    return previous_prepare_v49(source, structure)


@_preserve_function('finalize_conditions', 'fashion_recommendation_v2.search.requirements_v49')
def finalize_conditions_v49(*args, **kwargs):
    from fashion_recommendation_v2.schemas.search.requirements.search_requirements import ResolvedRequirementsV49
    result, derived = previous_finalize(*args, **kwargs)
    return ResolvedRequirementsV49.model_validate(result.model_dump()), derived


# ---- requirements_v50 ----
"""v50 search scopes; reuse the existing immutable source and routing binder."""
prepare_structure_v50 = prepare_structure_v49
previous_rules = application_rules_v47
bind = finalize_conditions_v47
from fashion_recommendation_v2.search.stylist_policy import SEARCH_ATTRIBUTES_V50



@_preserve_function('application_rules', 'fashion_recommendation_v2.search.requirements_v50')
def application_rules_v50():
    return {**previous_rules(), 'hard_search_attributes': sorted(SEARCH_ATTRIBUTES_V50),
            'soft_search_attributes': sorted(SEARCH_ATTRIBUTES_V50)}


@_preserve_function('finalize_conditions', 'fashion_recommendation_v2.search.requirements_v50')
def finalize_conditions_v50(source, structure, conditions, output):
    from fashion_recommendation_v2.schemas.search.requirements.search_requirements import ResolvedRequirementsV49
    result, derived = bind(source, structure, conditions, output, rules=application_rules_v50(),
                           search_attributes=SEARCH_ATTRIBUTES_V50)
    return ResolvedRequirementsV49.model_validate(result.model_dump()), derived


# ---- requirements_v54 ----
"""v54 reference selection guidance and nonblocking omission diagnostics."""
application_rules = application_rules_v50
finalize_conditions = finalize_conditions_v50
previous_prepare = prepare_structure_v50
previous_sources = source_contract_v35


REFERENCE_SELECTION = """
Similarity: similarity_reference.attributes에 근거가 있는 특징 중 유사한 상품을
찾는 데 유용한 특징을 선별해 source=reference, role=target 조건으로 구성한다.
기존 soft 및 scope 정책을 따른다. 모든 특징을 복사하거나 브랜드·사이즈까지
동일하게 요구하지 않는다. 조건으로 사용하지 않았다면 reference_nonuse_reason에
짧은 이유를 남긴다(사용자 조건과 충돌, 제공된 특징이 불확실,
같은 의미가 이미 사용자 조건에 반영됨 등).
Compatibility: 조합 대상 앵커의 특징을 검색 대상의 상품 조건으로 복사하지 않는다.
앵커 정보는 조합 판단의 문맥으로 보존한다.
reference 미사용 사유가 없거나 불충분해도 경고만 기록하며 실행을 계속한다.
이 경고만으로 추가 LLM 교정 호출이나 최종 실패를 만들지 않는다.
존재하지 않는 앵커 특징을 인용하는 것은 여전히 근거 검증 오류다.
"""


@_preserve_function('source_contract', 'fashion_recommendation_v2.search.requirements_v54')
def source_contract(source):
    contract = previous_sources(source)
    contract['operations']['composition'] = (
        'effective_query combines source segments; only retained actual user words '
        'can be source=user. Code attaches structured Stylist conditions as target/soft; '
        'do not extract sentence copies. ' + REFERENCE_SELECTION)
    return contract


@_preserve_function('prepare_structure', 'fashion_recommendation_v2.search.requirements_v54')
def prepare_structure(source, output):
    structure, conditions, derived = previous_prepare(source, output)
    reference = source.similarity_reference
    intent = source.relation_intent
    if reference is not None and (intent is None or intent.relation_type == 'similarity'):
        if not any(c.source == 'reference' and c.role == 'target' for c in conditions):
            # Never judge prose adequacy with another model call or hide the raw response.
            reason = output.reference_nonuse_reason
            derived.setdefault('warnings', []).append(dict(
                code='reference_conditions_missing', reason=reason,
                reason_status='provided_unassessed' if reason and reason.strip() else 'missing',
                message='No reference target conditions selected; omission reason is advisory.',
                action='record_only'))
    return structure, conditions, derived
