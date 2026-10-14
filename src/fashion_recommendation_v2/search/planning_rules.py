"""search.planning_rules: definitions relocated without semantic changes."""
from __future__ import annotations
from fashion_recommendation_v2.module_compat import import_module as _role_module
from fashion_recommendation_v2.search.policy import CORE_ATTRIBUTES
import json
import re
from fashion_recommendation_v2.search.policy import search_policy
import unicodedata


def execution_evidence_contract(plan):
    """One code-owned set of source documents and match modes for v25 plan review."""
    return {
        'query': {'source_path': 'execution_strings.query', 'text': plan.query,
                  'match': 'contiguous'},
        'category': {'source_path': 'execution_strings.category',
                     'text': json.dumps(plan.category_ids, ensure_ascii=False),
                     'match': 'selected_id', 'allowed_values': list(plan.category_ids)},
        'filter': {'source_path': 'execution_strings.filter',
                   'text': json.dumps(plan.aspect_filters, ensure_ascii=False),
                   'match': 'complete_fragment', 'allowed_values': [json.dumps({k: v}, ensure_ascii=False)[1:-1]
                       for k, v in plan.aspect_filters.items()]},
    }


def validate_execution_sources(plan, usages):
    contract = execution_evidence_contract(plan)
    for usage in usages:
        rule = contract[usage.location]
        valid = bool(usage.evidence.strip()) and usage.evidence in rule['text']
        if rule['match'] == 'selected_id':
            valid = valid and usage.evidence in rule['allowed_values']
        elif rule['match'] == 'complete_fragment':
            valid = valid and any(fragment in usage.evidence for fragment in rule['allowed_values'])
        if not valid:
            raise ValueError(f'Invalid evidence for {rule["source_path"]}: {usage.evidence!r}; match={rule["match"]}')

def normalized_type(value):
    return ' '.join(re.findall(r"[^\W_]+", unicodedata.normalize('NFKC', value).casefold()))


def validate_specific_product_types(plan, requirements, usages, categories, *, singular=False, semantic_supported=()):
    """Do not certify a concrete hard type solely from its broad ancestor category."""
    normalize = singular_type if singular else normalized_type
    by_id = {c['category_id']: c for c in categories}
    for r in requirements.requirements:
        if r.kind != 'hard' or r.attribute not in {'product_type', 'category', 'type'}:
            continue
        values = r.value if isinstance(r.value, list) else [r.value]
        values = [normalize(v) for v in values if isinstance(v, str)]
        evidence = [u for u in usages if u.requirement_id == r.requirement_id]
        supported = any((u.requirement_id, u.location, u.evidence) in semantic_supported for u in evidence)
        for usage in evidence:
            if usage.location == 'category':
                entry = by_id.get(usage.evidence, {})
                leaf = (entry.get('category_path') or entry.get('category_name', '')).split('|')[-1]
                supported |= normalize(leaf) in values
            else:
                # Retain the full canonical phrase, including its defining qualifier.
                # Space/hyphen variants like trench coat/trenchcoat are equivalent.
                text = normalize(usage.evidence)
                supported |= any(re.search(r'(?<!\w)' + re.escape(v) + r'(?!\w)', text)
                    or text.replace(' ', '') == v.replace(' ', '') for v in values)
        if not supported:
            raise ValueError(f'Hard product type {r.requirement_id} ({values}) needs specific query/filter/leaf evidence; a parent category is insufficient.')


def singular_type(value):
    """Conservative regular morphology, not a product synonym/category dictionary."""
    words = normalized_type(value).split()
    def singular(word):
        if word.endswith(('sses', 'shes', 'ches', 'xes', 'zzes')):
            return word[:-2]
        if len(word) > 4 and word.endswith('ies'):
            return word[:-3] + 'y'
        if len(word) > 3 and word.endswith('s') and not word.endswith(('ss', 'us', 'is')):
            return word[:-1]
        return word
    return ' '.join(singular(word) for word in words)


def validate_v8_query_usage(requirements, usages, *, max_soft=1):
    query_ids = {u.requirement_id for u in usages if u.location == 'query'}
    hard = {r.requirement_id for r in requirements.requirements if r.kind == 'hard' and r.attribute != 'price'}
    if hard - query_ids:
        raise ValueError(f'Hard conditions missing from query: {sorted(hard-query_ids)}')
    item_only = {r.requirement_id for r in requirements.requirements if r.evaluation_scope == 'item' and r.attribute != 'price'}
    if item_only & query_ids:
        raise ValueError('Item-only preferences must not be forced into query terms.')
    soft_search = {r.requirement_id for r in requirements.requirements if r.kind == 'soft' and r.evaluation_scope == 'search'}
    if len(query_ids & soft_search) > max_soft:
        raise ValueError('Choose at most one soft-search condition per query; do not accumulate soft terms.' if max_soft == 1 else f'Choose at most {max_soft} soft-search conditions per query.')


def requirement_alternatives(requirements):
    """All explicit OR lists, including stylist detail alternatives; never price."""
    from fashion_recommendation_v2.schemas.stylist import StylistDetailValue_base as StylistDetailValue
    result = []
    for r in requirements.requirements:
        if r.unrestricted:
            continue
        values = r.value if isinstance(r.value, list) else r.value.values if isinstance(r.value, StylistDetailValue) else []
        if len(values) > 1:
            result.extend((r.requirement_id, value) for value in values)
    return result


def core_attributes(version='v16'):
    if version in {'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
        from fashion_recommendation_v2.search.stylist_policy import SEARCH_ATTRIBUTES_V50
        return set(SEARCH_ATTRIBUTES_V50)
    if version in {'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
        from fashion_recommendation_v2.search.stylist_policy import SEARCH_ATTRIBUTES
        return set(SEARCH_ATTRIBUTES)
    return CORE_ATTRIBUTES | ({'brand'} if search_policy(version).enabled('per_item_evidence_contract') else set())


def validate_marketplace_query(query):
    """Reject untranslated Korean before category lookup, for initial AND revised plans."""
    query = unicodedata.normalize('NFKC', query)
    if re.search(r'[\u1100-\u11ff\u3130-\u318f\ua960-\ua97f\uac00-\ud7ff]', query):
        raise ValueError('query_language: Translate the query to natural marketplace English before lookup. '
            'Use the canonical English product type from requirements (dress, skirt set, trench coat, etc.); '
            'do not change the original user/Stylist requirements.')


def retrieval_contract(requirements, version='v16'):
    """The generator, reviewer and recovery all receive the same code-owned contract."""
    return dict(query_language='marketplace English',
        required_retrieval_ids=sorted(required_retrieval_ids(requirements, version)),
        mandatory_item_ids=[r.requirement_id for r in requirements.requirements if r.kind == 'hard'],
        max_additional_restrictions=search_policy(version).max_additional_restrictions,
        **({'min_additional_restrictions': 1,
            'minimum_exception': 'Zero only when no eligible additional original query condition remains, including conditions already represented by category/filter.'} if search_policy(version).enabled('exact_execution_evidence') else {}),
        core_attributes=sorted(core_attributes(version)),
        product_type_values=[r.value for r in requirements.requirements if r.attribute == 'product_type' and r.kind == 'hard'],
        audience_rule=('Every branch must preserve the context/user hard gender constraint; do not diversify into the opposite audience.'
            if getattr(requirements, 'audience_policy_v1', None) and requirements.audience_policy_v1.target_gender else
            'A men/women branch is valid unless it contradicts explicit user gender; quotas apply to the pool.'))


def plan_signature(plan):
    """Ignore word order, punctuation and repeated tokens when detecting duplicate directions."""
    import json
    return (frozenset(singular_type(plan.query).split()), tuple(plan.category_ids),
        json.dumps(plan.aspect_filters, sort_keys=True, ensure_ascii=False))


def required_retrieval_ids(requirements, version='v16'):
    return {r.requirement_id for r in requirements.requirements
        if r.kind == 'hard' and (r.attribute in core_attributes(version) or r.attribute == 'price')
        and (version not in {'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'} or r.evaluation_scope == 'search' or r.attribute == 'price')}


def additional_restrictions(requirements, usages, version='v16'):
    """Count nested expressions once, without merging unrelated IDs with broad evidence."""
    from fashion_recommendation_v2.schemas.stylist import StylistDetailValue_base as StylistDetailValue
    by_id = {r.requirement_id: r for r in requirements.requirements}
    groups = []
    for rid in dict.fromkeys(u.requirement_id for u in usages if u.location == 'query'):
        r = by_id[rid]
        if (r.requirement_id in required_retrieval_ids(requirements, version) if version in {'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'} else
                r.attribute in CORE_ATTRIBUTES | {'price'} or (search_policy(version).enabled('per_item_evidence_contract') and r.attribute == 'brand' and r.kind == 'hard')):
            continue
        values = r.value.values if isinstance(r.value, StylistDetailValue) else r.value if isinstance(r.value, list) else [r.value]
        dimension = (r.attribute, r.value.key if isinstance(r.value, StylistDetailValue) else None)
        texts = [singular_type(u.evidence) for u in usages if u.requirement_id == rid and u.location == 'query']
        terms = {singular_type(v) for v in values if isinstance(v, str) and any(
            re.search(r'(?<!\w)' + re.escape(singular_type(v)) + r'(?!\w)', text) for text in texts)}
        # A single specific expression can support both floral and small floral.
        # Require canonical terms and the same dimension; quoting the whole query
        # for festival + small floral cannot collapse those independent conditions.
        term = next(iter(terms)) if len(terms) == 1 else None
        for group in groups:
            old = group['term']
            if term and old and dimension == group['dimension'] and (
                    re.search(r'(?<!\w)' + re.escape(term) + r'(?!\w)', old)
                    or re.search(r'(?<!\w)' + re.escape(old) + r'(?!\w)', term)):
                group['ids'].append(rid)
                group['term'] = max((old, term), key=len)
                break
        else:
            groups.append(dict(dimension=dimension, term=term, ids=[rid]))
    return [group['ids'] for group in groups]


def alternative_targets(requirements, usages):
    """Only validated execution evidence advances search coverage, never model target IDs."""
    options = requirement_alternatives(requirements)
    return {(k, v) for k, v in options if any(u.requirement_id == k
        and query_covers_alternative(u.evidence, v) for u in usages)}


def strategy_trigger_contract(context):
    """V24 choices derived from code evidence, shared by schema and execution."""
    from fashion_recommendation_v2.search.planning import evaluation_limited
    if evaluation_limited(context):
        return {}
    metrics = context.get('code_metrics', {})
    causes = set(context.get('code_diagnoses', []))
    remaining = metrics.get('search_attempts_remaining', context.get('attempts_remaining_after_current'))
    if remaining is not None and remaining <= 0:
        return {}

    def observed(cause):
        key = cause + '_count'
        return metrics[key] > 0 if key in metrics else cause in causes

    changes = ['new_direction', 'synonym_replacement', 'broaden_by_removal']
    allowed = {}
    if context.get('unused_requirements_after_current') or context.get('unsearched_hard_alternatives'):
        allowed['unused_requirements'] = changes
    distribution = context.get('gender_distribution_after', {})
    missing_gender = context.get('gender_diversity_required') and any(
        distribution.get(g, 0) < context.get('gender_minimum_share', .05) for g in ('men', 'women'))
    if missing_gender or context.get('code_preferred_audience') or context.get('code_required_audience'):
        allowed['gender_diversity'] = ['new_direction']
    relevance = observed('relevance_rejection')
    thumbnail = observed('thumbnail_rejection')
    if relevance:
        allowed['irrelevant_results'] = changes
        allowed['too_broad'] = changes
    requirements = context.get('resolved_requirements', {}).get('requirements', [])
    failures = context.get('hard_failure_counts', {})
    if relevance and any(r['attribute'] in {'product_type', 'gender', 'category'}
                         and failures.get(r['requirement_id'], 0) > 0 for r in requirements):
        allowed['wrong_gender_or_category'] = ['new_direction', 'synonym_replacement']
    after = metrics.get('pool_after', context.get('candidate_count_after'))
    target = context.get('target_candidate_count')
    shortage = after is not None and target is not None and after < target
    retrieval = 'retrieval_shortage' in causes
    errors_only = (observed('evaluation_error') or context.get('image_fetch_error_count', 0)) and not (
        retrieval or relevance or thumbnail or 'duplicate_excess' in causes)
    if retrieval or thumbnail or 'duplicate_excess' in causes or (shortage and not errors_only):
        # A full result page with poor thumbnails does not justify broadening.
        # Use a new supply direction, preserving every frozen hard condition.
        allowed['too_few_results'] = changes if retrieval else ['new_direction']
    return allowed


class StrategyChoiceError(ValueError):
    def __init__(self, feedback):
        self.feedback = feedback
        super().__init__(json.dumps(feedback, ensure_ascii=False))


def strategy_choice_feedback(context, field, rejected_value, *, trigger=None):
    allowed = strategy_trigger_contract(context)
    metrics = context.get('code_metrics', {})
    relevance = metrics.get('relevance_rejection_count')
    thumbnail = metrics.get('thumbnail_rejection_count')
    relevance_text = f'{relevance}개' if relevance is not None else '미제공'
    thumbnail_text = f'{thumbnail}개' if thumbnail is not None else '미제공'
    message = f'관련성 탈락은 {relevance_text}, 사진 품질 탈락은 {thumbnail_text}다. '
    message += f'{field}={rejected_value!r}는 현재 진단에서 허용되지 않는다. '
    if thumbnail and not relevance:
        message += ('사진 품질 개선은 trigger=too_few_results, intent.change_type=new_direction으로 '
                    '다른 상품·사진을 찾는 검색 방향을 제안하라. ')
    message += '검색어만 변경하지 말고 지적된 필드를 반드시 수정하라. 기존 hard/soft 조건과 검색 예산은 유지하라.'
    choices = list(allowed) if field == 'revision.trigger' else allowed.get(trigger, sorted({v for values in allowed.values() for v in values}))
    feedback = dict(code='unsupported_strategy_choice', field=field, rejected_value=rejected_value,
        observed_counts={key: metrics.get(key) for key in (
            'relevance_rejection_count', 'thumbnail_rejection_count', 'evaluation_error_count',
            'retrieved_count', 'pool_after', 'search_attempts_remaining')},
        code_diagnoses=context.get('code_diagnoses', []), allowed_triggers=list(allowed),
        allowed_change_types=allowed, required_changes=[dict(field=field, forbidden_value=rejected_value,
            allowed_values=choices)], message=message)
    return feedback


def validate_strategy_choice(proposal, context):
    allowed = strategy_trigger_contract(context)
    trigger = proposal.revision.trigger
    if trigger not in allowed:
        raise StrategyChoiceError(strategy_choice_feedback(context, 'revision.trigger', trigger))
    if proposal.intent.change_type not in allowed[trigger]:
        raise StrategyChoiceError(strategy_choice_feedback(context, 'intent.change_type',
            proposal.intent.change_type, trigger=trigger))
    # Repairs must change the field identified by code, not just their query.
    for change in context.get('validation_feedback', {}).get('required_changes', []):
        value = {'revision.trigger': trigger, 'intent.change_type': proposal.intent.change_type}.get(change['field'])
        if value is not None and (value == change['forbidden_value'] or value not in change['allowed_values']):
            raise StrategyChoiceError(strategy_choice_feedback(context, change['field'], value, trigger=trigger))


def additional_condition_candidates(requirements, usages, *, version=None):
    from fashion_recommendation_v2.search.policy import CORE_ATTRIBUTES
    represented_elsewhere = {u.requirement_id for u in usages if u.location != 'query'}
    if version in {'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
        required = required_retrieval_ids(requirements, version)
        routing = getattr(requirements, 'condition_routing_v37', None)
        policy = routing.stylist_policy_v47 if routing else None
        polarities = policy.polarities if policy else {}
        return [r for r in requirements.requirements if r.requirement_id not in required | represented_elsewhere
                and r.attribute not in {'price', 'avoid_product_type'} and not r.unrestricted
                and polarities.get(r.requirement_id, 'positive') == 'positive'
                and not (r.kind == 'soft' and r.evaluation_scope == 'item')]
    eligible = [r for r in requirements.requirements
        if r.attribute not in CORE_ATTRIBUTES | {'price', 'avoid_product_type'}
        and not (r.attribute == 'brand' and r.kind == 'hard')
        and not r.unrestricted and not (r.kind == 'soft' and r.evaluation_scope == 'item')
        and r.requirement_id not in represented_elsewhere]
    return eligible


def additional_condition_bounds(requirements, usages, *, version=None):
    return (1 if additional_condition_candidates(requirements, usages, version=version) else 0), 3




def planning_constraints(requirements, usages=(), *, version=None):
    """Use the SAME eligibility test as the final minimum, before generation."""
    represented = {u.requirement_id for u in usages if u.location != 'query'}
    candidates = additional_condition_candidates(requirements, usages, version=version)
    minimum, maximum = additional_condition_bounds(requirements, usages, version=version)
    return {'required_retrieval_ids': sorted(required_retrieval_ids(requirements, version or 'v24')),
        'additional_condition_candidates': [r.model_dump(mode='json') for r in candidates],
        'min_additional_query_conditions': minimum, 'max_additional_query_conditions': maximum,
        'represented_by_filter_or_category': sorted(represented),
        'allowed_model_filters': ['Condition', 'Size'],
        'filter_rule': 'Only verified marketplace options; code owns prices.',
        'repair_instruction': 'Reflect at least the minimum from the listed candidates in query, '
            'or represent them with verified filter/category evidence. Do not merely swap core brand/audience.'}


def effective_category_scope(plan, category_evidence):
    """Account for eBay aspect_filter binding to category_ids[0]."""
    ids = plan.category_ids
    if not ids:
        return 'all'
    if any(key not in {'Condition', 'PriceMin', 'PriceMax'} for key in plan.aspect_filters):
        ids = ids[:1]
    by_id = {entry['category_id']: entry for entry in category_evidence}
    scopes = {by_id.get(key, {}).get('gender_scope', 'unknown') for key in ids}
    if 'unknown' in scopes:
        return 'unknown'
    if 'all' in scopes or {'men', 'women'} <= scopes:
        return 'all'
    return next(iter(scopes))


def changed_plan_dimensions(current, final):
    """Exact structural differences after all execution-time resolution."""
    return [key for key, old, new in (
        ('query', current.query, final.query),
        ('category', current.category_ids, final.category_ids),
        ('filter', current.aspect_filters, final.aspect_filters)) if old != new]


def query_covers_alternative(query, value):
    query, value = singular_type(query), singular_type(value)
    return bool(re.search(r'(?<!\w)' + re.escape(value) + r'(?!\w)', query))


def rejection_counts(rows, version):
    """Count each rejection axis independently; one item may fail both gates."""
    rejected = [row for row in rows if row.status == 'rejected']
    if version in {'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
        return dict(
            relevance_rejection_count=sum(not row.analysis.admission_checks.hard_conditions_pass for row in rejected),
            thumbnail_rejection_count=sum(not row.analysis.admission_checks.photo_pass for row in rejected))
    return dict(
        relevance_rejection_count=sum(any(reason.startswith(('relevance_below_medium', 'hard_requirement_violated'))
                                          for reason in row.reasons) for row in rejected),
        thumbnail_rejection_count=sum(any(reason.startswith('thumbnail_gate_failed') for reason in row.reasons)
                                      for row in rejected))
