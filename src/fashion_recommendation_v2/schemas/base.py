from fashion_recommendation_v2.module_compat import import_module as _role_module
from pydantic import BaseModel
from pydantic import ConfigDict


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )