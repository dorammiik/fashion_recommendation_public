"""Role-consolidated implementation; service contracts and behavior are preserved."""
from __future__ import annotations
from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function

# ---- search_ranking_observation_legacy ----
"""schemas.search.ranking_observation.search_ranking_observation_legacy: definitions relocated without semantic changes."""

from pydantic import Field as Field_legacy
from typing import Literal as Literal_legacy
from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_legacy
from pydantic import model_validator as model_validator_legacy

@_preserve_class('ThumbnailObservation', 'fashion_recommendation_v2.schemas.search.ranking_observation.search_ranking_observation_legacy')
class ThumbnailObservation(StrictBaseModel_legacy):
    __qualname__ = 'ThumbnailObservation'
    presentation: Literal_legacy['person_full', 'person_cropped', 'mannequin', 'flat_lay', 'hanger', 'other', 'unknown']
    background: Literal_legacy['plain', 'non_plain', 'unknown']
    mannequin_pose: Literal_legacy['upright', 'tilted', 'unknown']
    view_angle: Literal_legacy['front', 'oblique', 'front/oblique', 'other', 'unknown']
    product_clearly_visible: bool
    garment_neatly_arranged: bool
    evidence: str = Field_legacy(min_length=1)

    def quality(self):
        if self.presentation in {'person_full', 'person_cropped'}:
            return ('person', ('high' if self.presentation == 'person_full' else 'medium')
                    if self.product_clearly_visible else 'low')
        if self.presentation == 'hanger':
            return 'product_only', 'medium'
        if self.presentation == 'mannequin':
            high = (self.background == 'plain' and self.mannequin_pose == 'upright'
                    and self.view_angle in {'front', 'oblique', 'front/oblique'} and self.product_clearly_visible)
            return 'product_only', 'high' if high else 'medium'
        if self.presentation == 'flat_lay':
            return 'product_only', 'high' if self.background == 'plain' and self.product_clearly_visible and self.garment_neatly_arranged else 'low'
        return 'unknown', 'low'


@_preserve_class('ThumbnailObservationV8', 'fashion_recommendation_v2.schemas.search.ranking_observation.search_ranking_observation_legacy')
class ThumbnailObservationV8_legacy(StrictBaseModel_legacy):
    __qualname__ = 'ThumbnailObservationV8'
    photo_type: Literal_legacy['unknown', 'product_only', 'person']
    product_focus: Literal_legacy['unknown', 'full', 'partial']
    view_angle: Literal_legacy['unknown', 'front', 'side', 'back']
    support: Literal_legacy['unknown', 'hanger', 'mannequin', 'flat_lay']
    background: Literal_legacy['unknown', 'solid', 'two_color', 'three_color', 'multicolor']
    evidence: str = Field_legacy(min_length=1)

    def passes(self):
        if self.photo_type == 'person':
            return self.product_focus in {'full', 'partial'}
        return (self.photo_type == 'product_only' and self.support in {'hanger', 'mannequin', 'flat_lay'}
                and self.background in {'solid', 'two_color'} and self.view_angle in {'front', 'side', 'unknown'})


@_preserve_class('ThumbnailObservationV1', 'fashion_recommendation_v2.schemas.search.ranking_observation.search_ranking_observation_legacy')
class ThumbnailObservationV1_legacy(ThumbnailObservationV8_legacy):
    """Ranking v1 presentation observation; inherited Search admission is unchanged."""
    __qualname__ = 'ThumbnailObservationV1'

    thum_quality: Literal_legacy['met', 'mostly_met', 'partial', 'unknown', 'unmet'] | None
    thum_quality_evidence: str | None

    @model_validator_legacy(mode='after')
    def validate_presentation_quality(self):
        if self.photo_type == 'product_only':
            if self.thum_quality is None or not (self.thum_quality_evidence or '').strip():
                raise ValueError('Product-only thumbnails require thum_quality and visual evidence.')
        elif self.thum_quality is not None or self.thum_quality_evidence is not None:
            raise ValueError('thum_quality applies only to product_only; other photo types require null.')
        return self


@_preserve_class('ThumbnailObservationDraft', 'fashion_recommendation_v2.schemas.search.ranking_observation.search_ranking_observation_legacy')
class ThumbnailObservationDraft(StrictBaseModel_legacy):
    __qualname__ = 'ThumbnailObservationDraft'
    presentation: str
    background: str
    mannequin_pose: str
    view_angle: str
    product_clearly_visible: bool
    garment_neatly_arranged: bool
    evidence: str


# ---- search_ranking_observation_v5 ----
"""Separate Ranking observations; never overwrite the original Search admission data."""
import hashlib
import json
import re
from pydantic import Field
from pydantic import model_validator
from fashion_recommendation_v2.schemas.base import StrictBaseModel
ThumbnailObservationV1 = ThumbnailObservationV1_legacy
from fashion_recommendation_v2.schemas.search.retrieval.search_retrieval import ProductRecord
from fashion_recommendation_v2.schemas.search.requirements.search_requirements import ResolvedRequirements_legacy as ResolvedRequirements
from fashion_recommendation_v2.schemas.exposure_suitability import ExposureSuitability
from fashion_recommendation_v2.schemas.visual_confirmation import VisualConfirmationV5
from fashion_recommendation_v2.schemas.visual_confirmation import VisualConsistencyAuditV5
from fashion_recommendation_v2.schemas.visual_confirmation import visual_applicability


@_preserve_class('SearchImageObservationsOutputV5', 'fashion_recommendation_v2.schemas.search.ranking_observation.search_ranking_observation_v5')
class SearchImageObservationsOutputV5(StrictBaseModel):
    __qualname__ = 'SearchImageObservationsOutputV5'
    ranking_thumbnail_observation_v5: ThumbnailObservationV1 = Field(description=(
        'Person photos require support=unknown and BOTH thum_quality fields=null. '
        'Mannequin photos are product_only/support=mannequin. '
        'Hidden major garment regions forbid product_focus=full.'))
    visual_confirmation_v5: VisualConfirmationV5
    exposure_suitability: ExposureSuitability

    @model_validator(mode='after')
    def validate_cross_fields(self):
        thumb, visual = self.ranking_thumbnail_observation_v5, self.visual_confirmation_v5
        expected = {'person': 'person', 'mannequin': 'product_only', 'garment_only': 'product_only', 'unknown': 'unknown'}
        if thumb.photo_type != expected[visual.display_subject]:
            raise ValueError('Photo type must match the observed display subject; mannequins are product_only.')
        if (visual.display_subject == 'mannequin') != (thumb.support == 'mannequin'):
            raise ValueError('Mannequin display and support must agree.')
        if thumb.photo_type == 'person' and thumb.support != 'unknown':
            raise ValueError('Person photographs have no display support.')
        if thumb.product_focus == 'full' and visual.hidden_parts:
            raise ValueError('A garment with hidden major parts cannot be full.')
        if visual.hidden_parts and visual.overall_form_status == 'met':
            raise ValueError('Hidden major garment parts cannot fully confirm overall form.')
        return self


@_preserve_class('SearchImageObservationsInputV5', 'fashion_recommendation_v2.schemas.search.ranking_observation.search_ranking_observation_v5')
class SearchImageObservationsInputV5(StrictBaseModel):
    __qualname__ = 'SearchImageObservationsInputV5'
    item: ProductRecord
    resolved_requirements: ResolvedRequirements
    previous_observation: SearchImageObservationsOutputV5 | None
    correction_issues: list[str]


from fashion_recommendation_v2.search.observation_review import visual_review_questions
from fashion_recommendation_v2.search.observation_review import observation_hash


@_preserve_function('validate_reviewed_observation', 'fashion_recommendation_v2.schemas.search.ranking_observation.search_ranking_observation_v5')
def validate_reviewed_observation(item, requirements, observation, audit):
    observation = SearchImageObservationsOutputV5.model_validate(observation.model_dump())
    observation.visual_confirmation_v5.validate_against(requirements)
    audit = VisualConsistencyAuditV5.model_validate(audit.model_dump())
    for attempt in audit.attempts:
        if attempt.product_target_v26 is not None:
            target = attempt.product_target_v26
            if attempt.product_target_sha256_v26 != observation_hash(item, requirements, target):
                raise ValueError('Original product review target hash mismatch.')
            slot = target['model_response'][target['target_slot']]
            for original, derived in (('thumbnail_observation_v8', 'ranking_thumbnail_observation_v5'),
                    ('visual_confirmation_v5', 'visual_confirmation_v5'), ('exposure_suitability', 'exposure_suitability')):
                if slot[original] != attempt.observation[derived]:
                    raise ValueError('Ranking projection must match the originally reviewed product observation.')
        elif audit.review_policy == 'product_evaluation_v26_conditional' and attempt.review_source == 'llm':
            raise ValueError('v26 semantic review must preserve its original product response and schema.')
        if attempt.observation_sha256 != observation_hash(item, requirements, attempt.observation):
            raise ValueError('Semantic review snapshot hash mismatch.')
        if audit.review_policy in {'visual_consistency_v5_conditional', 'product_evaluation_v26_conditional'}:
            snapshot = SearchImageObservationsOutputV5.model_validate(attempt.observation)
            snapshot.visual_confirmation_v5.validate_against(requirements)
            expected_questions = visual_review_questions(snapshot, requirements)
            if (attempt.review_questions != expected_questions
                    or attempt.review_source != ('llm' if expected_questions else 'code')):
                raise ValueError('Conditional review routing/questions do not match the exact observation.')
    if (audit.attempts[-1].observation != observation.model_dump(mode='json')
            or audit.attempts[-1].observation_sha256 != observation_hash(item, requirements, observation)):
        raise ValueError('Semantic review must approve the exact final image observation.')
    return observation


# ---- search_ranking_observation_v1 ----
"""schemas.search.ranking_observation.search_ranking_observation_v1: definitions relocated without semantic changes."""

from pydantic import Field as Field_v1
from typing import Literal as Literal_v1
from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_v1
ThumbnailObservationV8_v1 = ThumbnailObservationV8_legacy
from pydantic import model_validator as model_validator_v1

@_preserve_class('ProductThumbnailQualityInputV1', 'fashion_recommendation_v2.schemas.search.ranking_observation.search_ranking_observation_v1')
class ProductThumbnailQualityInputV1(StrictBaseModel_v1):
    __qualname__ = 'ProductThumbnailQualityInputV1'
    item_id: str
    image_url: str
    frozen_observation: ThumbnailObservationV8_v1


@_preserve_class('ProductThumbnailQualityOutputV1', 'fashion_recommendation_v2.schemas.search.ranking_observation.search_ranking_observation_v1')
class ProductThumbnailQualityOutputV1(StrictBaseModel_v1):
    __qualname__ = 'ProductThumbnailQualityOutputV1'
    thum_quality: Literal_v1['met', 'mostly_met', 'partial', 'unknown', 'unmet']
    thum_quality_evidence: str = Field_v1(min_length=1)

    @model_validator_v1(mode='after')
    def nonblank_evidence(self):
        if not self.thum_quality_evidence.strip():
            raise ValueError('Thumbnail quality requires nonblank image evidence.')
        return self


# ---- search_ranking_observation_v4 ----
"""schemas.search.ranking_observation.search_ranking_observation_v4: definitions relocated without semantic changes."""

from fashion_recommendation_v2.schemas.exposure_suitability import ExposureSuitability as ExposureSuitability_v4
from typing import Literal
from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_v4
ThumbnailObservationV8 = ThumbnailObservationV8_legacy
from pydantic import model_validator as model_validator_v4

@_preserve_class('SearchImageObservationsInputV4', 'fashion_recommendation_v2.schemas.search.ranking_observation.search_ranking_observation_v4')
class SearchImageObservationsInputV4(StrictBaseModel_v4):
    __qualname__ = 'SearchImageObservationsInputV4'
    item_id: str
    image_url: str
    frozen_observation: ThumbnailObservationV8


@_preserve_class('SearchImageObservationsOutputV4', 'fashion_recommendation_v2.schemas.search.ranking_observation.search_ranking_observation_v4')
class SearchImageObservationsOutputV4(StrictBaseModel_v4):
    __qualname__ = 'SearchImageObservationsOutputV4'
    thum_quality: Literal['met', 'mostly_met', 'partial', 'unknown', 'unmet'] | None
    thum_quality_evidence: str | None
    exposure_suitability: ExposureSuitability_v4

    @model_validator_v4(mode='after')
    def paired_quality(self):
        if self.thum_quality is None:
            if self.thum_quality_evidence is not None:
                raise ValueError('Inactive quality requires null evidence.')
        elif not (self.thum_quality_evidence or '').strip():
            raise ValueError('Active thumbnail quality requires nonblank evidence.')
        return self
