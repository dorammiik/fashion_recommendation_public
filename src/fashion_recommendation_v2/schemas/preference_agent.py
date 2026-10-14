"""Text-only semantic extraction contracts; numeric preferences are never LLM outputs."""
from fashion_recommendation_v2.module_compat import import_module as _role_module
from typing import Literal
from pydantic import Field
from fashion_recommendation_v2.schemas.base import StrictBaseModel
from fashion_recommendation_v2.schemas.preference_profile import Attribute
from fashion_recommendation_v2.schemas.preference_profile import Identifier


class Observation(StrictBaseModel):
    observation_id: Identifier
    field: str
    text: str


class AnalysisUnit(StrictBaseModel):
    unit_id: Identifier
    snapshot_id: Identifier
    observations: list[Observation]


class ExtractedFeature(StrictBaseModel):
    attribute: Attribute
    value: str = Field(min_length=1)
    detail_key: str | None
    observation_ids: list[Identifier] = Field(min_length=1)
    explanation: str = Field(min_length=1)


class ExtractedKeyword(StrictBaseModel):
    original: str = Field(min_length=1)
    normalized: str = Field(min_length=1)
    observation_ids: list[Identifier] = Field(min_length=1)
    # Avoid counting a title keyword a second time as an ordinary attribute.
    equivalent_attribute: Attribute | None


class UnitAnalysis(StrictBaseModel):
    unit_id: Identifier
    category: str | None
    category_observation_ids: list[Identifier]
    features: list[ExtractedFeature]
    keywords: list[ExtractedKeyword]
    unresolved: list[str]


class PreferenceBatchInput(StrictBaseModel):
    units: list[AnalysisUnit]
    existing_categories: list[str]
    feedback: str | None = None


class PreferenceBatchOutput(StrictBaseModel):
    units: list[UnitAnalysis]


class CachedAnalysis(StrictBaseModel):
    snapshot_id: Identifier
    category: str | None
    features: list[ExtractedFeature]
    keywords: list[ExtractedKeyword]
    observations: list[Observation]
    unresolved: list[str]
    extractor_version: Literal['preference-extractor-v1'] = 'preference-extractor-v1'


class PreferenceAgentConfig(StrictBaseModel):
    max_events_per_batch: int = Field(default=100, ge=1, le=100)
    max_items_per_batch: int = Field(default=30, ge=1, le=30)
    max_batches: int = Field(default=10, ge=1, le=10)
    max_input_tokens: int = Field(default=16000, ge=2000, le=16000)
    max_retries: int = Field(default=2, ge=0, le=2)
