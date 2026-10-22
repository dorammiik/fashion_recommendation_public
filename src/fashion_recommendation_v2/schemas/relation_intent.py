"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- relation_intent ----

from typing import Literal
from pydantic import Field
from pydantic import model_validator
from fashion_recommendation_v2.schemas.base import StrictBaseModel

@_preserve_class('RelationIntent', 'fashion_recommendation_v2.schemas.relation_intent')
class RelationIntent(StrictBaseModel):
    relation_type: Literal['compatibility', 'similarity']
    source_text: str = Field(min_length=1)
    anchor_category: str | None = None
    anchor_item_id: str | None = None
    anchor_rank: int | None = Field(default=None, ge=1)

    @model_validator(mode='after')
    def anchor(self):
        if bool(self.anchor_category) == bool(self.anchor_item_id):
            raise ValueError('Exactly one category or item anchor is required.')
        if self.anchor_category and self.anchor_rank is not None:
            raise ValueError('Category anchors have no recommendation rank.')
        if self.relation_type == 'similarity' and (not self.anchor_item_id):
            raise ValueError('Similarity requires a specific item anchor.')
        return self
