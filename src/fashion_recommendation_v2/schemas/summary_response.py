"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- summary_response ----

"""Service boundary for current Summary responses and stored legacy responses."""
from pydantic import BaseModel
from pydantic import TypeAdapter
from fashion_recommendation_v2.schemas.summary import RecommendationResponse_base as LegacyRecommendationResponse
from fashion_recommendation_v2.schemas.summary import SummaryAgentInput_base as SummaryAgentInput
from fashion_recommendation_v2.schemas.summary import RecommendationResponse_v7 as RecommendationResponseV7
from fashion_recommendation_v2.schemas.summary import RecommendationResponse_summary_v12 as RecommendationResponseV12
from fashion_recommendation_v2.schemas.summary import RecommendationResponse_summary_v13 as RecommendationResponseV13
RecommendationResponse = RecommendationResponseV13 | RecommendationResponseV12 | LegacyRecommendationResponse | RecommendationResponseV7
_RESPONSE = TypeAdapter(RecommendationResponse)

@_preserve_function('validate_summary_response', 'fashion_recommendation_v2.schemas.summary_response')
def validate_summary_response(value: BaseModel | dict, source: SummaryAgentInput) -> RecommendationResponse:
    # Revalidate a detached copy. Do not rename/drop fields to fit an old schema.
    payload = value.model_dump() if isinstance(value, BaseModel) else value
    return _RESPONSE.validate_python(payload).validate_against(source)
