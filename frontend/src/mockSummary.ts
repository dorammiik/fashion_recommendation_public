import type { Response } from './types';
import type { Scenario } from './mock';

// Presentation fixtures for Summary v9 (v6 response contract, v5 feedback copy).
// These are fixed preview products; mock never runs Search or Summary.
const feedbackNoticeOff = '좋아요를 누르거나 추천 아이템을 클릭한 기록은 저장되고 있어요. 다만 현재는 취향 프로필 자동 갱신이 꺼져 있어, 이 기록을 추천에 반영하기 어려워요. 자동 갱신을 켜면 행동 기록을 바탕으로 취향에 더 잘 맞는 아이템을 추천해드릴게요!';
const products = [
  {title: '클래식 스트레이트 팬츠', value: 29.99, reason: '일자로 떨어지는 실루엣의 검은색 팬츠예요. 핏이 여유로운 2번보다 단정한 인상으로 입기 좋아요.', features: ['스트레이트 핏', '미니멀 디자인']},
  {title: '소프트 와이드 팬츠', value: 34.5, reason: '통이 넓고 앞면에 턱이 있는 검은색 팬츠예요. 몸에 붙지 않는 여유로운 실루엣을 원하신다면 살펴보세요.', features: ['와이드 핏', '턱 디테일']},
  {title: '테이퍼드 코튼 팬츠', value: 27, reason: '밑단으로 갈수록 좁아지는 형태의 검은색 코튼 팬츠예요. 넓게 떨어지는 핏보다 밑단이 정돈된 스타일을 찾을 때 고려해보세요.', features: ['테이퍼드 핏', '코튼']},
  {title: '릴랙스드 카고 팬츠', value: 39.99, reason: '옆면 포켓이 있는 여유로운 핏의 검은색 팬츠예요. 기본 팬츠보다 포켓 디테일이 드러나는 캐주얼한 스타일이에요.', features: ['카고 포켓', '여유 있는 핏']},
];

export function mockSummary(scenario: Scenario, requestId: string, mode: 'cold' | 'warm' = 'cold'): Response {
  const response_id = `response_${requestId}`;
  if (scenario === 'empty') return {
    response_id,
    intro: '조건에 맞는 상품을 찾지 못했어요.',
    remarks: '검색에서 반환된 후보 상품이 없어 추천할 상품을 고르지 못했어요. 제공된 결과만으로는 후보가 없었던 구체적인 이유를 확인하기 어려워요.',
    recommendations: [],
    outro: '어떤 상품을 원하시는지 좀 더 구체적으로 설명해주시면 다시 검색해볼게요.',
    next_recommendation: [],
    feedback_notice: null,
  };
  return {
    response_id,
    intro: mode === 'warm' ? '취향을 함께 고려한 검은색 팬츠 2개와 요청 조건을 기준으로 추가한 상품 2개를 골랐어요.' : '요청하신 조건을 중심으로 서로 다른 핏과 디테일의 검은색 팬츠 4개를 골랐어요.',
    remarks: (mode === 'warm' ? '1번은 단정한 실루엣에 보인 관심을, 2번은 여유로운 핏에 보인 관심을 고려했어요. 3·4번은 비교할 취향 정보가 부족해 요청 조건을 기준으로 추가했어요. ' : '') + '상품 정보는 eBay 판매 정보를 바탕으로 안내해드려요. 구매 전 판매 페이지에서 실측 사이즈와 상품 상태, 배송 조건을 확인해주세요.' +
      (scenario === 'missing' ? ' 1번 상품은 이미지와 상품 링크가 제공되지 않아 사진과 판매 페이지를 확인할 수 없어요.' : ''),
    recommendations: products.map((product, i) => ({
      item_id: `mock-${i}`, rank: i + 1, title: product.title,
      price: {value: product.value, currency: 'USD'},
      image_url: scenario === 'missing' && i === 0 ? null : `/mock/pants-${i}.svg`,
      item_web_url: scenario === 'missing' && i === 0 ? null : 'https://www.ebay.com/',
      recommendation_reason: mode === 'warm' && i === 0 ? '관심을 보이셨던 단정한 실루엣의 검은색 팬츠예요. 일자로 떨어지는 핏이라 넓은 통의 2번과 다른 느낌으로 살펴볼 수 있어요.' : mode === 'warm' && i === 1 ? '관심을 보이셨던 여유로운 핏에 앞면 턱 디테일이 더해진 검은색 팬츠예요. 몸에 붙지 않는 넓은 실루엣으로 살펴볼 수 있어요.' : product.reason, key_features: product.features,
    })),
    outro: '일자로 떨어지는 핏과 통이 넓은 핏 중 어느 쪽을 더 원하시나요?',
    next_recommendation: ['1번 추천과 비슷한 팬츠 찾아줘.', '1번 추천과 어울리는 상의 찾아줘.'],
    feedback_notice: scenario === 'no_notice' ? null : feedbackNoticeOff,
  };
}
