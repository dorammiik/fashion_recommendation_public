"""Evidence alignment by LLM; applicability, aggregation and scores by code."""
from fashion_recommendation_v2.module_compat import import_module as _role_module
from math import isclose
from fashion_recommendation_v2.schemas.preference_profile import PreferenceGroup
from fashion_recommendation_v2.schemas.stylist import StylistDetailValue_base as StylistDetailValue
from fashion_recommendation_v2.agents.preference_scoring import score_candidate
from fashion_recommendation_v2.agents.orchestrator_preferences import has_evidence


def request_profile(source):
    if source.preference_profile is None:
        return None
    profile = source.preference_profile.model_copy(deep=True)
    if source.preference_category and source.preference_category not in profile.by_category:
        raise ValueError('Unknown ranking preference category')
    local = profile.by_category.get(source.preference_category, PreferenceGroup())
    selected = {}
    for group in (profile.global_preferences, local):
        for attr in {f.attribute for f in group.features if has_evidence(f)}:
            selected[attr] = [f for f in group.features if f.attribute == attr and has_evidence(f)]
    excluded = {'size'} | {r.attribute for r in source.candidate_set.resolved_requirements.requirements
                           if r.source == 'user'}
    if excluded & {'category', 'product_type', 'product_group', 'type'}:
        excluded.add('category_path')
    features = [f for attr, values in selected.items() if attr not in excluded for f in values]
    # Conservatively suppress free keywords when explicit user conditions could overlap them.
    keywords = [] if excluded & {'color', 'fit', 'pattern', 'material', 'brand', 'detail', 'theme', 'occasion', 'season', 'strength'} else [
        k for k in (local.title_keywords or profile.global_preferences.title_keywords)
        if k.equivalent_attribute is None and has_evidence(k)]
    attribute_values = {value.casefold() for f in features
                        for value in (f.value.values if hasattr(f.value, 'values') else [f.value])}
    keywords = [k for k in keywords if k.normalized.casefold() not in attribute_values]
    profile.global_preferences = PreferenceGroup(features=features, title_keywords=keywords)
    profile.by_category = {}
    profile.summary = None
    return profile if features or keywords else None


def vocabulary(profile):
    if profile is None:
        return []
    return ([{'attribute': f.attribute, 'value': f.value.model_dump() if hasattr(f.value, 'model_dump') else f.value}
             for f in profile.global_preferences.features] +
            [{'attribute': 'title_keywords', 'value': k.normalized} for k in profile.global_preferences.title_keywords])


from fashion_recommendation_v2.search.product_validation import validate_observations


def calculate(profile, observations, conflicts=()):
    if profile is None:
        return dict(preference_score=None, attribute_scores={}, evidence_refs=[])
    observed = {}
    disputed = {c.attribute for c in conflicts}
    for obs in observations:
        if obs.attribute in disputed:
            continue  # Conflicting product evidence is unknown, hence neutral.
        if isinstance(obs.value, StylistDetailValue):
            observed.setdefault('detail', {}).setdefault(obs.value.key, []).extend(obs.value.values)
        else:
            observed.setdefault(obs.attribute, []).extend(obs.value if isinstance(obs.value, list) else [obs.value])
    scored = score_candidate(profile, observed)
    refs = set()
    for f in profile.global_preferences.features:
        if f.attribute == 'detail':
            matches = set(f.value.values) & set(observed.get('detail', {}).get(f.value.key, []))
        else:
            matches = f.value in observed.get(f.attribute, [])
        if matches:
            refs.update(f.evidence_refs)
    for k in profile.global_preferences.title_keywords:
        if k.normalized in observed.get('title_keywords', []):
            refs.update(k.evidence_refs)
    return dict(preference_score=scored['preference_score'], attribute_scores=scored['attribute_scores'], evidence_refs=sorted(refs))


def observations_from_search(analysis, item, profile):
    """Reuse supported Search observations; unknown preference attributes stay neutral."""
    from fashion_recommendation_v2.schemas.product_evidence import PreferenceObservation
    from fashion_recommendation_v2.agents.ranking_runner import normalize
    allowed = {v['attribute'] for v in vocabulary(profile)}
    observations = []
    seen = set()
    from fashion_recommendation_v2.search.evidence_projection import semantic_facts
    for feature in semantic_facts(analysis):
        if feature.attribute not in allowed:
            continue
        if analysis.evaluation_policy in {'v36', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'} and feature.attribute == 'material':
            row = next(a for a in analysis.attributes if a.attribute == 'material')
            if row.metadata.value is None or not row.metadata.evidence_fields:
                continue
            feature = feature.model_copy(update=dict(value=row.metadata.value,
                evidence_fields=list(row.metadata.evidence_fields), evidence=list(row.metadata.evidence), image_evidence=[]))
        if analysis.evaluation_policy in {'v36', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'} and feature.attribute in {'material', 'brand', 'category_path', 'title_keywords'} and not feature.evidence_fields:
            continue  # Preserve Preference's metadata-only policy, independently of R.
        observations.append(PreferenceObservation(attribute=feature.attribute, value=feature.value,
            evidence_fields=feature.evidence_fields, evidence=feature.evidence, image_evidence=feature.image_evidence))
        seen.add(feature.attribute)
    metadata_attributes = allowed - seen - {'title_keywords', 'detail', 'size'}
    if analysis.evaluation_policy in {'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
        # Marketplace category paths are original retrieval metadata, not
        # mapper-inferred garment characteristics. Preserve this preference signal.
        metadata_attributes &= {'category_path'}
    for attribute in sorted(metadata_attributes):
        value = getattr(item, attribute, None)
        if value and isinstance(value, (str, list)):
            observations.append(PreferenceObservation(attribute=attribute, value=value,
                evidence_fields=[attribute], evidence=[str(value)]))
    if 'title_keywords' in allowed:
        title = ' ' + normalize(item.title) + ' '
        terms = [v['value'] for v in vocabulary(profile) if v['attribute'] == 'title_keywords'
                 and ' ' + normalize(v['value']) + ' ' in title]
        if terms:
            observations.append(PreferenceObservation(attribute='title_keywords', value=list(dict.fromkeys(terms)),
                evidence_fields=['title'], evidence=[item.title]))
    validate_observations(observations, item)
    return observations


def validate_ranked_preference(ranked, source, item, *, scoring_policy_version='ranking_v0.4_preference'):
    validate_observations(ranked.preference_observations, item)
    profile = request_profile(source)
    allowed = {v['attribute'] for v in vocabulary(profile)}
    if any(obs.attribute not in allowed for obs in ranked.preference_observations):
        raise ValueError('Preference observations outside request scope')
    from fashion_recommendation_v2.schemas.ranking import ScoringInputV11
    if isinstance(source, ScoringInputV11):
        from fashion_recommendation_v2.ranking.personalization import score_injection
        expected = score_injection(source, ranked.item_id)
    else:
        expected = calculate(profile, ranked.preference_observations, ranked.conflicts)
    score = ranked.scores.preference_score
    if (score is None) != (expected['preference_score'] is None) or (
        score is not None and not isclose(score, expected['preference_score'], abs_tol=1e-9)
    ):
        raise ValueError('Preference score must match stored evidence and observations')
    if ranked.preference_attribute_scores != expected['attribute_scores'] or ranked.preference_evidence_refs != expected['evidence_refs']:
        raise ValueError('Preference explanation evidence mismatch')
    s = ranked.scores
    if source.candidate_set.search_policy_version in {'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
        from fashion_recommendation_v2.ranking.ranking_contracts import scoring_for_policy
        scorer = scoring_for_policy(scoring_policy_version)
        base, record = scorer.routed_score(s.request_relevance_score, s.thumbnail_quality_score,
            s.ebay_best_match_score, score, source, ranked.item_id)
        relation = next((e for e in source.ralationRatio.evaluations if e.item_id == ranked.item_id), None) if source.ralationRatio else None
        if ranked.relation_evaluation != relation or s.relation_score != (relation.score if relation else None):
            raise ValueError('Ranking relation evidence must preserve the validated Relation output.')
        if s.application_v8 != record or not isclose(s.base_score, base, abs_tol=1e-9) or not isclose(s.final_score, base, abs_tol=1e-9):
            raise ValueError('v37 handoff score/activation/application mismatch.')
        return
    base = .8*s.request_relevance_score + .2*s.ebay_best_match_score if score is None else (
        .7*s.request_relevance_score + .2*score + .1*s.ebay_best_match_score)
    from fashion_recommendation_v2.schemas.ranking import RANKING_V0_POLICIES
    from fashion_recommendation_v2.schemas.ranking import RANKING_V1_POLICIES
    from fashion_recommendation_v2.schemas.ranking import RANKING_V2_POLICIES
    from fashion_recommendation_v2.schemas.ranking import RANKING_V4_POLICIES
    from fashion_recommendation_v2.schemas.ranking import RANKING_V5_POLICIES
    from fashion_recommendation_v2.schemas.ranking import RANKING_V6
    from fashion_recommendation_v2.schemas.ranking import RANKING_V6_RELATION
    from fashion_recommendation_v2.schemas.ranking import RANKING_V6_POLICIES
    from fashion_recommendation_v2.schemas.ranking import RANKING_V7
    from fashion_recommendation_v2.schemas.ranking import RANKING_V7_RELATION
    from fashion_recommendation_v2.schemas.ranking import RANKING_V7_POLICIES
    from fashion_recommendation_v2.schemas.ranking import RANKING_V9_POLICIES
    from fashion_recommendation_v2.schemas.ranking import RANKING_V8
    from fashion_recommendation_v2.schemas.ranking import RANKING_V8_RELATION
    from fashion_recommendation_v2.schemas.ranking import RANKING_V8_POLICIES
    if scoring_policy_version in RANKING_V0_POLICIES | RANKING_V1_POLICIES | RANKING_V2_POLICIES | RANKING_V4_POLICIES | RANKING_V5_POLICIES | RANKING_V6_POLICIES | RANKING_V7_POLICIES | RANKING_V8_POLICIES | RANKING_V9_POLICIES:
        if s.thumbnail_quality_score is None:
            raise ValueError('Ranking eval v0 requires a thumbnail quality score.')
        base = (.5*s.request_relevance_score + .3*s.thumbnail_quality_score + .2*s.ebay_best_match_score
                if score is None else .5*s.request_relevance_score + .2*score
                + .2*s.thumbnail_quality_score + .1*s.ebay_best_match_score)
    if scoring_policy_version in RANKING_V2_POLICIES | RANKING_V4_POLICIES | RANKING_V5_POLICIES | RANKING_V6_POLICIES | RANKING_V7_POLICIES | RANKING_V8_POLICIES | RANKING_V9_POLICIES and score is None:
        base = .55*s.request_relevance_score + .35*s.thumbnail_quality_score + .10*s.ebay_best_match_score
    relation = next((e for e in source.ralationRatio.evaluations if e.item_id == ranked.item_id), None) if source.ralationRatio else None
    if ranked.relation_evaluation != relation:
        raise ValueError('Ranking relation evidence must match the validated Relation output')
    expected_relation = relation.score if relation else None
    if s.relation_score != expected_relation:
        raise ValueError('Ranking relation score must match the validated Relation output')
    if scoring_policy_version in RANKING_V8_POLICIES | RANKING_V9_POLICIES:
        from fashion_recommendation_v2.ranking.ranking_contracts import scoring_for_policy
        scorer = scoring_for_policy(scoring_policy_version)
        base = scorer.base_score(s.request_relevance_score, s.thumbnail_quality_score, s.ebay_best_match_score, score)
        base, record = scorer.apply_relation(base, source, ranked.item_id)
        if s.application_v8 != record:
            raise ValueError('Ranking v8 score application must match the code policy and saved Relation evidence.')
    elif expected_relation is not None:
        base = .75 * base + .25 * expected_relation
    if not isclose(s.base_score, base, abs_tol=1e-9) or not isclose(s.final_score, max(0., base-s.diversity_penalty), abs_tol=1e-9):
        raise ValueError('Ranking cold/warm score formula mismatch')
