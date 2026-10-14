"""Stylist v2 lookup policy and structural provenance checks (no agents/prompts)."""
from fashion_recommendation_v2.module_compat import import_module as _role_module
from copy import deepcopy
from typing import get_args
from fashion_recommendation_v2.preference.profile_lookup import freeze_bundle
from fashion_recommendation_v2.compatibility import response_record
from fashion_recommendation_v2.compatibility import validate_stylist_compatibility

STYLIST_V2 = 'v2'
STYLIST_V3 = 'v3'
PERSONALIZED_STYLIST_VERSIONS = {'v2', 'v3', 'v4', 'v5', 'v6'}
PERSONALIZED_STYLIST_CONTRACTS = {'stylist-v2', 'stylist-v3', 'stylist-v4', 'stylist-v5', 'stylist-v6'}
PROFILE_LOOKUP_MODELS = {'v5': 'gpt-6-luna', 'v6': 'gpt-6-luna'}
LOOKUP_ATTEMPTS = 2
GENERATION_ATTEMPTS = 2  # existing initial + one correction


def validate_bundle(raw, user_id):
    bundle = freeze_bundle(raw)
    if bundle['profile'] is not None and bundle['profile']['user_id'] != user_id:
        raise ValueError('Profile belongs to another user.')
    if raw.get('frozen') is not None and raw['frozen'] != bundle['frozen']:
        raise ValueError('Frozen profile version/as_of/content hash mismatch.')
    return bundle


def validate_context(ctx):
    if ctx.mode == 'cold':
        if ctx.profile_status != 'not_requested' or ctx.bundle is not None or ctx.lookup_attempts or ctx.fallback:
            raise ValueError('Cold must not look up or use preferences.')
    elif ctx.profile_status == 'not_requested':
        raise ValueError('Warm requires a lookup outcome.')
    if ctx.profile_status in {'available', 'empty', 'not_found'}:
        if ctx.bundle is None or ctx.fallback:
            raise ValueError('Lookup status must match frozen bundle.')
        checked = validate_bundle(ctx.bundle, ctx.user_id)
        if checked['status'] != ctx.profile_status or ctx.bundle.get('frozen') != checked['frozen']:
            raise ValueError('Stored context must preserve frozen version/as_of/content hash.')
    elif ctx.bundle is not None:
        raise ValueError('Failed/not-requested lookup cannot expose a usable bundle.')
    if ctx.fallback != (ctx.profile_status == 'failed'):
        raise ValueError('Lookup failure must be recorded as fallback, not missing profile.')


def validate_evidence_links(bundle):
    """Check identities within the supplied snapshot, not semantic sufficiency."""
    events, snapshots = {}, {}
    for evidence in bundle['evidence_index'].values():
        event = evidence['event_id']
        identity = tuple(evidence[k] for k in ('user_id', 'item_id', 'item_snapshot_id', 'source_action', 'occurred_at'))
        if event in events and events[event] != identity:
            raise ValueError('Evidence event is linked to inconsistent item/snapshot/action/time.')
        events[event] = identity
        snapshot = evidence['item_snapshot_id']
        identity = (evidence['user_id'], evidence['item_id'], evidence['category_id'])
        if snapshot in snapshots and snapshots[snapshot] != identity:
            raise ValueError('Evidence snapshot is linked to inconsistent user/item/category.')
        snapshots[snapshot] = identity


def validate_preference_refs(entries, bundle):
    profile = bundle.get('profile') if bundle else None
    claims = {i['interpretation_id']: i for i in profile['interpretations']} if profile else {}
    for entry in entries:
        if getattr(entry, 'preference_basis', None) == 'raw_evidence':
            if not profile or not bundle:
                raise ValueError('Raw evidence requires an authenticated frozen bundle.')
            validate_evidence_links(bundle)
            if not set(entry.preference_evidence_refs) <= set(bundle['evidence_index']):
                raise ValueError('Unknown raw evidence reference.')
            continue
        if not entry.preference_interpretation_id:
            continue
        claim = claims.get(entry.preference_interpretation_id)
        if claim is None:
            raise ValueError('Unknown preference interpretation in the frozen profile.')
        allowed = set(claim['supporting_evidence_refs']) | set(claim['counter_evidence_refs'])
        if not set(entry.preference_evidence_refs) <= allowed:
            raise ValueError('Evidence must belong to the referenced preference interpretation.')
        if not set(entry.preference_evidence_refs) <= set(bundle['evidence_index']):
            raise ValueError('Unknown profile evidence reference.')


def validate_copy(result, source, bundle):
    from fashion_recommendation_v2.schemas.stylist import CompatibilityCriterion_base as CompatibilityCriterion
    expected = {s.state_id for s in source.unresolved_states}
    if set(result.resolved_state_ids) | {s.state_id for s in result.unresolved_states} != expected:
        raise ValueError('Every input state must be reported exactly once.')
    if bundle is not None:
        if source.personalization_mode != 'warm':
            raise ValueError('Cold cannot consume a profile.')
        validate_bundle(bundle, source.user_id)
    if getattr(result, 'exclude_profile_guidance', False):
        from fashion_recommendation_v2.schemas.stylist import validate_basis
        for entry in result.interpretations:
            validate_basis(entry)
    validate_preference_refs(result.interpretations, bundle)
    for entry in result.interpretations:
        if entry.origin == 'user_request' and entry.source_text not in source.user_request:
            raise ValueError('source_text must quote the supplied user_request.')
    for state in result.unresolved_states:
        if state.reason_code == 'profile_lookup_failed' and source.profile_lookup_status != 'failed':
            raise ValueError('Cannot claim an unrecorded lookup failure.')
        if state.reason_code == 'profile_missing' and source.profile_lookup_status == 'failed':
            raise ValueError('Lookup failure is not a missing profile.')
    profile_indices = frozenset(
        i for i, entry in enumerate(result.interpretations)
        if getattr(entry, 'preference_basis', 'none') != 'none'
    ) if getattr(result, 'exclude_profile_guidance', False) else frozenset()
    validate_stylist_compatibility(source, result, get_args(CompatibilityCriterion), profile_indices=profile_indices)


def lookup_context(source, llm, lookup, *, check_evidence_links=False, version=None):
    if source.personalization_mode == 'cold':
        return dict(mode='cold', user_id=source.user_id, profile_status='not_requested')
    attempts = []
    for attempt in range(LOOKUP_ATTEMPTS):
        raw = None
        try:
            raw = llm.request_profile_lookup(model=PROFILE_LOOKUP_MODELS.get(version, llm.model), operation='StylistProfileLookupV2')
            if lookup is None:
                raise ValueError('Authenticated profile lookup is not configured.')
            bundle = validate_bundle(lookup(), source.user_id)
            if check_evidence_links:
                validate_evidence_links(bundle)
            attempts.append(dict(attempt=attempt + 1, model_response=deepcopy(raw),
                code_validation=dict(status='passed', errors=[]), applied=True))
            return dict(mode='warm', user_id=source.user_id,
                profile_status=bundle['status'], bundle=bundle, lookup_attempts=attempts)
        except Exception as exc:
            attempts.append(dict(attempt=attempt + 1, **(dict(model_response=deepcopy(raw)) if raw is not None else response_record(error=exc)),
                code_validation=dict(status='failed', errors=[str(exc)]), applied=False))
    return dict(mode='warm', user_id=source.user_id,
        profile_status='failed', lookup_attempts=attempts, fallback=True)


def condition_provenance(result, entry):
    """Same definition for Search attachment, comparison and source validation."""
    if getattr(result, 'contract_version', None) not in PERSONALIZED_STYLIST_CONTRACTS:
        return None
    ctx = result.personalization_context
    provenance = dict(origin=entry.origin, state_id=entry.state_id,
        preference_interpretation_id=entry.preference_interpretation_id,
        preference_evidence_refs=entry.preference_evidence_refs,
        frozen_profile=deepcopy(ctx.bundle['frozen']) if entry.preference_evidence_refs else None, contract_version=result.contract_version)
    if result.contract_version in {'stylist-v3', 'stylist-v4', 'stylist-v5', 'stylist-v6'}:
        provenance['preference_basis'] = entry.preference_basis
    return provenance


def search_provenance_view(data):
    """Search receives Stylist proposals/references, not another full preference input.

    The complete bundle and lookup responses remain in stored Stylist results.
    """
    result = deepcopy(data)
    def visit(value):
        if isinstance(value, dict):
            if value.get('contract_version') in PERSONALIZED_STYLIST_CONTRACTS and 'personalization_context' in value:
                ctx = value['personalization_context']
                bundle = ctx.pop('bundle', None)
                ctx['frozen_profile'] = bundle.get('frozen') if bundle else None
                ctx.pop('lookup_attempts', None)
            for child in value.values(): visit(child)
        elif isinstance(value, list):
            for child in value: visit(child)
    visit(result)
    return result


SHORT_REFERENCE_INSTRUCTIONS_V4 = '''
프로필 근거는 입력 evidence_index에 제공된 요청별 짧은 키(E001 등)로 인용한다.
profile의 supporting_evidence_refs/counter_evidence_refs도 같은 키 체계다.
preference_interpretation_id는 제공된 원래 해석 ID를 그대로 사용한다.
preference_evidence_refs에는 스키마가 허용한 키만 사용한다. 키를 만들거나 추측하지 않는다.
원래 근거 ID로의 연결은 코드가 수행한다. frozen 정보는 원본 묶음의 식별 정보다.
최초 생성과 교정에 같은 키를 사용하며, 선택한 해석에 속하는 근거인지 확인한다.
'''


def short_reference_input(bundle):
    """Project references only; keep the authoritative frozen bundle untouched."""
    mapping = {f'E{i:03d}': key for i, key in enumerate(sorted((bundle or {}).get('evidence_index', {})), 1)}
    if bundle is None:
        return None, mapping
    inverse = {value: key for key, value in mapping.items()}
    projected = deepcopy(bundle)
    projected['evidence_index'] = {
        inverse[key]: dict(deepcopy(value), evidence_id=inverse[key])
        for key, value in bundle['evidence_index'].items()}
    if projected.get('profile'):
        for claim in projected['profile']['interpretations']:
            for field in ('supporting_evidence_refs', 'counter_evidence_refs'):
                claim[field] = [inverse[ref] for ref in claim[field]]
    return projected, mapping


def resolve_short_references(payload, mapping):
    """Separate code-derived copy; never mutate the received model response."""
    result = deepcopy(payload)
    for row in result['interpretations']:
        row['preference_evidence_refs'] = [mapping[ref] for ref in row['preference_evidence_refs']]
    return result
