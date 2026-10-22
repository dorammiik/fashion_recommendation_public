"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- product_evidence ----

"""Product evidence shared by Search visual evaluation and Ranking."""
from typing import Literal
from typing import Self
from pydantic import Field
from pydantic import model_validator
from fashion_recommendation_v2.schemas.base import StrictBaseModel
from fashion_recommendation_v2.schemas.stylist import StylistAttribute
from fashion_recommendation_v2.schemas.stylist import StylistDetailValue_base as StylistDetailValue
from fashion_recommendation_v2.schemas.stylist import NonBlankText_base as NonBlankText
from fashion_recommendation_v2.schemas.stylist import Alternatives
DIVERSITY_ATTRIBUTE_GROUPS = {"category": "product", "color": "visual", "pattern": "visual", "fit": "shape", "detail": "shape", "gender": "gender", "material": "material", "theme": "style", "occasion": "style"}

@_preserve_class('ImageEvidence', 'fashion_recommendation_v2.schemas.product_evidence')
class ImageEvidence(StrictBaseModel):
    image_url: str = Field(pattern=r"^https?://[^\s]+$")
    observation: str = Field(min_length=1)

@_preserve_class('ConditionDefinitionV26', 'fashion_recommendation_v2.schemas.product_evidence')
class ConditionDefinitionV26(StrictBaseModel):
    """Code-bound observation instructions, never model classification output."""
    key: str
    requirement_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    visually_applicable: bool | None
    meaning: str
    observation_cues: list[str]

@_preserve_class('ProductFactV26', 'fashion_recommendation_v2.schemas.product_evidence')
class ProductFactV26(StrictBaseModel):
    attribute: StylistAttribute | Literal['product_type', "gender", 'sleeve_length', 'sleeve']
    value: NonBlankText | Alternatives | StylistDetailValue
    evidence_fields: list[str]
    evidence: list[str]
    image_evidence: list[ImageEvidence]

    @model_validator(mode='after')
    def value_contract(self):
        if (self.attribute == "detail") != isinstance(self.value, StylistDetailValue):
            raise ValueError('Only detail uses the original key/values shape.')
        if not (self.evidence_fields and any((t.strip() for t in self.evidence)) or self.image_evidence):
            raise ValueError('Known product facts require metadata or image evidence; omit unknown facts.')
        values = self.value.values if isinstance(self.value, StylistDetailValue) else self.value if isinstance(self.value, list) else [self.value]
        if any((v.strip().casefold() in {'unknown', 'n/a', 'unspecified'} for v in values)):
            raise ValueError('Unknown product properties must remain absent, not fabricated facts.')
        return self

@_preserve_class('EvidenceConflict', 'fashion_recommendation_v2.schemas.product_evidence')
class EvidenceConflict(StrictBaseModel):
    """Contradictory evidence, including attributes not explicitly requested."""
    attribute: str = Field(min_length=1)
    requirement_id: str | None = None
    evidence_fields: list[str] = Field(min_length=1)
    metadata_evidence: list[str] = Field(min_length=1)
    image_evidence: list[ImageEvidence] = Field(min_length=1)
    explanation: str = Field(min_length=1)

@_preserve_class('RequirementJudgment', 'fashion_recommendation_v2.schemas.product_evidence')
class RequirementJudgment(StrictBaseModel):
    """LLM output for ANY original condition, hard or soft; no numeric scoring."""
    requirement_id: str
    status: Literal["met", "mostly_met", "partial", "unmet", 'unknown']
    evidence_fields: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    image_evidence: list[ImageEvidence] = Field(default_factory=list)

@_preserve_class('DiversityFeature', 'fashion_recommendation_v2.schemas.product_evidence')
class DiversityFeature(StrictBaseModel):
    """Evidence-backed English features using Stylist's attribute/value convention."""
    attribute: StylistAttribute | Literal["gender"]
    value: NonBlankText | Alternatives | StylistDetailValue
    group: Literal["product", "visual", "shape", "gender", "material", "style"]
    fixed_by_requirement_ids: list[str] = Field(default_factory=list)
    evidence_fields: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    image_evidence: list[ImageEvidence] = Field(default_factory=list)

    @model_validator(mode='after')
    def validate_feature(self) -> Self:
        if (self.attribute == "detail") != isinstance(self.value, StylistDetailValue):
            raise ValueError("Only detail requires key/values, as in Stylist.")
        if DIVERSITY_ATTRIBUTE_GROUPS.get(self.attribute) != self.group:
            raise ValueError("Attribute does not belong to a diversity scoring group.")
        return self
from fashion_recommendation_v2.schemas.preference_profile import Attribute

@_preserve_class('HardConstraintAssessment', 'fashion_recommendation_v2.schemas.product_evidence')
class HardConstraintAssessment(StrictBaseModel):
    """Pre-LLM code filter: price only in v0.3; legacy outputs also contain semantic gates."""
    requirement_id: str
    status: Literal["met", "unmet", 'unknown']
    evidence_fields: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)

@_preserve_class('RankingItemIssue', 'fashion_recommendation_v2.schemas.product_evidence')
class RankingItemIssue(StrictBaseModel):
    batch_id: str
    item_id: str
    requirement_id: str | None = None
    fields: list[str] = Field(default_factory=list)
    code: Literal["invalid_response", "missing_assessments"]
    message: str
    retry_count: int = Field(ge=0, le=1)

@_preserve_class('PreferenceObservation', 'fashion_recommendation_v2.schemas.product_evidence')
class PreferenceObservation(StrictBaseModel):
    attribute: Attribute | Literal['title_keywords']
    value: NonBlankText | Alternatives | StylistDetailValue
    evidence_fields: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    image_evidence: list[ImageEvidence] = Field(default_factory=list)

    @model_validator(mode='after')
    def detail_value(self) -> Self:
        if (self.attribute == "detail") != isinstance(self.value, StylistDetailValue):
            raise ValueError('Only detail uses key/values')
        return self
