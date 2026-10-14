from fashion_recommendation_v2.module_compat import import_module as _role_module
from typing import Protocol
from typing import TypeVar

from pydantic import BaseModel
from pydantic import Field

from fashion_recommendation_v2.schemas.base import StrictBaseModel


T = TypeVar("T", bound=BaseModel)


class ImageInput(StrictBaseModel):
    """Explicit image attachment; a URL in ordinary JSON is not an attachment."""

    item_id: str = Field(min_length=1)
    slot_id: str | None = Field(default=None, pattern=r'^item_(0[1-9]|10)$')
    image_url: str = Field(pattern=r"^https?://[^\s]+$")
    image_data_url: str | None = Field(default=None, exclude=True, pattern=r'^data:image/(jpeg|png|webp|gif);base64,')


class StructuredLLM(Protocol):

    def generate(
        self,
        *,
        system_prompt: str,
        user_input: BaseModel,
        output_schema: type[T],
        images: list[ImageInput] | None = None,
        timeout_seconds: float | None = None,
        failure_stage: str | None = None,
        max_call_timeout_seconds: float | None = None,
        max_output_tokens: int | None = None,
        stream_response: bool = False,
        call_model_settings: dict[str, str] | None = None,
    ) -> T:
        ...
