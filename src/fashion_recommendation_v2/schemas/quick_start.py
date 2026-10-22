"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- quick_start ----

"""Server-selected demo inputs, persisted with each accepted request."""
from typing import Literal
from pydantic import Field
from fashion_recommendation_v2.schemas.base import StrictBaseModel
from fashion_recommendation_v2.schemas.relation import ReferenceItem
QuickStartID = Literal['complex', 'similar', 'profile_a', 'profile_b']

@_preserve_class('QuickStartSnapshot', 'fashion_recommendation_v2.schemas.quick_start')
class QuickStartSnapshot(StrictBaseModel):
    profile_bundle: dict | None = None
    reference_items: list[ReferenceItem] = Field(default_factory=list)
    source: str | None = None
