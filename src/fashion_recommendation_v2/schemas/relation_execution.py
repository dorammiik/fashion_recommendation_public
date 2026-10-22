"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- relation_execution_v7 ----

"""Code-owned candidate outcomes, distinct from an evaluated null score."""
from typing import Literal
from pydantic import Field
from pydantic import model_validator
from fashion_recommendation_v2.schemas.base import StrictBaseModel

@_preserve_class('RelationItemExecutionV7', 'fashion_recommendation_v2.schemas.relation_execution_v7')
class RelationItemExecutionV7(StrictBaseModel):
    status: Literal['success', 'fail', 'unevaluated']
    call_count: int = Field(ge=0, le=2)
    reason: str
    errors: list[str] = Field(default_factory=list)
    cost_call_ids: list[str] = Field(default_factory=list)

    @model_validator(mode='after')
    def coherent(self):
        if self.status == 'success' and (self.call_count == 0 or self.reason != 'evaluated'):
            raise ValueError('Successful evaluation needs a call and evaluated reason.')
        if self.status == 'fail' and (self.call_count == 0 or not self.errors):
            raise ValueError('Failure needs an attempted call and error records.')
        if not self.reason.strip():
            raise ValueError('Every execution outcome needs a reason.')
        return self
