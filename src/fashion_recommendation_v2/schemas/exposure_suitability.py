"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- exposure_suitability ----

"""Saved visual exposure assessment; advisory in Search, policy input in Ranking."""
from typing import Literal
from pydantic import Field
from pydantic import model_validator
from fashion_recommendation_v2.schemas.base import StrictBaseModel

@_preserve_class('ExposureSuitability', 'fashion_recommendation_v2.schemas.exposure_suitability')
class ExposureSuitability(StrictBaseModel):
    status: Literal['allowed', 'restricted']
    evidence: str = Field(min_length=1)

    @model_validator(mode='after')
    def nonblank_evidence(self):
        if not self.evidence.strip():
            raise ValueError('Exposure suitability requires nonblank visual evidence.')
        return self
