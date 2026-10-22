"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- stylist_condition_policy ----

"""Code-persisted provenance of same-dimension Stylist/user comparisons."""
from typing import Literal
from pydantic import Field
from fashion_recommendation_v2.schemas.base import StrictBaseModel

@_preserve_class('StylistUserComparison', 'fashion_recommendation_v2.schemas.stylist_condition_policy')
class StylistUserComparison(StrictBaseModel):
    stylist_requirement_id: str
    user_requirement_id: str
    relationship: Literal['refinement', 'compatible', 'conflict']
    reason: str = Field(min_length=1, pattern=r'\S')

@_preserve_class('StylistPolicyV47', 'fashion_recommendation_v2.schemas.stylist_condition_policy')
class StylistPolicyV47(StrictBaseModel):
    comparisons: list[StylistUserComparison]
    polarities: dict[str, Literal['positive', 'negative', 'unrestricted']]
