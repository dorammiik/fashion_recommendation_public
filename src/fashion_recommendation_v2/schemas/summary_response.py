"""Service boundary for current Summary responses and stored legacy responses."""
from fashion_recommendation_v2.module_compat import import_module as _role_module
from pydantic import BaseModel
from pydantic import TypeAdapter

from fashion_recommendation_v2.schemas.summary import RecommendationResponse_base as LegacyRecommendationResponse
from fashion_recommendation_v2.schemas.summary import SummaryAgentInput_base as SummaryAgentInput
from fashion_recommendation_v2.schemas.summary import RecommendationResponse_v7 as RecommendationResponseV7

RecommendationResponse = LegacyRecommendationResponse | RecommendationResponseV7
_RESPONSE = TypeAdapter(RecommendationResponse)


def validate_summary_response(value: BaseModel | dict, source: SummaryAgentInput) -> RecommendationResponse:
    # Revalidate a detached copy. Do not rename/drop fields to fit an old schema.
    payload = value.model_dump() if isinstance(value, BaseModel) else value
    return _RESPONSE.validate_python(payload).validate_against(source)
