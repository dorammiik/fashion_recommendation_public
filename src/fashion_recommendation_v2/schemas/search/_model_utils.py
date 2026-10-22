"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- _model_utils ----

"""schemas.search._model_utils: definitions relocated without semantic changes."""
from fashion_recommendation_v2.schemas.base import StrictBaseModel
from copy import deepcopy as _copy_field
from pydantic import create_model as _create_model
from copy import deepcopy
from functools import lru_cache
from pydantic import PrivateAttr

@_preserve_class('ResponseSnapshot', 'fashion_recommendation_v2.schemas.search._model_utils')
class ResponseSnapshot(StrictBaseModel):
    """Internal evidence only; these are never part of an LLM output schema."""
    _model_response: dict | None = PrivateAttr(default=None)
    _model_response_text: str | None = PrivateAttr(default=None)

@_preserve_function('preserve_response_schema', 'fashion_recommendation_v2.schemas.search._model_utils')
@lru_cache(maxsize=128)
def preserve_response_schema(schema):
    if '_model_response' in schema.__private_attributes__:
        return schema
    return _create_model(schema.__name__, __base__=(schema, ResponseSnapshot))

@_preserve_function('_common_schema', 'fashion_recommendation_v2.schemas.search._model_utils')
def _common_schema(name, source, fields, **overrides):
    return _create_model(name, __base__=StrictBaseModel, **{key: overrides.get(key, (source.model_fields[key].annotation, _copy_field(source.model_fields[key]))) for key in fields})

@_preserve_function('copy_fields', 'fashion_recommendation_v2.schemas.search._model_utils')
def copy_fields(model, *, exclude=()):
    return {name: (field.annotation, deepcopy(field)) for name, field in model.model_fields.items() if name not in exclude}
