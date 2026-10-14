from fashion_recommendation_v2.module_compat import import_module as _role_module
import pytest
from pydantic import ValidationError

from fashion_recommendation_v2.schemas.summary import RecommendationCopy_base as RecommendationCopy
from fashion_recommendation_v2.schemas.summary import RecommendationResponse_base as RecommendationResponse
from fashion_recommendation_v2.schemas.summary import SummaryAgentInput_base as SummaryAgentInput


@pytest.fixture
def summary_input():
    candidates = []
    ranked = []
    for rank in (1, 2):
        item_id = f'item_{rank}'
        candidates.append(dict(
            item=dict(item_id=item_id, title='꽃무늬 원피스',
                      item_web_url=f'https://www.ebay.com/itm/{rank}',
                      image_url=None if rank == 2 else 'https://example.com/image.jpg',
                      normalization_metadata=dict(deterministic_fields=[],
                                                  llm_normalized_fields=[], unresolved_fields=[])),
            sources=[dict(attempt_id='attempt', native_order=rank)],
            retrieval_signals=dict(best_native_order=rank, appearance_count=1),
        ))
        ranked.append(dict(
            item_id=item_id, rank=rank, base_rank=rank,
            scores=dict(request_relevance_score=1.0, native_order_score=1.0,
                        appearance_score=0.0, ebay_best_match_score=0.8,
                        base_score=0.96, max_selected_similarity=0.0,
                        diversity_penalty=0.0, final_score=0.96),
            hard_constraint_assessments=[dict(requirement_id='type', status='met')],
            requirement_assessments=[dict(requirement_id='type', status='met',
                                         match_score=1.0, penalty=0.0)],
            ranking_reasons=['요청한 원피스입니다.'],
        ))
    return SummaryAgentInput.model_validate(dict(
        user_request='꽃무늬 원피스 추천해줘',
        candidate_set=dict(
            candidate_set_id='pool', candidate_count=2, target_candidate_count=20,
            candidates=candidates, minimum_relevance_quality_met=True,
            stop_reason='target_reached',
            resolved_requirements=dict(requirements_id='requirements', requirements=[
                dict(requirement_id='type', attribute='product_type', value='dress',
                     kind='hard', source='user', source_text='원피스'),
            ]),
        ),
        final_ranking=dict(
            ranking_id='ranking', candidate_set_id='pool', requirements_id='requirements',
            scoring_policy_version='ranking_v0.2_vision', random_seed=42,
            requested_count=2, returned_count=2, status='complete', ranked_items=ranked,
        ),
    ))


def response_payload(source):
    return dict(
        response_id='response_001', intro='요청하신 원피스를 찾아봤어요. 모든 아이템은 eBay 상품이에요.',
        source_notice='상품 정보는 eBay 검색 결과를 바탕으로 안내해 드려요.',
        outro='마음에 든 아이템이 있다면 좋아요 버튼을 눌러주세요!',
        recommendations=[dict(
            rank=ranked.rank, item_id=ranked.item_id, title=candidate.item.title,
            recommendation_reason='요청하신 원피스 조건에 맞아요.', key_features=[],
            item_web_url=candidate.item.item_web_url, image_url=candidate.item.image_url,
        ) for ranked, candidate in zip(source.final_ranking.ranked_items,
                                       source.candidate_set.candidates)],
    )


def test_response_round_trip_and_missing_image(summary_input):
    response = RecommendationResponse(**response_payload(summary_input)).validate_against(summary_input)
    assert RecommendationResponse.model_validate_json(response.model_dump_json()) == response
    assert response.recommendations[1].image_url is None


@pytest.mark.parametrize('field,value', [
    ('title', 'invented title'), ('item_id', 'invented'), ('rank', 3), ('item_web_url', 'https://wrong.example'),
    ('image_url', 'https://wrong.example/image'), ('recommendation_reason', '  '),
    ('key_features', ['하나', '둘', '셋']), ('key_features', [' ']),
])
def test_invalid_recommendation(summary_input, field, value):
    data = response_payload(summary_input)
    data['recommendations'][0][field] = value
    with pytest.raises(ValueError):
        RecommendationResponse(**data).validate_against(summary_input)


@pytest.mark.parametrize('mode', ['omit', 'duplicate', 'swap', 'source'])
def test_output_contract(summary_input, mode):
    data = response_payload(summary_input)
    if mode == 'omit':
        data['recommendations'].pop()
    elif mode == 'duplicate':
        data['recommendations'][1]['item_id'] = 'item_1'
    elif mode == 'swap':
        data['recommendations'][0]['item_id'], data['recommendations'][1]['item_id'] = 'item_2', 'item_1'
    else:
        data['source_notice'] = '온라인 검색 결과입니다.'
    with pytest.raises(ValueError):
        RecommendationResponse(**data).validate_against(summary_input)


@pytest.mark.parametrize('mode', ['pool', 'requirements', 'missing_snapshot', 'duplicate', 'count'])
def test_invalid_input(summary_input, mode):
    data = summary_input.model_dump()
    if mode in ('pool', 'requirements'):
        data['final_ranking']['candidate_set_id' if mode == 'pool' else 'requirements_id'] = 'wrong'
    elif mode == 'missing_snapshot':
        data['candidate_set']['resolved_requirements'] = None
    elif mode == 'duplicate':
        data['candidate_set']['candidates'][1]['item']['item_id'] = 'item_1'
    else:
        data['candidate_set']['candidate_count'] = 0
    with pytest.raises(ValidationError):
        SummaryAgentInput(**data)


@pytest.mark.parametrize('count', [0, 1])
def test_empty_and_partial(summary_input, count):
    data = summary_input.model_dump()
    data['final_ranking'].update(
        ranked_items=data['final_ranking']['ranked_items'][:count], returned_count=count,
        status='empty' if count == 0 else 'partial', shortfall_reasons=['추천 가능한 후보 부족'],
    )
    source = SummaryAgentInput(**data)
    RecommendationResponse(**response_payload(source)).validate_against(source)


def test_llm_copy_excludes_urls_and_response_id(summary_input):
    data = response_payload(summary_input)
    with pytest.raises(ValidationError):
        RecommendationCopy(**data)
    del data['response_id']
    for item in data['recommendations']:
        del item['title']
        del item['item_web_url']
        del item['image_url']
    RecommendationCopy(**data).validate_against(summary_input)


@pytest.mark.parametrize('field,value', [('intro', '요청한 상품을 찾아봤어요.'), ('outro', ' ')])
def test_intro_source_and_outro_required(summary_input, field, value):
    data = response_payload(summary_input)
    data[field] = value
    with pytest.raises(ValidationError):
        RecommendationResponse(**data)
