"""Persistence contracts. LLM interpretation and recommendation integration are separate."""
from __future__ import annotations
from fashion_recommendation_v2.module_compat import import_module as _role_module

from datetime import datetime
from datetime import timezone
from typing import Annotated
from typing import Literal
from typing import Self

from pydantic import AfterValidator
from pydantic import Field
from pydantic import model_validator
from pydantic import model_serializer
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import SearchItemAnalysis
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import SearchItemAnalysisV36_v36 as SearchItemAnalysisV36
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import SearchItemAnalysisV40_v40 as SearchItemAnalysisV40
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import SearchItemAnalysisV41_v41 as SearchItemAnalysisV41
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import SearchItemAnalysisV42
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import SearchItemAnalysisV43
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import SearchItemAnalysisV44
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import SearchItemAnalysisV45

from fashion_recommendation_v2.schemas.base import StrictBaseModel
from fashion_recommendation_v2.schemas.preference.interpretation.preference_interpretation import PreferenceProfileV1_v1 as PreferenceProfileV1
from fashion_recommendation_v2.schemas.preference.interpretation.preference_interpretation import PreferenceProfileV2_v2 as PreferenceProfileV2
from fashion_recommendation_v2.schemas.preference.interpretation.preference_interpretation import PreferenceProfileV3
from fashion_recommendation_v2.schemas.preference.interpretation.preference_interpretation import PreferenceProfileV4
from fashion_recommendation_v2.schemas.search.retrieval.search_retrieval import ProductRecord
from fashion_recommendation_v2.schemas.product_evidence import ImageEvidence


from fashion_recommendation_v2.schemas.preference_profile import utc
from fashion_recommendation_v2.schemas.preference_profile import UTCDateTime
from fashion_recommendation_v2.schemas.preference_profile import Identifier
from fashion_recommendation_v2.schemas.preference_profile import Action
from fashion_recommendation_v2.schemas.preference_profile import Attribute
from fashion_recommendation_v2.schemas.preference_profile import EventCounts
from fashion_recommendation_v2.schemas.preference_profile import PreferenceWindow
from fashion_recommendation_v2.schemas.preference_profile import DetailPreference
from fashion_recommendation_v2.schemas.preference_profile import FeaturePreference
from fashion_recommendation_v2.schemas.preference_profile import TitleKeyword
from fashion_recommendation_v2.schemas.preference_profile import PreferenceGroup
from fashion_recommendation_v2.schemas.preference_profile import PreferenceProfile


class AnonymousUser(StrictBaseModel):
    user_id: Identifier
    created_at: UTCDateTime
    expires_at: UTCDateTime


class PreferenceSession(StrictBaseModel):
    session_id: Identifier
    user_id: Identifier
    started_at: UTCDateTime
    ended_at: UTCDateTime | None = None


class PreferenceRequest(StrictBaseModel):
    request_id: Identifier
    user_id: Identifier
    session_id: Identifier
    user_query: str = Field(min_length=1)
    kind: Literal['new', 'followup', 'pending']
    parent_request_id: Identifier | None = None
    created_at: UTCDateTime

    @model_validator(mode='after')
    def relation(self) -> Self:
        if (self.kind == 'followup') != (self.parent_request_id is not None):
            raise ValueError('Only followup requires parent_request_id')
        return self


class ItemSnapshot(StrictBaseModel):
    item_snapshot_id: Identifier
    user_id: Identifier
    session_id: Identifier
    request_id: Identifier
    recommendation_id: Identifier
    rank: int = Field(ge=1)
    item: ProductRecord
    search_analysis: SearchItemAnalysis | SearchItemAnalysisV36 | SearchItemAnalysisV40 | SearchItemAnalysisV41 | SearchItemAnalysisV42 | SearchItemAnalysisV43 | SearchItemAnalysisV44 | SearchItemAnalysisV45 | None = None
    image_observations: list[ImageEvidence] = Field(default_factory=list)
    captured_at: UTCDateTime

    @model_validator(mode='after')
    def evidence_image(self) -> Self:
        from fashion_recommendation_v2.search.evidence_projection import validate_analysis_identity
        validate_analysis_identity(self.item, self.search_analysis)
        if any(e.image_url != self.item.image_url for e in self.image_observations):
            raise ValueError('Observation must reference the item image')
        return self

    @model_serializer(mode='wrap')
    def serialize_analysis(self, handler):
        data = handler(self)
        if self.search_analysis is None:
            data.pop('search_analysis', None)
        return data


class InteractionEvent(StrictBaseModel):
    event_id: Identifier
    user_id: Identifier
    session_id: Identifier
    request_id: Identifier
    recommendation_id: Identifier
    rank: int = Field(ge=1)
    item_id: Identifier
    item_snapshot_id: Identifier
    action: Action
    operation: Literal['record', 'cancel', 'correct'] = 'record'
    target_event_id: Identifier | None = None
    occurred_at: UTCDateTime
    received_at: UTCDateTime

    @model_validator(mode='after')
    def target(self) -> Self:
        if (self.operation != 'record') != (self.target_event_id is not None):
            raise ValueError('Cancel/correct require a target; record must not have one')
        if self.target_event_id == self.event_id:
            raise ValueError('Event cannot target itself')
        return self


class PreferenceEvidence(StrictBaseModel):
    evidence_id: Identifier
    user_id: Identifier
    event_id: Identifier
    item_snapshot_id: Identifier
    source_action: Action
    attribute: Attribute | Literal['title_keywords']
    value: str | DetailPreference
    metadata_fields: list[str] = Field(default_factory=list)
    image_observations: list[ImageEvidence] = Field(default_factory=list)
    explanation: str = Field(min_length=1)
    category: str | None = None
    original_forms: list[str] = Field(default_factory=list)
    equivalent_attribute: Attribute | None = None


class ProfileLookup(StrictBaseModel):
    status: Literal['not_found', 'empty', 'available', 'failed']
    preference_profile: PreferenceProfile | PreferenceProfileV1 | PreferenceProfileV2 | PreferenceProfileV3 | PreferenceProfileV4 | None = None
    error: str | None = None


class PreferenceJob(StrictBaseModel):
    job_id: Identifier
    user_id: Identifier
    status: Literal['pending', 'running', 'completed', 'stopped']
    target_cursor: int = Field(ge=0)
    attempts: int = Field(ge=0)
    cycle_attempts: int = Field(default=0, ge=0)
    lease_token: str | None = None
    lease_until: UTCDateTime | None = None
    last_error: str | None = None


class PreferenceStorageConfig(StrictBaseModel):
    cookie_days: Literal[90] = 90
    pending_scan_seconds: Literal[60] = 60
    expiry_scan_seconds: Literal[3600] = 3600
    job_max_attempts: Literal[3] = 3
    job_lease_seconds: int = Field(default=300, ge=1)
