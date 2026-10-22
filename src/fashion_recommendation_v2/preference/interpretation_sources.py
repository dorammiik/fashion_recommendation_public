"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- interpretation_sources ----

"""One source definition for preparation, citation guidance, and storage checks."""
from fashion_recommendation_v2.preference.interpretation_references import fingerprint
from fashion_recommendation_v2.preference.interpretation_references import category
from fashion_recommendation_v2.preference.interpretation_references import validate_references
from fashion_recommendation_v2.schemas.preference.interpretation.preference_interpretation import InterpretationEvidence
SOURCE_GUIDANCE = '''Each evidence ID links an effective event to one stored observation.
Observations preserve metadata, image_observation and metadata_image_consistency separately.
Do not infer material composition from image texture. Conflict is uncertainty, not a merged fact.
No Q, V, request judgments, admission results, rank or raw_metadata are taste inputs.'''

@_preserve_function('source_observations', 'fashion_recommendation_v2.preference.interpretation_sources')
def source_observations(snapshot):
    result = {'item.title': {'text': snapshot.item.title}}
    if snapshot.item.category_path:
        result['item.category_path'] = {'value': snapshot.item.category_path}
    analysis = snapshot.search_analysis
    if analysis is not None:
        if not hasattr(analysis, 'attributes'):
            raise ValueError('Preference v1 requires source-separated Search analysis; use v0 for legacy analysis')
        for index, row in enumerate(analysis.attributes):
            result[f'search_analysis.attributes.{index}'] = {'attribute': row.attribute, 'metadata': row.metadata.model_dump(mode='json'), 'image_observation': row.image_observation.model_dump(mode='json') if row.image_observation else None, 'metadata_image_consistency': row.metadata_image_consistency.model_dump(mode='json')}
    else:
        # Preserve the existing no-Search compatibility evidence allowlist.
        from fashion_recommendation_v2.preference.observations import observations
        for obs in observations(snapshot):
            result.setdefault('legacy.' + obs.observation_id, {'field': obs.field, 'text': obs.text})
    return result

@_preserve_function('event_evidence', 'fashion_recommendation_v2.preference.interpretation_sources')
def event_evidence(event, snapshot):
    if (event.user_id, event.item_id, event.item_snapshot_id, event.session_id, event.request_id, event.recommendation_id, event.rank) != (snapshot.user_id, snapshot.item.item_id, snapshot.item_snapshot_id, snapshot.session_id, snapshot.request_id, snapshot.recommendation_id, snapshot.rank):
        raise ValueError('Event/snapshot ownership or identity mismatch')
    category_id, _ = category(snapshot)
    return [InterpretationEvidence(evidence_id='e_' + fingerprint([event.event_id, snapshot.item_snapshot_id, path, observation])[:32], user_id=event.user_id, event_id=event.event_id, item_snapshot_id=snapshot.item_snapshot_id, item_id=event.item_id, source_action=event.action, occurred_at=event.occurred_at, category_id=category_id, source_path=path, observation=observation) for path, observation in source_observations(snapshot).items()]
