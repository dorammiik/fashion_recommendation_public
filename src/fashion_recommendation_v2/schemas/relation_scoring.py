"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- relation_scoring ----

"""Persisted, evidence-linked criterion judgments shared by Relation consumers.

No prompt, agent or scoring-policy dependencies belong in these data contracts.
"""
from typing import Literal
from pydantic import Field
from pydantic import field_validator
from pydantic import model_validator
from pydantic import model_serializer
from fashion_recommendation_v2.schemas.base import StrictBaseModel
Criterion = Literal['category_pairing', 'color_pattern', 'style', 'season', 'use_context', 'product_type', 'color', 'length', 'pattern', 'details', 'material']
Facet = Literal['pattern', 'category_pairing', 'color', 'pattern_type', 'pattern_scale', 'pattern_distribution', 'style', 'season', 'use_context', 'product_type', 'garment_length', 'sleeve_length', 'details', 'material']
ScoreLevel = Literal[0.0, 0.25, 0.5, 0.75, 1.0]

@_preserve_class('RelationFacetJudgment', 'fashion_recommendation_v2.schemas.relation_scoring')
class RelationFacetJudgment(StrictBaseModel):
    facet: Facet
    state: Literal['assessed', 'unknown', 'observation_unavailable', 'conflicted', 'not_applicable']
    score: ScoreLevel | None
    anchor_evidence: list[str]
    candidate_evidence: list[str]
    reason: str = Field(min_length=1)

    @field_validator('score', mode='before')
    @classmethod
    def numeric_score(cls, value):
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
            raise ValueError('Facet score must be a numeric score level or null.')
        return value

    @model_validator(mode='after')
    def coherent(self):
        if (self.state == 'assessed') != (self.score is not None):
            raise ValueError('Only an assessed facet has a numeric score.')
        if not self.reason.strip():
            raise ValueError('Every facet needs a concrete reason, including missing evidence.')
        for refs in (self.anchor_evidence, self.candidate_evidence):
            if len(refs) != len(set(refs)):
                raise ValueError('Evidence refs must be unique within each side.')
        return self

@_preserve_class('RelationCriterionJudgment', 'fashion_recommendation_v2.schemas.relation_scoring')
class RelationCriterionJudgment(StrictBaseModel):
    criterion: Criterion
    facets: list[RelationFacetJudgment] = Field(min_length=1)

@_preserve_class('RelationCriterionScore', 'fashion_recommendation_v2.schemas.relation_scoring')
class RelationCriterionScore(StrictBaseModel):
    criterion: Criterion
    weight: float = Field(gt=0, le=1)
    score: float | None = Field(ge=0, le=1)
    evidence_coverage: float = Field(ge=0, le=1)
    effective_weight: float = Field(ge=0, le=1)

@_preserve_class('MetadataFallbackV5', 'fashion_recommendation_v2.schemas.relation_scoring')
class MetadataFallbackV5(StrictBaseModel):
    facet: Facet
    side: Literal['anchor', 'candidate']
    reason: str = Field(min_length=1, description='Explain which facet-specific information the available image observation lacks; not just a metadata preference.')

@_preserve_class('RelationScoreBreakdown', 'fashion_recommendation_v2.schemas.relation_scoring')
class RelationScoreBreakdown(StrictBaseModel):
    policy: Literal['relation_v3_weighted_v1', 'relation_v4_weighted_v1', 'relation_v5_weighted_v1', 'relation_v9_weighted_v1']
    metadata_fallbacks_v5: list[MetadataFallbackV5] | None = None

    @model_serializer(mode='wrap')
    def serialize_version(self, handler):
        data = handler(self)
        if self.metadata_fallbacks_v5 is None:
            data.pop('metadata_fallbacks_v5', None)
        return data
    judgments: list[RelationCriterionJudgment]
    criteria: list[RelationCriterionScore]
    evidence_coverage: float = Field(ge=0, le=1)
    score: float | None = Field(ge=0, le=1)
    null_reasons: list[str]
# Relation evaluation facets, distinct from Search attribute evidence policy.
METADATA_ONLY_RELATION_FACETS = frozenset({'material', 'season'})

@_preserve_function('fallback_error', 'fashion_recommendation_v2.schemas.relation_scoring')
def fallback_error(item_id, facet, side, reason, correction):
    return ValueError(f'{item_id}/{facet}/{side}: metadata_fallbacks: {reason} Correction: {correction}')
