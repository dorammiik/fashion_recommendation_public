"""Server-selected demo inputs, persisted with each accepted request."""
from fashion_recommendation_v2.module_compat import import_module as _role_module
from typing import Literal
from pydantic import Field
from fashion_recommendation_v2.schemas.base import StrictBaseModel
from fashion_recommendation_v2.schemas.relation import ReferenceItem

QuickStartID = Literal['complex', 'similar', 'profile_a', 'profile_b']


class QuickStartSnapshot(StrictBaseModel):
    profile_bundle: dict | None = None
    reference_items: list[ReferenceItem] = Field(default_factory=list)
    source: str | None = None
