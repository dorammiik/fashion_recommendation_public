"""Role-consolidated implementation; service contracts and behavior are preserved."""
from __future__ import annotations
from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function

# ---- personalization_v11 ----
"""Frozen profile lookup, bounded item evaluation, and replayable v11 policy."""
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from copy import deepcopy as deepcopy_v11
from pathlib import Path
from threading import BoundedSemaphore
import json
from fashion_recommendation_v2.preference.interpretation_sources import fingerprint
from fashion_recommendation_v2.preference.interpretation_sources import validate_references
from fashion_recommendation_v2.schemas.preference.interpretation.preference_interpretation import PreferenceProfileV4
from fashion_recommendation_v2.schemas.preference.interpretation.preference_interpretation import InterpretationEvidence
from fashion_recommendation_v2.schemas.ranking_personalization.ranking_personalization import PreferenceAssessmentV11_v11 as PreferenceAssessmentV11
from fashion_recommendation_v2.schemas.ranking_personalization.ranking_personalization import PreferenceAssessmentInputV11_v11 as PreferenceAssessmentInputV11

from fashion_recommendation_v2.ranking.ranking_contracts import RANKING_V11_CONTRACT
from fashion_recommendation_v2.ranking.ranking_contracts import RANKING_V15_CONTRACT
MODEL = RANKING_V11_CONTRACT['default_model']
MAX_CANDIDATES = RANKING_V11_CONTRACT['max_candidates']
MAX_CALLS = RANKING_V11_CONTRACT['max_calls']
MAX_CONCURRENCY = RANKING_V11_CONTRACT['max_concurrency']
CALL_SLOTS = BoundedSemaphore(MAX_CONCURRENCY)
V15_CALL_SLOTS = BoundedSemaphore(RANKING_V15_CONTRACT['max_concurrency'])
SCORES = dict(strong_mismatch=0., mismatch=.25, neutral=.5, match=.75, strong_match=1., undetermined=None)
REASONS = dict(supports={'preference_supported'}, opposes={'preference_opposed'}, neutral={'no_clear_effect'},
    unknown={'insufficient_product_evidence'}, conflicted={'conflicting_product_evidence'},
    not_applicable={'out_of_scope', 'request_attribute_excluded', 'request_overlap_combination'})

@_preserve_class('PersonalizationError', 'fashion_recommendation_v2.ranking.personalization_v11')
class PersonalizationError(RuntimeError):
    __qualname__ = 'PersonalizationError'
    def __init__(self, message, record):
        self.record = record
        super().__init__(message)


from fashion_recommendation_v2.preference.profile_lookup import freeze_bundle
from fashion_recommendation_v2.preference.profile_lookup import FileProfileLookup
from fashion_recommendation_v2.preference.profile_lookup import ServiceProfileLookup


@_preserve_function('excluded_attributes', 'fashion_recommendation_v2.ranking.personalization_v11')
def excluded_attributes(source):
    excluded = {'size'} | {r.attribute for r in source.candidate_set.resolved_requirements.requirements if r.source == 'user'}
    if excluded & {'category', 'product_type', 'product_group', 'type'}:
        excluded.update({'category', 'product_type'})
    return sorted(excluded)


@_preserve_function('candidate_input', 'fashion_recommendation_v2.ranking.personalization_v11')
def candidate_input(source, candidate, bundle):
    item = candidate.evaluation_item or candidate.item
    evidence = {'item.title': {'text': item.title}, 'item.category_path': {'value': item.category_path}}
    for n, row in enumerate(candidate.search_analysis.attributes):
        evidence[f'search_analysis.attributes.{n}'] = dict(attribute=row.attribute,
            metadata=row.metadata.model_dump(mode='json'),
            image_observation=row.image_observation.model_dump(mode='json') if row.image_observation else None,
            metadata_image_consistency=row.metadata_image_consistency.model_dump(mode='json'))
    return PreferenceAssessmentInputV11(item_id=item.item_id, user_request=source.user_request,
        resolved_requirements=source.candidate_set.resolved_requirements.model_dump(mode='json'),
        frozen_profile=bundle['profile'], categories=bundle['categories'], evidence_index=bundle['evidence_index'],
        product_evidence=evidence, excluded_attributes=excluded_attributes(source))


@_preserve_function('validate_assessment', 'fashion_recommendation_v2.ranking.personalization_v11')
def validate_assessment_v11(value, source, *, scope_first=False):
    result = PreferenceAssessmentV11.model_validate(value)
    interpretations = {i['interpretation_id']:i for i in source.frozen_profile['interpretations']}
    ids = [a.interpretation_id for a in result.interpretation_assessments]
    if result.item_id != source.item_id or len(ids) != len(set(ids)) or set(ids) != set(interpretations):
        raise ValueError('Candidate or interpretation ID missing/duplicate/unknown')
    for a in result.interpretation_assessments:
        i = interpretations[a.interpretation_id]
        if a.reason_code not in REASONS[a.judgment]:
            raise ValueError('Judgment/reason mismatch')
        if len(a.product_evidence_refs) != len(set(a.product_evidence_refs)):
            raise ValueError('Duplicate product evidence references')
        if not set(a.product_evidence_refs) <= set(source.product_evidence):
            raise ValueError('Unknown candidate evidence reference')
        if not set(a.used_attributes) <= set(i['attributes']) or not set(a.used_detail_keys) <= set(i['detail_keys']):
            raise ValueError('Attributes/detail keys outside interpretation')
        if len(a.used_attributes) != len(set(a.used_attributes)) or len(a.used_detail_keys) != len(set(a.used_detail_keys)):
            raise ValueError('Duplicate attribute/detail key')
        overlap = set(i['attributes']) & set(source.excluded_attributes)
        if scope_first and a.reason_code == 'out_of_scope':
            pass  # Scope semantics belong to the LLM; structural checks still run below.
        elif overlap:
            reason = 'request_overlap_combination' if len(i['attributes']) > 1 else 'request_attribute_excluded'
            if a.judgment != 'not_applicable' or a.reason_code != reason:
                raise ValueError('Request-excluded claim used for preference')
        elif a.reason_code.startswith('request_'):
            raise ValueError('No code-defined request exclusion for this claim')
        if a.judgment == 'not_applicable' and (a.used_attributes or a.used_detail_keys or a.product_evidence_refs):
            raise ValueError('Not applicable must not claim used evidence/attributes')
        if a.judgment in {'supports', 'opposes', 'neutral', 'conflicted'} and (not a.product_evidence_refs or not a.used_attributes):
            raise ValueError('Decisive assessment requires candidate evidence and used attributes')
        if a.used_detail_keys and 'detail' not in a.used_attributes:
            raise ValueError('Detail keys require detail attribute')
    decisive = {a.judgment for a in result.interpretation_assessments} & {'supports', 'opposes', 'neutral'}
    if (not decisive) != (result.overall_fit == 'undetermined'):
        raise ValueError('Undetermined/decisive evidence mismatch')
    if result.overall_fit in {'match','strong_match'} and 'supports' not in decisive:
        raise ValueError('Positive fit requires support')
    if result.overall_fit in {'mismatch','strong_mismatch'} and 'opposes' not in decisive:
        raise ValueError('Negative fit requires opposition')
    return result


@_preserve_function('derived', 'fashion_recommendation_v2.ranking.personalization_v11')
def derived(value):
    score = SCORES[value.overall_fit]
    reasons = {a.judgment for a in value.interpretation_assessments}
    return dict(preference_score=score, p_active=score is not None, execution_status='completed',
        inactive_reason=None if score is not None else 'no_applicable_preference' if reasons <= {'not_applicable'} else
        'conflicting_product_evidence' if 'conflicted' in reasons else 'insufficient_product_evidence')



@_preserve_function('used_profile_refs', 'fashion_recommendation_v2.ranking.personalization_v11')
def used_profile_refs(assessment, profile):
    used = {a.interpretation_id for a in assessment.interpretation_assessments
            if a.judgment in {'supports', 'opposes', 'neutral'}}
    return sorted({ref for i in profile['interpretations'] if i['interpretation_id'] in used
        for ref in [*i['supporting_evidence_refs'], *i['counter_evidence_refs']]})

@_preserve_function('score_injection', 'fashion_recommendation_v2.ranking.personalization_v11')
def score_injection(source, item_id):
    entry = source._personalization[item_id]
    return dict(preference_score=entry['preference_score'], attribute_scores={}, evidence_refs=entry.get('profile_evidence_refs', []))


@_preserve_function('evaluate', 'fashion_recommendation_v2.ranking.personalization_v11')
def evaluate(runner, source, candidates, *, scope_first=False):
    from fashion_recommendation_v2.prompts.ranking import ranking_personalization_v11__PREFERENCE_PROMPT as PREFERENCE_PROMPT
    assessment_schema = PreferenceAssessmentV11
    if scope_first:
        from fashion_recommendation_v2.prompts.ranking import PREFERENCE_PROMPT
        from fashion_recommendation_v2.schemas.ranking_personalization.ranking_personalization import PreferenceAssessmentV12
        assessment_schema = PreferenceAssessmentV12
    concurrency = RANKING_V15_CONTRACT['max_concurrency'] if runner.policy_version == 'ranking_eval_v15' else MAX_CONCURRENCY
    call_slots = V15_CALL_SLOTS if runner.policy_version == 'ranking_eval_v15' else CALL_SLOTS
    record = dict(input_sha256=fingerprint(source.model_dump(mode='json')),
        prompt_sha256=fingerprint(PREFERENCE_PROMPT), schema_sha256=fingerprint(assessment_schema.model_json_schema()),
        policy_version='ranking_eval_v11', cache_used=False, contract='ranking-personalization-v11', model=MODEL, reasoning_effort='api_default',
        personalization_mode=source.personalization_mode, profile_lookup_status='not_requested',
        bundle=None, items={}, lookup_attempts=[], call_count=0, max_calls=MAX_CALLS)
    if scope_first:
        from fashion_recommendation_v2.ranking.ranking_contracts import RANKING_V12_CONTRACT
        record.update(policy_version="ranking_eval_v12", contract="ranking-personalization-v12",
                      model=RANKING_V12_CONTRACT["default_model"])
    runner.personalization_record = record
    if source.personalization_mode == 'cold' or not candidates:
        reason = 'cold' if source.personalization_mode == 'cold' else 'no_eligible_candidates'
        record['items'] = {c.item.item_id: dict(execution_status='skipped', p_active=False,
            preference_score=None, inactive_reason=reason, attempts=[]) for c in candidates}
        return record
    if runner.profile_lookup is None:
        raise PersonalizationError('Warm v11 requires an authenticated or fixed-file lookup adapter', record)
    for retry in range(2):
        record['call_count'] += 1
        trace = None
        try:
            with call_slots:
                trace = runner.brain.request_profile_lookup()
            bundle = freeze_bundle(runner.profile_lookup())
            record['lookup_attempts'].append(dict(attempt=retry, status='completed', model_response=trace))
            record.update(bundle=bundle, profile_lookup_status=bundle['status'])
            break
        except Exception as exc:
            record['lookup_attempts'].append(dict(attempt=retry, status='failed', error=str(exc), model_response=trace,
                response_snapshot=getattr(exc, 'response_snapshot', None)))
            if retry:
                record['profile_lookup_status'] = 'failed'
                raise PersonalizationError('Profile lookup failed', record) from exc
    if bundle['status'] != 'available':
        record['items'] = {c.item.item_id: dict(execution_status='skipped', p_active=False,
            preference_score=None, inactive_reason='profile_'+bundle['status'], attempts=[]) for c in candidates}
        return record
    selected = sorted(candidates, key=lambda c:c.item.item_id)
    for c in selected[MAX_CANDIDATES:]:
        record['items'][c.item.item_id] = dict(execution_status='not_evaluated', p_active=False,
            preference_score=None, inactive_reason='candidate_budget', excluded_reason='preference_not_evaluated', attempts=[])
    requests = {c.item.item_id:candidate_input(source,c,bundle) for c in selected[:MAX_CANDIDATES]}
    if scope_first:
        from fashion_recommendation_v2.schemas.ranking_personalization.ranking_personalization import PreferenceAssessmentInputV12
        requests = {i: PreferenceAssessmentInputV12.model_validate(r.model_dump()) for i,r in requests.items()}
    pending = list(requests)
    def attempt(item_id):
        request = requests[item_id]
        entry = record['items'].setdefault(item_id, dict(attempts=[]))
        response = None
        try:
            with call_slots:
                response = runner.brain.assess_preference(request.model_copy(deep=True))
            raw = response._model_response if response._model_response is not None else response.model_dump(mode='json')
            checked = validate_assessment_v11(raw, request, scope_first=scope_first)
            entry['attempts'].append(dict(model_response=raw, code_validation=dict(valid=True)))
            entry.pop('excluded_reason', None)
            entry.update(derived(checked), assessment=checked.model_dump(mode='json'),
                profile_evidence_refs=used_profile_refs(checked, bundle['profile']))
            return None
        except Exception as exc:
            snapshot = getattr(exc, 'response_snapshot', {})
            raw = (response._model_response if response._model_response is not None else response.model_dump(mode='json')) if response is not None else snapshot.get('model_response')
            entry['attempts'].append(dict(model_response=raw, response_snapshot=snapshot,
                code_validation=dict(valid=False, error=str(exc)), error_type=type(exc).__name__))
            entry.update(execution_status='failed', p_active=False, preference_score=None,
                inactive_reason='evaluation_failed', excluded_reason='preference_evaluation_failed')
            requests[item_id] = request.model_copy(update=dict(validation_feedback=[str(exc)], previous_response=raw))
            return item_id
    for retry in range(2):
        allowed = pending[:MAX_CALLS-record['call_count']]
        for item_id in pending[len(allowed):]:
            record['items'][item_id]['retry_not_run_reason'] = 'call_budget'
        record['call_count'] += len(allowed)
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = [pool.submit(copy_context().run, attempt, i) for i in allowed]
            pending = [i for future in futures if (i := future.result()) is not None]
        if not pending:
            break
    return record


@_preserve_function('narrow', 'fashion_recommendation_v2.ranking.personalization_v11')
def narrow(source, ids):
    from fashion_recommendation_v2.schemas.relation import RelationAgentInput
    from fashion_recommendation_v2.relation.relation_contracts import get_relation_contract
    result = source.model_copy(deep=True)
    result.candidate_set.candidates = [c for c in result.candidate_set.candidates if c.item.item_id in ids]
    result.candidate_set.candidate_count = len(result.candidate_set.candidates)
    ratio = result.ralationRatio
    if ratio:
        ratio.evaluations = [e for e in ratio.evaluations if e.item_id in ids]
        ratio.unevaluated_item_ids = [i for i in ratio.unevaluated_item_ids if i in ids]
        for field in ('score_breakdowns_v3','score_breakdowns_v4','score_breakdowns_v5','item_statuses_v7'):
            value = getattr(ratio,field)
            if value is not None:
                setattr(ratio,field,{i:v for i,v in value.items() if i in ids})
        contract = get_relation_contract(ratio.evaluation_version)
        if contract.evidence_module:
            ratio.evidence_input_sha256 = contract.evidence().evidence_input_hash(RelationAgentInput(
                candidate_set=result.candidate_set, intent=ratio.intent, anchor_item=ratio.anchor_item,
                anchor_search_analysis=ratio.anchor_search_analysis, evaluation_version=ratio.evaluation_version))
    return result


@_preserve_function('scoring_input', 'fashion_recommendation_v2.ranking.personalization_v11')
def scoring_input(source, entries):
    from fashion_recommendation_v2.schemas.ranking import ScoringInputV11
    result = ScoringInputV11.model_validate(source.model_dump())
    result._personalization = deepcopy_v11(entries)
    return result


@_preserve_function('applied_weights', 'fashion_recommendation_v2.ranking.personalization_v11')
def applied_weights(row):
    """Actual shared v9 weights; used by versioned personalization records."""
    application = row.scores.application_v8
    weights = application.component_weights_v37
    if weights is None:
        warm = row.scores.preference_score is not None
        base = dict(R=.5 if warm else .55, Q=.2 if warm else .35, T=.1, P=.2 if warm else 0.)
        weights = {k:v*application.base_weight for k,v in base.items()}
        weights['Relation'] = application.relation_weight
    return weights


@_preserve_function('run', 'fashion_recommendation_v2.ranking.personalization_v11')
def run_v11(runner, source):
    from fashion_recommendation_v2.schemas.ranking import RankingAgentInputV11_v11 as RankingAgentInputV11
    from fashion_recommendation_v2.agents.ranking_runner import RankingRunner
    from fashion_recommendation_v2.ranking.partial_evaluation import project
    from fashion_recommendation_v2.schemas.ranking import FinalRanking
    source = RankingAgentInputV11.model_validate(source.model_dump())
    projected, upstream = project(source.legacy_input())
    scorer = RankingRunner(brain=runner.brain, random_seed=runner.random_seed, policy_version='ranking_eval_v9')
    preflight = scorer.run(projected)  # saved observations only, no LLM
    excluded = {e.item_id for e in preflight.excluded_items}
    eligible = [c for c in projected.candidate_set.candidates if c.item.item_id not in excluded]
    record = evaluate(runner, source, eligible)
    failed = {i for i,e in record['items'].items() if e['execution_status'] in {'failed','not_evaluated'}}
    if eligible and all(record['items'][c.item.item_id]['execution_status'] in {'failed','not_evaluated'} for c in eligible):
        raise PersonalizationError('All eligible candidates failed preference evaluation', record)
    retained = {c.item.item_id for c in projected.candidate_set.candidates} - failed
    scored = scorer.run(scoring_input(narrow(projected,retained),record['items']))
    # Store actual weights for every evaluated eligible candidate, not just Top K.
    all_source = scoring_input(narrow(projected, retained - excluded),record['items'])
    all_source.requested_count = max(1,len(all_source.candidate_set.candidates))
    full = scorer.run(all_source)
    for row in full.ranked_items:
        s = row.scores
        record['items'][row.item_id]['applied_weights'] = applied_weights(row)
        record['items'][row.item_id]['scores'] = s.model_dump(mode='json')
    data = scored.model_dump(mode='json')
    data['scoring_policy_version'] = 'ranking_eval_v11_relation' if source.ralationRatio else 'ranking_eval_v11'
    data['personalization_v11'] = record
    data['upstream_exclusions_v10'] = {i:f.model_dump(mode='json') for i,f in upstream.items()}
    data['excluded_items'].extend(dict(item_id=i,reason_codes=[f.reason_code],hard_constraint_assessments=[],requirement_assessments=[]) for i,f in upstream.items())
    data['excluded_items'].extend(dict(item_id=i,reason_codes=[record['items'][i]['excluded_reason']],hard_constraint_assessments=[],requirement_assessments=[]) for i in sorted(failed))
    if failed or upstream:
        data['warnings'].append(f'Upstream excluded: {len(upstream)}; preference failed/not evaluated: {len(failed)}.')
    return FinalRanking.model_validate(data).validate_against(source)


@_preserve_function('legacy_output', 'fashion_recommendation_v2.ranking.personalization_v11')
def legacy_output(result):
    from fashion_recommendation_v2.schemas.ranking import FinalRanking
    data = result.model_dump(mode='json')
    record = data.pop('personalization_v11')
    upstream = data.pop('upstream_exclusions_v10') or {}
    failed = {i for i,e in record['items'].items() if e['execution_status'] in {'failed','not_evaluated'}}
    data['excluded_items'] = [e for e in data['excluded_items'] if e['item_id'] not in failed and e['item_id'] not in upstream]
    data['scoring_policy_version'] = 'ranking_eval_v9_relation' if result.scoring_policy_version.endswith('_relation') else 'ranking_eval_v9'
    return FinalRanking.model_validate(data)


@_preserve_function('validate_output', 'fashion_recommendation_v2.ranking.personalization_v11')
def validate_output_v11(result):
    record = result.personalization_v11
    if not record or record['contract'] != 'ranking-personalization-v11' or result.upstream_exclusions_v10 is None:
        raise ValueError('Missing v11 execution record')
    if not 0 <= record['call_count'] <= MAX_CALLS:
        raise ValueError('Invalid v11 call count')
    if record['bundle'] is not None and freeze_bundle(record['bundle']) != record['bundle']:
        raise ValueError('Frozen bundle changed')
    ids = [e.item_id for e in [*result.ranked_items,*result.excluded_items]]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate output IDs')
    exclusions = {e.item_id:e.reason_codes for e in result.excluded_items}
    for i,e in record['items'].items():
        from fashion_recommendation_v2.schemas.ranking_personalization.ranking_personalization import PreferenceExecutionV11
        PreferenceExecutionV11.model_validate(e)
        if e['execution_status'] in {'failed','not_evaluated'}:
            if exclusions.get(i) != [e['excluded_reason']] or e['p_active'] or e['preference_score'] is not None:
                raise ValueError('Failed candidate must be excluded without a fabricated P')
        elif e['execution_status'] == 'completed':
            score = SCORES[e['assessment']['overall_fit']]
            if e['preference_score'] != score or e['p_active'] != (score is not None):
                raise ValueError('P mapping mismatch')
        elif e['execution_status'] != 'skipped' or e['p_active'] or e['preference_score'] is not None:
            raise ValueError('Invalid skipped execution')
    for i,f in result.upstream_exclusions_v10.items():
        if exclusions.get(i) != [f.reason_code]:
            raise ValueError('Upstream exclusion lost')
    legacy_output(result)
    return result


@_preserve_function('validate_against', 'fashion_recommendation_v2.ranking.personalization_v11')
def validate_against_v11(result, source):
    from fashion_recommendation_v2.ranking.partial_evaluation import project
    if hasattr(source, 'personalization_mode') and source.personalization_mode != result.personalization_v11['personalization_mode']:
        raise ValueError('Personalization mode changed during execution')
    source = source.legacy_input() if hasattr(source,'legacy_input') else source
    projected, upstream = project(source)
    if upstream != result.upstream_exclusions_v10:
        raise ValueError('Upstream accounting differs')
    record = result.personalization_v11
    candidates = {c.item.item_id:c for c in projected.candidate_set.candidates}
    from fashion_recommendation_v2.agents.ranking_runner import RankingRunner
    class NoLLM:
        def generate(self, **kw): raise AssertionError('Validation must not call LLM')
    preflight = RankingRunner(llm=NoLLM(),policy_version='ranking_eval_v9',random_seed=result.random_seed).run(projected)
    expected = set(candidates) - {e.item_id for e in preflight.excluded_items}
    if set(record['items']) != expected:
        raise ValueError('Eligible candidate evaluation accounting incomplete')
    if record['personalization_mode'] == 'cold' and (record['call_count'] or record['bundle'] is not None
            or any(e['execution_status'] != 'skipped' or e['inactive_reason'] != 'cold' for e in record['items'].values())):
        raise ValueError('Cold cannot lookup or evaluate preferences')
    if record['personalization_mode'] == 'warm' and expected and record['profile_lookup_status'] not in {'available','empty','not_found'}:
        raise ValueError('Warm requires a completed profile lookup')
    for i,e in record['items'].items():
        if e['execution_status'] == 'completed':
            checked = validate_assessment_v11(e['assessment'],candidate_input(source,candidates[i],record['bundle']))
            if e.get('profile_evidence_refs') != used_profile_refs(checked, record['bundle']['profile']):
                raise ValueError('Used profile evidence differs')
            if any(e[k] != v for k,v in derived(checked).items()):
                raise ValueError('Derived execution mismatch')
    failed = {i for i,e in record['items'].items() if e['execution_status'] in {'failed','not_evaluated'}}
    legacy_output(result).validate_against(scoring_input(narrow(projected,set(candidates)-failed),record['items']))
    return result


@_preserve_function('replay', 'fashion_recommendation_v2.ranking.personalization_v11')
def replay_v11(source, result, *, requested_count=None):
    """Read-only gallery replay: no lookup, no LLM, no changed frozen evidence."""
    from fashion_recommendation_v2.ranking.partial_evaluation import project
    from fashion_recommendation_v2.agents.ranking_runner import RankingRunner
    from fashion_recommendation_v2.schemas.ranking import FinalRanking
    result.validate_against(source)
    projected, _ = project(source.legacy_input() if hasattr(source,'legacy_input') else source)
    record = result.personalization_v11
    failed = {i for i,e in record['items'].items() if e['execution_status'] in {'failed','not_evaluated'}}
    view = scoring_input(narrow(projected,{c.item.item_id for c in projected.candidate_set.candidates}-failed),record['items'])
    view.requested_count = requested_count or result.requested_count
    class NoLLM:
        def generate(self, **kw):
            raise AssertionError('Replay must not call an LLM')
    data = RankingRunner(llm=NoLLM(),policy_version='ranking_eval_v9',random_seed=result.random_seed).run(view).model_dump(mode='json')
    data.update(scoring_policy_version=result.scoring_policy_version,personalization_v11=deepcopy_v11(record),
        upstream_exclusions_v10={i:f.model_dump(mode='json') for i,f in result.upstream_exclusions_v10.items()})
    data['excluded_items'] = [e.model_dump(mode='json') for e in result.excluded_items]
    return FinalRanking.model_validate(data)


# ---- personalization_v12 ----
"""Scope-first validation and two-tier deterministic selection, without new API calls."""
from fashion_recommendation_v2.validation_reuse import handoff_validation
from copy import deepcopy
shared = _role_module('fashion_recommendation_v2.ranking.personalization_v11')
from fashion_recommendation_v2.ranking.partial_evaluation import project
from fashion_recommendation_v2.schemas.ranking import FinalRanking
from fashion_recommendation_v2.schemas.ranking import ExcludedItem
from fashion_recommendation_v2.schemas.ranking import RankingAgentInputV12_v12 as RankingAgentInputV12
from fashion_recommendation_v2.schemas.ranking import SelectionV12
from fashion_recommendation_v2.schemas.ranking_personalization.ranking_personalization import PreferenceExecutionV11


@_preserve_class('NoLLM', 'fashion_recommendation_v2.ranking.personalization_v12')
class NoLLM:
    __qualname__ = 'NoLLM'
    def generate(self, **kwargs):
        raise AssertionError('v12 scoring/replay/validation must not call LLM')


@_preserve_function('validate_assessment', 'fashion_recommendation_v2.ranking.personalization_v12')
def validate_assessment(value, source):
    return shared.validate_assessment(value, source, scope_first=True)


@_preserve_function('supplement_allowed', 'fashion_recommendation_v2.ranking.personalization_v12')
def supplement_allowed(entry):
    # Normal absence of P is distinct from failed or budget-skipped evaluation.
    return entry['preference_score'] is None and entry['execution_status'] in {'completed', 'skipped'}


@_preserve_function('scorer', 'fashion_recommendation_v2.ranking.personalization_v12')
def scorer(seed):
    from fashion_recommendation_v2.agents.ranking_runner import RankingRunner
    return RankingRunner(llm=NoLLM(), policy_version='ranking_eval_v9', random_seed=seed)


@_preserve_function('views', 'fashion_recommendation_v2.ranking.personalization_v12')
def views(source, record, seed):
    """Both views retain the original candidate pool, requests and Relation evidence."""
    projected, upstream = project(source.legacy_input() if hasattr(source, 'legacy_input') else source)
    base = projected.model_copy(deep=True)
    base.requested_count = max(1, len(base.candidate_set.candidates))
    baseline = scorer(seed).run(base)
    personal = scorer(seed).run(shared.scoring_input(base, record['items']))
    return baseline, personal, upstream


@_preserve_function('compose', 'fashion_recommendation_v2.ranking.personalization_v12')
def compose(baseline, personal, record, upstream, count):
    entries = record['items']
    personalized = [r for r in personal.ranked_items if entries[r.item_id]['preference_score'] is not None]
    supplement = [r for r in baseline.ranked_items if supplement_allowed(entries[r.item_id])]
    ordered = [(r, 'personalized') for r in personalized] + [
        (r, 'nonpersonalized_supplement' if record['personalization_mode'] == 'warm' else 'nonpersonalized')
        for r in supplement]
    record = deepcopy(record)
    record['selection'] = {}
    rows = []
    for position, (original, kind) in enumerate(ordered, 1):
        row = original.model_dump(mode='json')
        record['selection'][original.item_id] = dict(kind=kind, position=position,
            score_view_rank=original.rank, score_view_base_rank=original.base_rank)
        # base_rank is now the two-tier base order. Original score-view ranks remain explicit.
        row.update(rank=position, base_rank=position)
        rows.append(row)
        entry = record['items'][original.item_id]
        entry['scores'] = original.scores.model_dump(mode='json')
        entry['applied_weights'] = shared.applied_weights(original)
    blocked = {i:e for i,e in entries.items() if e['preference_score'] is None and not supplement_allowed(e)}
    data = baseline.model_dump(mode='json')
    policy = record.get('policy_version', 'ranking_eval_v12')
    data.update(scoring_policy_version=policy + ('_relation' if baseline.scoring_policy_version.endswith('_relation') else ''),
        requested_count=count, returned_count=min(count,len(rows)), ranked_items=rows[:count],
        status='complete' if len(rows)>=count else 'partial' if rows else 'empty',
        shortfall_reasons=[] if len(rows)>=count else ['Insufficient eligible personalized/supplement candidates.'],
        personalization_v12=record, upstream_exclusions_v10={i:f.model_dump(mode='json') for i,f in upstream.items()})
    data['excluded_items'] += [dict(item_id=i,reason_codes=[f.reason_code],hard_constraint_assessments=[],requirement_assessments=[])
        for i,f in upstream.items()]
    data['excluded_items'] += [dict(item_id=i,reason_codes=[e['excluded_reason']],hard_constraint_assessments=[],requirement_assessments=[])
        for i,e in sorted(blocked.items())]
    data['excluded_items'] = [ExcludedItem.model_validate(e).model_dump(mode='json') for e in data['excluded_items']]
    failures = sum(e['execution_status']=='failed' for e in entries.values())
    if failures:
        data['warnings'].append(f'Preference evaluation failures: {failures}; original attempts retained.')
    return data


@_preserve_function('run', 'fashion_recommendation_v2.ranking.personalization_v12')
def run(runner, source):
    source = RankingAgentInputV12.model_validate(source.model_dump())
    if runner.policy_version in {'ranking_eval_v13', 'ranking_eval_v14', 'ranking_eval_v15'}:
        from fashion_recommendation_v2.personalization_policy import similarity_input
        source = similarity_input(source)
    projected, _ = project(source.legacy_input())
    preflight = scorer(runner.random_seed).run(projected)
    excluded = {e.item_id for e in preflight.excluded_items}
    eligible = [c for c in projected.candidate_set.candidates if c.item.item_id not in excluded]
    record = shared.evaluate(runner, source, eligible, scope_first=True)
    record['policy_version'] = runner.policy_version
    if eligible and all(record['items'][c.item.item_id]['execution_status'] in {'failed','not_evaluated'} for c in eligible):
        raise shared.PersonalizationError('All eligible candidates failed preference evaluation', record)
    baseline, personal, upstream = views(source, record, runner.random_seed)
    record['score_views'] = dict(baseline=baseline.model_dump(mode='json'), personalized=personal.model_dump(mode='json'))
    output = FinalRanking.model_validate(compose(baseline,personal,record,upstream,source.requested_count))
    runner.personalization_record = output.personalization_v12
    return output.validate_against(source)


@_preserve_function('validate_output', 'fashion_recommendation_v2.ranking.personalization_v12')
def validate_output(result):
    record = result.personalization_v12
    if record and record.get('policy_version') not in {'ranking_eval_v12', 'ranking_eval_v13', 'ranking_eval_v14', 'ranking_eval_v15'}:
        raise ValueError('Unsupported personalization policy')
    if result.personalization_v11 is not None or not record or record.get('contract') != 'ranking-personalization-v12':
        raise ValueError('Missing/extraneous v12 record')
    if result.upstream_exclusions_v10 is None or not 0 <= record['call_count'] <= shared.MAX_CALLS:
        raise ValueError('Invalid v12 upstream/call accounting')
    if record['bundle'] is not None and shared.freeze_bundle(record['bundle']) != record['bundle']:
        raise ValueError('Frozen profile changed')
    for entry in record['items'].values():
        PreferenceExecutionV11.model_validate(entry)
        if entry['execution_status']=='completed':
            if any(entry[k] != v for k,v in shared.derived(shared.PreferenceAssessmentV11.model_validate(entry['assessment'])).items()):
                raise ValueError('P mapping/activation mismatch')
    for selection in record.get('selection', {}).values():
        SelectionV12.model_validate(selection)
    raw_views = record['score_views']
    if any(v['scoring_policy_version'] not in {'ranking_eval_v9','ranking_eval_v9_relation'} for v in raw_views.values()):
        raise ValueError('v12 score views must use frozen v9 arithmetic')
    baseline = FinalRanking.model_validate(raw_views['baseline'])
    personal = FinalRanking.model_validate(raw_views['personalized'])
    expected = compose(baseline, personal, record, result.upstream_exclusions_v10, result.requested_count)
    if result.model_dump(mode='json') != expected:
        raise ValueError('v12 selection, tiers, scores or output accounting changed')
    return result


@_preserve_function('validate_against', 'fashion_recommendation_v2.ranking.personalization_v12')
def validate_against(result, source):
    if result.scoring_policy_version in {'ranking_eval_v13', 'ranking_eval_v13_relation', 'ranking_eval_v14', 'ranking_eval_v14_relation', 'ranking_eval_v15', 'ranking_eval_v15_relation'} and hasattr(source, 'personalization_mode'):
        from fashion_recommendation_v2.personalization_policy import similarity_input
        source = similarity_input(source)
    record = result.personalization_v12
    intent = getattr(source, 'relation_intent', None) or (source.ralationRatio.intent if source.ralationRatio else None)
    if result.scoring_policy_version.startswith(('ranking_eval_v13', 'ranking_eval_v14', 'ranking_eval_v15')) and intent and intent.relation_type == 'similarity' and record['personalization_mode'] != 'cold':
        raise ValueError('Similarity must not use preferences in v13')
    if hasattr(source,'personalization_mode') and source.personalization_mode != record['personalization_mode']:
        raise ValueError('Personalization mode changed')
    legacy = source.legacy_input() if hasattr(source,'legacy_input') else source
    if legacy.preference_profile is not None:
        raise ValueError('v12 uses only its frozen lookup profile')
    return validate_common_input(result, legacy)


@_preserve_function('validate_common_input', 'fashion_recommendation_v2.ranking.personalization_v12')
@handoff_validation
def validate_common_input(result, legacy):
    record = result.personalization_v12
    projected, upstream = project(legacy)
    preflight = scorer(result.random_seed).run(projected)
    candidates = {c.item.item_id:c for c in projected.candidate_set.candidates}
    eligible = set(candidates)-{e.item_id for e in preflight.excluded_items}
    if set(record['items']) != eligible or upstream != result.upstream_exclusions_v10:
        raise ValueError('v12 eligible/upstream accounting mismatch')
    if record['personalization_mode']=='cold' and (record['call_count'] or record['bundle'] is not None or
            any(e['execution_status']!='skipped' or e['inactive_reason']!='cold' for e in record['items'].values())):
        raise ValueError('Cold cannot use preferences')
    if record['personalization_mode']=='warm' and eligible and record['profile_lookup_status'] not in {'available','empty','not_found'}:
        raise ValueError('Warm requires successful lookup')
    for item_id,entry in record['items'].items():
        if entry['execution_status']=='completed':
            assessment = validate_assessment(entry['assessment'], shared.candidate_input(legacy,candidates[item_id],record['bundle']))
            if entry.get('profile_evidence_refs') != shared.used_profile_refs(assessment,record['bundle']['profile']):
                raise ValueError('Used profile refs changed')
    base = projected.model_copy(deep=True)
    base.requested_count = max(1,len(base.candidate_set.candidates))
    for key, inp in [('baseline',base),('personalized',shared.scoring_input(base,record['items']))]:
        saved = FinalRanking.model_validate(record['score_views'][key])
        saved.validate_against(inp)
        # Validate deterministic selection order as well as score arithmetic.
        fresh = scorer(result.random_seed).run(inp).model_dump(mode='json')
        previous = saved.model_dump(mode='json')
        fresh.pop('ranking_id'); previous.pop('ranking_id')
        if fresh != previous:
            raise ValueError('Saved score view differs from deterministic replay')
    return result


@_preserve_function('replay', 'fashion_recommendation_v2.ranking.personalization_v12')
def replay(source, result, *, requested_count=None):
    result.validate_against(source)
    record = result.personalization_v12
    baseline = FinalRanking.model_validate(record['score_views']['baseline'])
    personal = FinalRanking.model_validate(record['score_views']['personalized'])
    return FinalRanking.model_validate(compose(baseline, personal, record,
        result.upstream_exclusions_v10, requested_count or result.requested_count))
