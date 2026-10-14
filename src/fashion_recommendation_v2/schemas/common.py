from __future__ import annotations
from fashion_recommendation_v2.module_compat import import_module as _role_module
from typing import Literal


AgentName = Literal[
    "stylist_agent",
    "search_agent",
    "relation_agent",
    "ranking_agent",
    "summary_agent",
]


OutputName = Literal[
    "StylistResult",
    "CandidateSet",
    "ralationRatio",
    "FinalRanking",
    "RecommendationResponse",
]


StateRef = Literal[
    "request.user_query",
    "request.requested_count",
    "request.preference_profile",
    "agent_outputs.stylist_result",
    "agent_outputs.candidate_set",
    "agent_outputs.ralationRatio",
    "agent_outputs.final_ranking",
]

# Raw marketplace values shared by retrieval and normalization.
from pydantic import Field
from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_base

class RawMoney(StrictBaseModel_base):
    __qualname__ = 'RawMoney'
    value: str
    currency: str


class RawAspect(StrictBaseModel_base):
    __qualname__ = 'RawAspect'
    type: str | None = None
    name: str
    value: str


class EBayRawItem(StrictBaseModel_base):
    __qualname__ = 'EBayRawItem'
    native_order: int = Field(ge=1)

    item_id: str
    title: str

    category_path: str | None = None
    category_id_path: str | None = None

    image_url: str | None = None
    item_web_url: str | None = None

    price: RawMoney | None = None

    condition: str | None = None
    condition_description: str | None = None

    color: str | None = None

    size: str | None = None
    size_type: str | None = None

    material: str | None = None
    pattern: str | None = None
    brand: str | None = None

    short_description: str | None = None

    localized_aspects: list[RawAspect] = Field(
        default_factory=list
    )
