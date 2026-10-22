"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- registry ----

from fashion_recommendation_v2.schemas.planner import AvailableAgent
AVAILABLE_AGENTS = [AvailableAgent(name="stylist_agent", description='Orchestrator가 Stylist 해석이 필요하다고 지정한 unresolved state를 검색 가능한 상품 속성으로 해석한다.', output_schema="StylistResult"), AvailableAgent(name="search_agent", description='검색 전략을 수립하고 충분한 Candidate Set을 확보한다.', output_schema="CandidateSet"), AvailableAgent(name="relation_agent", description='상품 간 compatibility 또는 관계 적합도를 평가한다.', output_schema="ralationRatio"), AvailableAgent(name="ranking_agent", description='Candidate를 비교하여 최종 추천 순위를 생성한다.', output_schema="FinalRanking"), AvailableAgent(name="summary_agent", description='최종 Ranking 결과를 사용자에게 설명 가능한 추천 응답으로 변환한다.', output_schema="RecommendationResponse")]
