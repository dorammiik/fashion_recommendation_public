"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- base ----

from typing import Protocol
from typing import TypeVar
from pydantic import BaseModel
from pydantic import Field
from fashion_recommendation_v2.schemas.base import StrictBaseModel
T = TypeVar("T", bound=BaseModel)

@_preserve_class('ImageInput', 'fashion_recommendation_v2.llm.base')
class ImageInput(StrictBaseModel):
    """Explicit image attachment; a URL in ordinary JSON is not an attachment."""
    item_id: str = Field(min_length=1)
    slot_id: str | None = Field(default=None, pattern=r'^item_(0[1-9]|10)$')
    image_url: str = Field(pattern=r"^https?://[^\s]+$")
    image_data_url: str | None = Field(default=None, exclude=True, pattern=r'^data:image/(jpeg|png|webp|gif);base64,')

@_preserve_class('StructuredLLM', 'fashion_recommendation_v2.llm.base')
class StructuredLLM(Protocol):

    def generate(self, *, system_prompt: str, user_input: BaseModel, output_schema: type[T], images: list[ImageInput] | None=None, timeout_seconds: float | None=None, failure_stage: str | None=None, max_call_timeout_seconds: float | None=None, max_output_tokens: int | None=None, stream_response: bool=False, call_model_settings: dict[str, str] | None=None) -> T:
        ...
