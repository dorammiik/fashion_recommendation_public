"""Validate LLM-selected applicability, then select a detached request view."""
from fashion_recommendation_v2.module_compat import import_module as _role_module
from fashion_recommendation_v2.schemas.preference_profile import PreferenceGroup


def has_evidence(feature):
    return bool(feature.evidence_refs) and any(
        window.positive_mass + window.negative_mass > 0
        for window in (feature.short_term, feature.long_term)
    )


def select_profile(profile, assessment):
    if profile is None:
        if assessment.preference_attributes or assessment.use_title_keywords or assessment.preference_category:
            raise ValueError('Cannot select preferences without a stored profile')
        return None
    category = assessment.preference_category
    if category is not None and category not in profile.by_category:
        raise ValueError('Unknown preference category')
    if 'size' in assessment.preference_attributes:
        raise ValueError('Size is excluded from preference ranking')
    global_group = profile.global_preferences
    local = profile.by_category.get(category, PreferenceGroup())
    features = []
    for attribute in dict.fromkeys(assessment.preference_attributes):
        selected = [f for f in local.features if f.attribute == attribute]
        selected = selected or [f for f in global_group.features if f.attribute == attribute]
        if not selected:
            raise ValueError('Selected preference has no evidence')
        features.extend(f.model_copy(deep=True) for f in selected if has_evidence(f))
    keywords = []
    if assessment.use_title_keywords:
        keywords = [k.model_copy(deep=True) for k in (local.title_keywords or global_group.title_keywords)
                    if k.equivalent_attribute is None and has_evidence(k)]
    if not features and not keywords:
        return None
    view = profile.model_copy(deep=True)
    # Flatten selected category/global attributes, so consumers never count both.
    view.global_preferences = PreferenceGroup(features=features, title_keywords=keywords)
    view.by_category = {}
    view.summary = None
    return view
