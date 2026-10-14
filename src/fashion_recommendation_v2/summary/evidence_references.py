"""Request-local Summary references, derived exclusively from selected Ranking rows."""
from fashion_recommendation_v2.module_compat import import_module as _role_module
from copy import deepcopy

REFERENCE_INSTRUCTIONS = '''
preference_evidence_refs에는 해당 상품의 allowed_preference_evidence_refs에 있는 짧은 키만
사용한다. preference_support.evidence_refs도 동일한 요청별 키이며 근거 내용과 연결된다.
다른 상품에만 있는 키나 프로필에만 있는 근거는 인용하지 않는다. 허용 근거가 없으면
빈 배열을 반환한다. 키를 추측하거나 원래 ID를 출력하지 않는다. 실제 ID 연결은 코드가
담당한다. 최초 생성과 교정에서 키의 의미는 같다. 기존 취향 주장·근거 연결 규칙을 유지한다.
resolved_requirements의 stylist_provenance는 다른 에이전트가 만든 조건의 원래 출처이며
Summary의 인용 가능 근거 목록이 아니다. 그 출처의 실제 ID를 응답에 복사하거나,
해당 상품의 allowed_preference_evidence_refs 밖의 근거를 취향 설명에 사용하지 않는다.
'''


def reference_map(source):
    allowed = {row.item_id: sorted(set(row.preference_evidence_refs))
               for row in source.final_ranking.ranked_items}
    ids = sorted({ref for refs in allowed.values() for ref in refs})
    mapping = {f'E{i:03d}': ref for i, ref in enumerate(ids, 1)}
    inverse = {ref: key for key, ref in mapping.items()}
    return dict(key_to_id=mapping, allowed_by_item={
        item: [inverse[ref] for ref in refs] for item, refs in allowed.items()})


def project_references(request, mapping):
    projected = request.model_copy(deep=True)
    inverse = {ref: key for key, ref in mapping['key_to_id'].items()}
    for item in projected.items:
        item['allowed_preference_evidence_refs'] = list(mapping['allowed_by_item'][item['item_id']])
        for support in item['preference_support']:
            support['evidence_refs'] = [inverse[ref] for ref in support['evidence_refs']]
    return projected


def resolve_references(payload, mapping):
    """Reject before resolving; no fuzzy match, ID fallback, or input mutation."""
    for row in payload['recommendations']:
        refs = row['preference_evidence_refs']
        if any(ref not in mapping['key_to_id'] for ref in refs):
            raise ValueError('Unknown Summary preference evidence key')
        if row['item_id'] not in mapping['allowed_by_item'] or not set(refs) <= set(mapping['allowed_by_item'][row['item_id']]):
            raise ValueError('Summary preference claims must cite actually used ranking evidence for this item')
    result = deepcopy(payload)
    for row in result['recommendations']:
        row['preference_evidence_refs'] = [mapping['key_to_id'][key] for key in row['preference_evidence_refs']]
    return result


def validate_saved_result(record, source):
    """Recheck the saved raw-to-canonical link against authoritative Ranking input."""
    from fashion_recommendation_v2.schemas.summary import response_schema
    from fashion_recommendation_v2.schemas.summary import RecommendationCopy
    mapping = reference_map(source)
    if record['reference_map'] != mapping:
        raise ValueError('Saved Summary reference map differs from Ranking input')
    if record['code_validation'].get('valid') is not True:
        raise ValueError('Failed Summary attempts have no applicable result')
    raw = record['model_response']
    response_schema(mapping['key_to_id']).model_validate(raw)
    canonical = RecommendationCopy.model_validate(resolve_references(raw, mapping)).validate_against(source)
    if canonical.model_dump(mode='json') != record['code_derived']:
        raise ValueError('Saved Summary result differs from validated raw response')
    return canonical
