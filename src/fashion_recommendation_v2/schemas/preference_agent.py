"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- preference_agent ----

"""Text-only semantic extraction contracts; numeric preferences are never LLM outputs."""
from typing import Literal
from pydantic import Field
from fashion_recommendation_v2.schemas.base import StrictBaseModel
from fashion_recommendation_v2.schemas.preference_profile import Attribute
from fashion_recommendation_v2.schemas.preference_profile import Identifier

@_preserve_class('Observation', 'fashion_recommendation_v2.schemas.preference_agent')
class Observation(StrictBaseModel):
    observation_id: Identifier
    field: str
    text: str

@_preserve_class('AnalysisUnit', 'fashion_recommendation_v2.schemas.preference_agent')
class AnalysisUnit(StrictBaseModel):
    unit_id: Identifier
    snapshot_id: Identifier
    observations: list[Observation]

@_preserve_class('ExtractedFeature', 'fashion_recommendation_v2.schemas.preference_agent')
class ExtractedFeature(StrictBaseModel):
    attribute: Attribute
    value: str = Field(min_length=1)
    detail_key: str | None
    observation_ids: list[Identifier] = Field(min_length=1)
    explanation: str = Field(min_length=1)

@_preserve_class('ExtractedKeyword', 'fashion_recommendation_v2.schemas.preference_agent')
class ExtractedKeyword(StrictBaseModel):
    original: str = Field(min_length=1)
    normalized: str = Field(min_length=1)
    observation_ids: list[Identifier] = Field(min_length=1)
    # Avoid counting a title keyword a second time as an ordinary attribute.
    equivalent_attribute: Attribute | None

@_preserve_class('UnitAnalysis', 'fashion_recommendation_v2.schemas.preference_agent')
class UnitAnalysis(StrictBaseModel):
    unit_id: Identifier
    category: str | None
    category_observation_ids: list[Identifier]
    features: list[ExtractedFeature]
    keywords: list[ExtractedKeyword]
    unresolved: list[str]

@_preserve_class('PreferenceBatchInput', 'fashion_recommendation_v2.schemas.preference_agent')
class PreferenceBatchInput(StrictBaseModel):
    units: list[AnalysisUnit]
    existing_categories: list[str]
    feedback: str | None = None

@_preserve_class('PreferenceBatchOutput', 'fashion_recommendation_v2.schemas.preference_agent')
class PreferenceBatchOutput(StrictBaseModel):
    units: list[UnitAnalysis]

@_preserve_class('CachedAnalysis', 'fashion_recommendation_v2.schemas.preference_agent')
class CachedAnalysis(StrictBaseModel):
    snapshot_id: Identifier
    category: str | None
    features: list[ExtractedFeature]
    keywords: list[ExtractedKeyword]
    observations: list[Observation]
    unresolved: list[str]
    extractor_version: Literal['preference-extractor-v1'] = 'preference-extractor-v1'

@_preserve_class('PreferenceAgentConfig', 'fashion_recommendation_v2.schemas.preference_agent')
class PreferenceAgentConfig(StrictBaseModel):
    max_events_per_batch: int = Field(default=100, ge=1, le=100)
    max_items_per_batch: int = Field(default=30, ge=1, le=30)
    max_batches: int = Field(default=10, ge=1, le=10)
    max_input_tokens: int = Field(default=16000, ge=2000, le=16000)
    max_retries: int = Field(default=2, ge=0, le=2)
