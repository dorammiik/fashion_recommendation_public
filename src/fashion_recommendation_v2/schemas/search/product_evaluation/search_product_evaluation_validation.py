"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- search_product_evaluation_validation ----

"""Shared definitions moved unchanged from their former owner."""
from pydantic import Field
from fashion_recommendation_v2.schemas.base import StrictBaseModel
from fashion_recommendation_v2.schemas.price import PriceConversion
from fashion_recommendation_v2.schemas.search.retrieval.search_retrieval import ProductRecord
from fashion_recommendation_v2.schemas.search.requirements.search_requirements import ResolvedRequirements_legacy as ResolvedRequirements
from fashion_recommendation_v2.schemas.product_evidence import HardConstraintAssessment
from fashion_recommendation_v2.schemas.product_evidence import RankingItemIssue
from fashion_recommendation_v2.schemas.product_evidence import PreferenceObservation
from fashion_recommendation_v2.schemas.product_evidence import RequirementJudgment
from fashion_recommendation_v2.schemas.product_evidence import EvidenceConflict
from fashion_recommendation_v2.schemas.product_evidence import DiversityFeature

@_preserve_class('EvaluationItem', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_validation')
class EvaluationItem(StrictBaseModel):
    item: ProductRecord
    hard_constraint_assessments: list[HardConstraintAssessment]

@_preserve_class('EvaluationBatchInput', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_validation')
class EvaluationBatchInput(StrictBaseModel):
    user_request: str
    resolved_requirements: ResolvedRequirements
    price_conversion: PriceConversion | None = None
    items: list[EvaluationItem]
    preference_vocabulary: list[dict] = Field(default_factory=list)
    feature_vocabulary: list[dict] = Field(default_factory=list)
    validation_feedback: list[RankingItemIssue] = Field(default_factory=list)

@_preserve_class('ItemJudgments', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_validation')
class ItemJudgments(StrictBaseModel):
    item_id: str
    judgments: list[RequirementJudgment]
    conflicts: list[EvidenceConflict]
    diversity_features: list[DiversityFeature]
    preference_features: list[PreferenceObservation] = Field(default_factory=list)

@_preserve_class('EvaluationBatchOutput', 'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_validation')
class EvaluationBatchOutput(StrictBaseModel):
    items: list[ItemJudgments]
