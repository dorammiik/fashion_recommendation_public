"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- preference_profile ----

"""Dependency-free profile contracts shared by recommendation and persistence schemas."""
from datetime import datetime
from datetime import timezone
from typing import Annotated
from typing import Literal
from typing import Self
from pydantic import AfterValidator
from pydantic import ConfigDict
from pydantic import Field
from pydantic import model_validator
from fashion_recommendation_v2.schemas.base import StrictBaseModel

@_preserve_function('utc', 'fashion_recommendation_v2.schemas.preference_profile')
def utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('Timezone-aware datetime required')
    return value.astimezone(timezone.utc)
UTCDateTime = Annotated[datetime, AfterValidator(utc)]
Identifier = Annotated[str, Field(min_length=1, pattern=r'^\S+$')]
Action = Literal['click', 'like', 'dislike', 'purchase']
Attribute = Literal['category_path', 'color', 'size', 'fit', 'material', 'pattern', 'brand', 'strength', 'garment_care', 'theme', 'season', 'occasion', 'detail']

@_preserve_class('EventCounts', 'fashion_recommendation_v2.schemas.preference_profile')
class EventCounts(StrictBaseModel):
    click: int = Field(default=0, ge=0)
    like: int = Field(default=0, ge=0)
    dislike: int = Field(default=0, ge=0)
    purchase: int = Field(default=0, ge=0)

@_preserve_class('PreferenceWindow', 'fashion_recommendation_v2.schemas.preference_profile')
class PreferenceWindow(StrictBaseModel):
    positive_mass: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    negative_mass: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    score: float | None = Field(default=None, ge=-1, le=1, allow_inf_nan=False)
    strength: Literal['unknown', 'low', 'medium', 'high'] = 'unknown'

    @model_validator(mode='after')
    def score_contract(self) -> Self:
        mass = self.positive_mass + self.negative_mass
        expected = (self.positive_mass - self.negative_mass) / (mass + 1)
        if mass == 0:
            if self.score is not None or self.strength != 'unknown':
                raise ValueError('Zero mass requires unknown')
        elif self.score is None or abs(self.score - expected) > 1e-09:
            raise ValueError('Score must match mass formula')
        elif self.strength != ('low' if abs(expected) < 0.25 else 'medium' if abs(expected) < 0.6 else 'high'):
            raise ValueError('Strength must match score')
        return self

@_preserve_class('DetailPreference', 'fashion_recommendation_v2.schemas.preference_profile')
class DetailPreference(StrictBaseModel):
    key: Identifier
    values: list[str] = Field(min_length=1)

@_preserve_class('FeaturePreference', 'fashion_recommendation_v2.schemas.preference_profile')
class FeaturePreference(StrictBaseModel):
    attribute: Attribute
    value: str | DetailPreference
    short_term: PreferenceWindow = Field(default_factory=PreferenceWindow)
    long_term: PreferenceWindow = Field(default_factory=PreferenceWindow)
    confidence: float = Field(default=0.0, ge=0, le=1, allow_inf_nan=False)
    total: EventCounts = Field(default_factory=EventCounts)
    recent_30d: EventCounts = Field(default_factory=EventCounts)
    distinct_item_count: int = Field(default=0, ge=0)
    distinct_session_count: int = Field(default=0, ge=0)
    last_interaction_at: UTCDateTime | None = None
    evidence_refs: list[Identifier] = Field(default_factory=list)

    @model_validator(mode='after')
    def detail(self) -> Self:
        if (self.attribute == 'detail') != isinstance(self.value, DetailPreference):
            raise ValueError('Only detail uses key/values')
        if isinstance(self.value, str) and (not self.value.strip()):
            raise ValueError('Feature value cannot be blank')
        return self

@_preserve_class('TitleKeyword', 'fashion_recommendation_v2.schemas.preference_profile')
class TitleKeyword(StrictBaseModel):
    short_term: PreferenceWindow = Field(default_factory=PreferenceWindow)
    long_term: PreferenceWindow = Field(default_factory=PreferenceWindow)
    equivalent_attribute: Attribute | None = None
    original_forms: list[str] = Field(min_length=1)
    normalized: str = Field(min_length=1)
    distinct_item_count: int = Field(ge=1)
    evidence_refs: list[Identifier] = Field(min_length=1)

@_preserve_class('PreferenceGroup', 'fashion_recommendation_v2.schemas.preference_profile')
class PreferenceGroup(StrictBaseModel):
    features: list[FeaturePreference] = Field(default_factory=list)
    title_keywords: list[TitleKeyword] = Field(default_factory=list)
    summary: str | None = None

@_preserve_class('PreferenceProfile', 'fashion_recommendation_v2.schemas.preference_profile')
class PreferenceProfile(StrictBaseModel):
    model_config = ConfigDict(populate_by_name=True)
    schema_version: Literal['1.0'] = '1.0'
    policy_version: str = 'preference-v1'
    user_id: Identifier
    profile_version: int = Field(ge=1)
    updated_at: UTCDateTime
    as_of: UTCDateTime
    processed_event_cursor: int = Field(ge=0)
    global_preferences: PreferenceGroup = Field(default_factory=PreferenceGroup, alias='global')
    by_category: dict[str, PreferenceGroup] = Field(default_factory=dict)
    summary: str | None = None

    @model_validator(mode='after')
    def category_keys(self) -> Self:
        import re
        if any((not re.fullmatch(r'[a-z][a-z0-9]*(?:_[a-z0-9]+)*', k) for k in self.by_category)):
            raise ValueError('Category keys must be normalized English identifiers')
        return self

    def evidence_ids(self) -> set[str]:
        return {ref for group in [self.global_preferences, *self.by_category.values()] for feature in [*group.features, *group.title_keywords] for ref in feature.evidence_refs}

    def has_features(self) -> bool:
        return any((g.features or g.title_keywords for g in [self.global_preferences, *self.by_category.values()]))
