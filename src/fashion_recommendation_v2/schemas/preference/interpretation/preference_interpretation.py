"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- preference_interpretation_v1 ----

"""Minimal v1 profile and interpretation contracts; no agent/prompt imports."""
from typing import Literal as Literal_v1
from pydantic import Field as Field_v1
from pydantic import PrivateAttr
from pydantic import model_validator as model_validator_v1
from fashion_recommendation_v2.schemas.base import StrictBaseModel
from fashion_recommendation_v2.schemas.preference_profile import Identifier as Identifier_v1
from fashion_recommendation_v2.schemas.preference_profile import UTCDateTime
from fashion_recommendation_v2.schemas.preference_profile import Action

@_preserve_class('Scope', 'fashion_recommendation_v2.schemas.preference.interpretation.preference_interpretation_v1')
class Scope(StrictBaseModel):
    type: Literal_v1['global', 'category']
    categories: list[Identifier_v1]

    @model_validator_v1(mode='after')
    def validate_scope(self):
        if self.type == 'global' and self.categories or (self.type == 'category' and (not self.categories)):
            raise ValueError('Global scope requires no categories; category scope requires categories')
        return self

@_preserve_class('Interpretation', 'fashion_recommendation_v2.schemas.preference.interpretation.preference_interpretation_v1')
class Interpretation_v1(StrictBaseModel):
    preference: str = Field_v1(min_length=1)
    direction: Literal_v1['positive', 'negative', 'mixed']
    importance: Literal_v1['low', 'medium', 'high']
    confidence: Literal_v1['low', 'medium', 'high']
    scope: Scope
    supporting_evidence_refs: list[Identifier_v1] = Field_v1(min_length=1)
    counter_evidence_refs: list[Identifier_v1]
    uncertainty: str

@_preserve_class('StoredInterpretation', 'fashion_recommendation_v2.schemas.preference.interpretation.preference_interpretation_v1')
class StoredInterpretation_v1(Interpretation_v1):
    interpretation_id: Identifier_v1

@_preserve_class('InterpretationOutput', 'fashion_recommendation_v2.schemas.preference.interpretation.preference_interpretation_v1')
class InterpretationOutput_v1(StrictBaseModel):
    interpretations: list[Interpretation_v1]
    summary: str
    _model_response: dict | None = PrivateAttr(default=None)
    _model_response_text: str | None = PrivateAttr(default=None)

@_preserve_class('PreferenceProfileV1', 'fashion_recommendation_v2.schemas.preference.interpretation.preference_interpretation_v1')
class PreferenceProfileV1_v1(StrictBaseModel):
    schema_version: Literal_v1['2.0'] = '2.0'
    interpretation_version: Literal_v1['preference-interpretation-v1'] = 'preference-interpretation-v1'
    user_id: Identifier_v1
    profile_version: int = Field_v1(ge=1)
    updated_at: UTCDateTime
    as_of: UTCDateTime
    processed_event_cursor: int = Field_v1(ge=0)
    interpretations: list[StoredInterpretation_v1]
    summary: str

    def evidence_ids(self):
        return {r for i in self.interpretations for r in [*i.supporting_evidence_refs, *i.counter_evidence_refs]}

    def has_features(self):
        # Common storage predicate only, not compatibility with v0 scoring.
        return bool(self.interpretations)

@_preserve_class('InterpretationEvidence', 'fashion_recommendation_v2.schemas.preference.interpretation.preference_interpretation_v1')
class InterpretationEvidence(StrictBaseModel):
    schema_version: Literal_v1['preference-evidence-v1'] = 'preference-evidence-v1'
    evidence_id: Identifier_v1
    user_id: Identifier_v1
    event_id: Identifier_v1
    item_snapshot_id: Identifier_v1
    item_id: Identifier_v1
    source_action: Action
    occurred_at: UTCDateTime
    category_id: Identifier_v1 | None
    source_path: str = Field_v1(min_length=1)
    observation: dict

@_preserve_class('InterpretationInput', 'fashion_recommendation_v2.schemas.preference.interpretation.preference_interpretation_v1')
class InterpretationInput_v1(StrictBaseModel):
    as_of: UTCDateTime
    categories: dict[str, dict]
    products: list[dict]
    evidence: list[InterpretationEvidence]
    previous_profile: dict | None
    feedback: str | None = None

@_preserve_class('InterpretationConfig', 'fashion_recommendation_v2.schemas.preference.interpretation.preference_interpretation_v1')
class InterpretationConfig(StrictBaseModel):
    # Full-history interpretation uses its own explicit serialized-input cap.
    # This is bytes including schema/prompt allowance, not a token count claim.
    max_input_bytes: int = Field_v1(default=320000, ge=4096, le=320000)
    max_retries: int = Field_v1(default=2, ge=0, le=2)


# ---- preference_interpretation_v2 ----

"""v2 typed taste subjects; v1 evidence and management semantics remain intact."""
from typing import Literal as Literal_v2
from pydantic import Field
from pydantic import model_validator
PreviousInterpretation = Interpretation_v1
PreviousOutput = InterpretationOutput_v1
PreviousInput = InterpretationInput_v1
PreferenceProfileV1 = PreferenceProfileV1_v1
Identifier = Identifier_v1
PreferenceAttribute = Literal_v2['category', 'product_type', 'color', 'pattern', 'fit', 'sleeve_length', 'material', 'theme', 'occasion', 'brand', 'season', 'strength', 'garment_care', 'detail', 'size', 'gender']

@_preserve_class('Interpretation', 'fashion_recommendation_v2.schemas.preference.interpretation.preference_interpretation_v2')
class Interpretation(PreviousInterpretation):
    attributes: list[PreferenceAttribute] = Field(min_length=1)
    detail_keys: list[str] = Field(description='Exact Search detail keys; empty unless attributes includes detail.')

    @model_validator(mode='after')
    def validate_attributes(self):
        if len(self.attributes) != len(set(self.attributes)):
            raise ValueError('Duplicate attributes')
        if len(self.detail_keys) != len(set(self.detail_keys)) or any((not k.strip() for k in self.detail_keys)):
            raise ValueError('Detail keys must be nonblank and unique')
        if ('detail' in self.attributes) != bool(self.detail_keys):
            raise ValueError('detail requires detail_keys; other interpretations require an empty detail_keys list')
        return self

@_preserve_class('StoredInterpretation', 'fashion_recommendation_v2.schemas.preference.interpretation.preference_interpretation_v2')
class StoredInterpretation_v2(Interpretation):
    interpretation_id: Identifier

@_preserve_class('InterpretationOutput', 'fashion_recommendation_v2.schemas.preference.interpretation.preference_interpretation_v2')
class InterpretationOutput_v2(PreviousOutput):
    interpretations: list[Interpretation]

@_preserve_class('PreferenceProfileV2', 'fashion_recommendation_v2.schemas.preference.interpretation.preference_interpretation_v2')
class PreferenceProfileV2_v2(PreferenceProfileV1):
    schema_version: Literal_v2['3.0'] = '3.0'
    interpretation_version: Literal_v2['preference-interpretation-v2'] = 'preference-interpretation-v2'
    interpretations: list[StoredInterpretation_v2]

@_preserve_class('InterpretationInput', 'fashion_recommendation_v2.schemas.preference.interpretation.preference_interpretation_v2')
class InterpretationInput_v2(PreviousInput):
    allowed_detail_keys: list[str]


# ---- preference_interpretation_v3 ----

"""v3 changes interpretation instructions, reusing the exact v2 output structure."""
from typing import Literal as Literal_v3
InterpretationInput_v3 = InterpretationInput_v2
InterpretationOutput_v3 = InterpretationOutput_v2
StoredInterpretation_v3 = StoredInterpretation_v2
PreferenceProfileV2_v3 = PreferenceProfileV2_v2

@_preserve_class('PreferenceProfileV3', 'fashion_recommendation_v2.schemas.preference.interpretation.preference_interpretation_v3')
class PreferenceProfileV3(PreferenceProfileV2_v3):
    interpretation_version: Literal_v3['preference-interpretation-v3'] = 'preference-interpretation-v3'


# ---- preference_interpretation_v4 ----

"""v4 interpretation semantics, with the unchanged v2 input/output structure."""
from typing import Literal
InterpretationInput = InterpretationInput_v2
InterpretationOutput = InterpretationOutput_v2
StoredInterpretation = StoredInterpretation_v2
PreferenceProfileV2 = PreferenceProfileV2_v2

@_preserve_class('PreferenceProfileV4', 'fashion_recommendation_v2.schemas.preference.interpretation.preference_interpretation_v4')
class PreferenceProfileV4(PreferenceProfileV2):
    interpretation_version: Literal['preference-interpretation-v4'] = 'preference-interpretation-v4'
