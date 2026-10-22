"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- preference_scoring ----

"""Deterministic replay aggregation, current-time view, and equal-weight candidate score."""
from collections import defaultdict
from datetime import timedelta
import json
from math import fsum
from uuid import uuid5
from uuid import NAMESPACE_URL
from fashion_recommendation_v2.schemas.preference_profile import DetailPreference
from fashion_recommendation_v2.schemas.preference_profile import EventCounts
from fashion_recommendation_v2.schemas.preference_profile import FeaturePreference
from fashion_recommendation_v2.schemas.preference_profile import PreferenceGroup
from fashion_recommendation_v2.schemas.preference_profile import PreferenceProfile
from fashion_recommendation_v2.schemas.preference_profile import PreferenceWindow
from fashion_recommendation_v2.schemas.preference_profile import TitleKeyword
from fashion_recommendation_v2.schemas.preference_profile import utc
from fashion_recommendation_v2.schemas.preference import PreferenceEvidence
WEIGHTS = {'click': 0.2, 'like': 1.0, 'dislike': -1.0, 'purchase': 1.5}

@_preserve_function('window', 'fashion_recommendation_v2.agents.preference_scoring')
def window(events, now, half_life):
    positive, negative = ([], [])
    for event in events:
        days = (now - event.occurred_at).total_seconds() / 86400
        if days < 0:
            raise ValueError('Cannot score future events')
        contribution = WEIGHTS[event.action] * 2 ** (-days / half_life)
        (positive if contribution > 0 else negative).append(abs(contribution))
    p, n = (fsum(positive), fsum(negative))
    if p + n == 0:
        return PreferenceWindow()
    score = (p - n) / (p + n + 1)
    return PreferenceWindow(positive_mass=p, negative_mass=n, score=score, strength='low' if abs(score) < 0.25 else 'medium' if abs(score) < 0.6 else 'high')

@_preserve_function('feature_key', 'fashion_recommendation_v2.agents.preference_scoring')
def feature_key(attribute, value):
    return attribute + ':' + (value.model_dump_json() if isinstance(value, DetailPreference) else value)

@_preserve_function('build_evidence', 'fashion_recommendation_v2.agents.preference_scoring')
def build_evidence(events, analyses):
    result = []
    for event in events:
        analysis = analyses[event.item_snapshot_id]
        observations = {o.observation_id: o for o in analysis.observations}
        for feature in analysis.features:
            value = DetailPreference(key=feature.detail_key, values=[feature.value]) if feature.attribute == 'detail' else feature.value
            refs = [observations[r] for r in feature.observation_ids]
            images = []
            # Image observation indices and original URL/text are expanded by runner after construction.
            fields = sorted({o.field for o in refs if not o.field.startswith('image:')})
            eid = uuid5(NAMESPACE_URL, event.event_id + '/' + feature_key(feature.attribute, value)).hex
            result.append(PreferenceEvidence(evidence_id=eid, user_id=event.user_id, event_id=event.event_id, item_snapshot_id=event.item_snapshot_id, source_action=event.action, attribute=feature.attribute, value=value, category=analysis.category, metadata_fields=fields, image_observations=images, explanation=feature.explanation))
        for keyword in analysis.keywords:
            eid = uuid5(NAMESPACE_URL, event.event_id + '/keyword/' + keyword.normalized).hex
            result.append(PreferenceEvidence(evidence_id=eid, user_id=event.user_id, event_id=event.event_id, item_snapshot_id=event.item_snapshot_id, source_action=event.action, attribute='title_keywords', value=keyword.normalized, category=analysis.category, original_forms=[keyword.original], equivalent_attribute=keyword.equivalent_attribute, metadata_fields=['title'], explanation='Observed title term; item reaction, not an explicit attribute statement.'))
    return result

@_preserve_function('build_profile', 'fashion_recommendation_v2.agents.preference_scoring')
def build_profile(user_id, version, cursor, events, evidence, *, now, updated_at=None):
    now = utc(now)
    by_id = {e.event_id: e for e in events}
    groups = defaultdict(lambda: defaultdict(list))
    for entry in evidence:
        if entry.event_id not in by_id:
            continue
        key = feature_key(entry.attribute, entry.value)
        groups['global'][key].append(entry)
        if entry.category:
            groups[entry.category][key].append(entry)

    def group(entries):
        features, keywords = ([], [])
        for key, refs in sorted(entries.items()):
            unique = {r.event_id: by_id[r.event_id] for r in refs}
            history = list(unique.values())
            if not history:
                continue
            first = refs[0]
            short, long = (window(history, now, 14), window(history, now, 90))
            items = len({e.item_id for e in history})
            sessions = len({e.session_id for e in history})
            if first.attribute == 'title_keywords':
                keywords.append(TitleKeyword(normalized=first.value, original_forms=sorted({v for r in refs for v in r.original_forms}), distinct_item_count=items, evidence_refs=sorted({r.evidence_id for r in refs}), short_term=short, long_term=long, equivalent_attribute=first.equivalent_attribute))
            else:

                def counts(recent=False):
                    return EventCounts(**{a: sum((e.action == a and (not recent or now - timedelta(days=30) <= e.occurred_at <= now) for e in history)) for a in WEIGHTS})
                features.append(FeaturePreference(attribute=first.attribute, value=first.value, short_term=short, long_term=long, confidence=0.7 * items / (items + 3) + 0.3 * sessions / (sessions + 2), total=counts(), recent_30d=counts(True), distinct_item_count=items, distinct_session_count=sessions, last_interaction_at=max((e.occurred_at for e in history)), evidence_refs=sorted({r.evidence_id for r in refs})))
        strongest = sorted((f for f in features if f.attribute != 'size'), key=lambda f: abs(combined(f)), reverse=True)[:3]
        summary = '; '.join((f'{f.attribute}={(f.value.model_dump_json() if isinstance(f.value, DetailPreference) else f.value)}: ' + ('선호 경향' if combined(f) > 0 else '비선호 경향' if combined(f) < 0 else '반응 혼재') for f in strongest)) or None
        return PreferenceGroup(features=features, title_keywords=keywords, summary=summary)
    global_group = group(groups.pop('global', {}))
    return PreferenceProfile(user_id=user_id, profile_version=version, processed_event_cursor=cursor, updated_at=updated_at or now, as_of=now, **{'global': global_group}, by_category={k: group(v) for k, v in sorted(groups.items())}, summary=global_group.summary)

@_preserve_function('combined', 'fashion_recommendation_v2.agents.preference_scoring')
def combined(feature):
    return 0.4 * (feature.short_term.score or 0) + 0.6 * (feature.long_term.score or 0)

@_preserve_function('score_candidate', 'fashion_recommendation_v2.agents.preference_scoring')
def score_candidate(profile, observed, *, category=None, excluded_attributes=()):
    """Canonical observed values from the caller; no request interpretation here.

    observed={'color':['black'], 'detail':{'closure':['zipper']}, 'title_keywords':['graphic']}
    Caller excludes signals conflicting with the current request. None means cold.
    """
    local = profile.by_category.get(category, PreferenceGroup())
    selected = {}
    for group in [profile.global_preferences, local]:
        attrs = {f.attribute for f in group.features}
        for attr in attrs:
            selected[attr] = [f for f in group.features if f.attribute == attr]
    scores = {}
    for attr, features in selected.items():
        if attr == 'size' or attr in excluded_attributes:
            continue
        values = observed.get(attr, {} if attr == 'detail' else [])
        if attr == 'detail':
            keys = sorted({f.value.key for f in features})
            per_key = []
            for key in keys:
                candidates = values.get(key, []) if isinstance(values, dict) else []
                lookup = {v: combined(f) for f in features if f.value.key == key for v in f.value.values}
                per_key.append(fsum((lookup.get(v, 0) for v in set(candidates))) / len(set(candidates)) if candidates else 0)
            scores[attr] = fsum(per_key) / len(per_key) if per_key else 0
        else:
            lookup = {f.value: combined(f) for f in features}
            scores[attr] = fsum((lookup.get(v, 0) for v in set(values))) / len(set(values)) if values else 0
    keywords = local.title_keywords or profile.global_preferences.title_keywords
    keywords = [k for k in keywords if k.equivalent_attribute is None]
    if keywords and 'title_keywords' not in excluded_attributes:
        lookup = {k.normalized: combined(k) for k in keywords}
        values = set(observed.get('title_keywords', []))
        scores['title_keywords'] = fsum((lookup.get(v, 0) for v in values)) / len(values) if values else 0
    return {'preference_score': (fsum(scores.values()) / len(scores) + 1) / 2 if scores else None, 'attribute_scores': scores, 'mode': 'warm' if scores else 'cold'}
