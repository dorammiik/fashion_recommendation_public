"""Role-consolidated implementation; service contracts and behavior are preserved."""
from __future__ import annotations
from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function

# ---- ranking_observations_v7 ----
"""One availability policy for Ranking generation, replay and output validation."""
from fashion_recommendation_v2.schemas.ranking import require_exposure
from fashion_recommendation_v2.schemas.ranking import require_visual_confirmation
from fashion_recommendation_v2.schemas.ranking import VisualConfirmationAssessmentV7
from fashion_recommendation_v2.schemas.ranking import ObservationUnavailableV7
from fashion_recommendation_v2.schemas.ranking import ThumbnailQualityAssessmentV2
from fashion_recommendation_v2.schemas.search.ranking_observation.search_ranking_observation import ThumbnailObservationV1_legacy as ThumbnailObservationV1


@_preserve_function('observation_assessments', 'fashion_recommendation_v2.tools.ranking_observations_v7')
def observation_assessments(candidate, requirements):
    # Identity and exposure are eligibility contracts, never availability fallbacks.
    require_exposure(candidate)
    analysis = candidate.search_analysis
    try:
        reviewed = require_visual_confirmation(candidate, requirements)
    except ValueError as exc:
        absent = [name for name in ('ranking_thumbnail_observation_v5',
            'visual_confirmation_v5', 'visual_consistency_v5') if getattr(analysis, name) is None]
        diagnostic = ObservationUnavailableV7(
            reason='validation_failed' if analysis.ranking_visual_error_v5 or not absent else 'missing_response',
            details=([analysis.ranking_visual_error_v5] if analysis.ranking_visual_error_v5 else [])
                + ([f'Missing: {", ".join(absent)}'] if absent else []) + [str(exc)], affected=['Q', 'V'])
        confirmation = VisualConfirmationAssessmentV7.unavailable(diagnostic)
        # Computational fallback only. Never write it into Search's observations,
        # raw response or audit, or claim that the model saw an unknown image.
        thumbnail = ThumbnailObservationV1(photo_type='unknown', product_focus='unknown',
            view_angle='unknown', support='unknown', background='unknown',
            thum_quality=None, thum_quality_evidence=None,
            evidence='Code fallback: observation_unavailable; no validated Q observation.')
    else:
        confirmation = VisualConfirmationAssessmentV7.from_observation(reviewed.observation)
        thumbnail = analysis.ranking_thumbnail_observation_v5
    return confirmation, ThumbnailQualityAssessmentV2.from_observation(thumbnail)
