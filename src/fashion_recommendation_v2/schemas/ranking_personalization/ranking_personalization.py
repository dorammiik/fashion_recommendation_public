"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- ranking_personalization_v11 ----

"""Versioned, text-only personalized suitability contract."""
from typing import Literal
from pydantic import Field
from pydantic import PrivateAttr
from pydantic import model_validator
from fashion_recommendation_v2.schemas.base import StrictBaseModel
from fashion_recommendation_v2.schemas.preference.interpretation.preference_interpretation import PreferenceAttribute
Judgment = Literal['supports', 'opposes', 'neutral', 'unknown', 'conflicted', 'not_applicable']
Reason = Literal['preference_supported', 'preference_opposed', 'no_clear_effect', 'insufficient_product_evidence', 'conflicting_product_evidence', 'out_of_scope', 'request_attribute_excluded', 'request_overlap_combination']
Fit = Literal['strong_mismatch', 'mismatch', 'neutral', 'match', 'strong_match', 'undetermined']
Level = Literal['low', 'medium', 'high']

@_preserve_class('InterpretationAssessment', 'fashion_recommendation_v2.schemas.ranking_personalization.ranking_personalization_v11')
class InterpretationAssessment(StrictBaseModel):
    interpretation_id: str
    judgment: Judgment
    reason_code: Reason
    used_attributes: list[PreferenceAttribute]
    used_detail_keys: list[str]
    product_evidence_refs: list[str]
    explanation: str = Field(min_length=1)

@_preserve_class('PreferenceAssessmentV11', 'fashion_recommendation_v2.schemas.ranking_personalization.ranking_personalization_v11')
class PreferenceAssessmentV11_v11(StrictBaseModel):
    item_id: str
    interpretation_assessments: list[InterpretationAssessment]
    overall_fit: Fit
    assessment_confidence: Level
    explanation: str = Field(min_length=1)
    _model_response: dict | None = PrivateAttr(default=None)
    _model_response_text: str | None = PrivateAttr(default=None)

@_preserve_class('PreferenceAssessmentInputV11', 'fashion_recommendation_v2.schemas.ranking_personalization.ranking_personalization_v11')
class PreferenceAssessmentInputV11_v11(StrictBaseModel):
    item_id: str
    user_request: str
    resolved_requirements: dict
    frozen_profile: dict
    categories: dict
    evidence_index: dict
    product_evidence: dict
    excluded_attributes: list[str]
    validation_feedback: list[str] = Field(default_factory=list)
    previous_response: dict | None = None

@_preserve_class('PreferenceExecutionV11', 'fashion_recommendation_v2.schemas.ranking_personalization.ranking_personalization_v11')
class PreferenceExecutionV11(StrictBaseModel):
    execution_status: Literal['completed', 'skipped', 'failed', 'not_evaluated']
    preference_score: float | None = Field(ge=0, le=1)
    p_active: bool
    inactive_reason: Literal['cold', 'no_eligible_candidates', 'profile_empty', 'profile_not_found', 'no_applicable_preference', 'conflicting_product_evidence', 'insufficient_product_evidence', 'candidate_budget', 'evaluation_failed'] | None
    excluded_reason: Literal['preference_evaluation_failed', 'preference_not_evaluated'] | None = None
    assessment: PreferenceAssessmentV11_v11 | None = None
    attempts: list[dict]
    applied_weights: dict[str, float] | None = None
    scores: dict | None = None
    profile_evidence_refs: list[str] = Field(default_factory=list)
    retry_not_run_reason: Literal['call_budget'] | None = None

    @model_validator(mode='after')
    def coherent_execution(self):
        if self.execution_status == 'completed':
            if self.assessment is None or self.excluded_reason is not None:
                raise ValueError('Completed requires an assessment and no failure exclusion')
        elif self.assessment is not None or self.p_active or self.preference_score is not None:
            raise ValueError('Noncompleted execution cannot have a valid assessment/P')
        if self.execution_status in {'failed', 'not_evaluated'} and self.excluded_reason is None:
            raise ValueError('Failed/unevaluated needs an exclusion reason')
        return self


# ---- ranking_personalization_v12 ----

"""v12 keeps the v11 wire fields; scope-first semantics are versioned separately."""
PreferenceAssessmentV11 = PreferenceAssessmentV11_v11
PreferenceAssessmentInputV11 = PreferenceAssessmentInputV11_v11

@_preserve_class('PreferenceAssessmentV12', 'fashion_recommendation_v2.schemas.ranking_personalization.ranking_personalization_v12')
class PreferenceAssessmentV12(PreferenceAssessmentV11):
    """Scope precedence v12 response, with the same structural contract."""

@_preserve_class('PreferenceAssessmentInputV12', 'fashion_recommendation_v2.schemas.ranking_personalization.ranking_personalization_v12')
class PreferenceAssessmentInputV12(PreferenceAssessmentInputV11):
    """Explicit prompt routing without adding model-visible control fields."""


# ---- ranking_personalization_v16 ----

"""Minimal preference response; historical assessment schemas stay unchanged."""
from typing import ClassVar
InterpretationAssessment_ranking_personalization_v16 = InterpretationAssessment
PreferenceAssessmentV11_ranking_personalization_v16 = PreferenceAssessmentV11_v11
PreferenceExecutionV11_ranking_personalization_v16 = PreferenceExecutionV11
PreferenceAssessmentInputV12_ranking_personalization_v16 = PreferenceAssessmentInputV12

@_preserve_class('InterpretationAssessmentV16', 'fashion_recommendation_v2.schemas.ranking_personalization.ranking_personalization_v16')
class InterpretationAssessmentV16_ranking_personalization_v16(InterpretationAssessment_ranking_personalization_v16):
    used_attributes: ClassVar[None] = None
    used_detail_keys: ClassVar[None] = None

@_preserve_class('PreferenceAssessmentV16', 'fashion_recommendation_v2.schemas.ranking_personalization.ranking_personalization_v16')
class PreferenceAssessmentV16_ranking_personalization_v16(PreferenceAssessmentV11_ranking_personalization_v16):
    interpretation_assessments: list[InterpretationAssessmentV16_ranking_personalization_v16]

@_preserve_class('PreferenceAssessmentInputV16', 'fashion_recommendation_v2.schemas.ranking_personalization.ranking_personalization_v16')
class PreferenceAssessmentInputV16_ranking_personalization_v16(PreferenceAssessmentInputV12_ranking_personalization_v16):
    """excluded_attributes contains only the retained size exclusion."""

@_preserve_class('PreferenceExecutionV16', 'fashion_recommendation_v2.schemas.ranking_personalization.ranking_personalization_v16')
class PreferenceExecutionV16_ranking_personalization_v16(PreferenceExecutionV11_ranking_personalization_v16):
    assessment: PreferenceAssessmentV16_ranking_personalization_v16 | None = None
