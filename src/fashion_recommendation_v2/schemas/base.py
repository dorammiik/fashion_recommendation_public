"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- base ----

from pydantic import BaseModel
from pydantic import ConfigDict

@_preserve_class('StrictBaseModel', 'fashion_recommendation_v2.schemas.base')
class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
