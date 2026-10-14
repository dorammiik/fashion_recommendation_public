"""Code-persisted provenance of same-dimension Stylist/user comparisons."""
from fashion_recommendation_v2.module_compat import import_module as _role_module
from typing import Literal
from pydantic import Field
from fashion_recommendation_v2.schemas.base import StrictBaseModel


class StylistUserComparison(StrictBaseModel):
    stylist_requirement_id: str
    user_requirement_id: str
    relationship: Literal['refinement', 'compatible', 'conflict']
    reason: str = Field(min_length=1, pattern=r'\S')


class StylistPolicyV47(StrictBaseModel):
    comparisons: list[StylistUserComparison]
    polarities: dict[str, Literal['positive', 'negative', 'unrestricted']]
