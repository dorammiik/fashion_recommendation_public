"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- interpretation_input ----

"""Prepare facts only; no feature normalization, decay, scores, or inference."""
from collections import Counter
from fashion_recommendation_v2.preference.interpretation_sources import category
from fashion_recommendation_v2.preference.interpretation_sources import event_evidence
from fashion_recommendation_v2.schemas.preference.interpretation.preference_interpretation import InterpretationInput_v1 as InterpretationInput

@_preserve_function('prepare_input', 'fashion_recommendation_v2.preference.interpretation_input')
def prepare_input(source, *, version='v1'):
    if version not in {'v1', 'v2', 'v3', 'v4'}:
        raise ValueError('Unsupported interpretation input version')
    # Import at call time: storage also uses the source definition for validation.
    from fashion_recommendation_v2.storage.preference import replay_events
    events = [(seq, event) for seq, event in source.events if seq <= source.job.target_cursor]
    previous = source.previous_profile
    if not events or events[-1][0] <= (previous.processed_event_cursor if previous else 0):
        raise ValueError('No new receipt boundary to process')
    if len({seq for seq, _ in events}) != len(events) or sorted((seq for seq, _ in events)) != [seq for seq, _ in events]:
        raise ValueError('Receipt sequence must be unique and ordered')
    if len({e.event_id for _, e in events}) != len(events):
        raise ValueError('Duplicate event IDs')
    if previous and previous.user_id != source.job.user_id:
        raise ValueError('Previous profile owner mismatch')
    for _, event in events:
        if event.user_id != source.job.user_id or event.occurred_at > source.as_of or event.received_at > source.as_of:
            raise ValueError('Event ownership/time mismatch')
        snapshot = source.snapshots[event.item_snapshot_id]
        if snapshot.captured_at > event.occurred_at:
            raise ValueError('Interaction precedes snapshot')
        # Includes identity checks, even for canceled events.
        event_evidence(event, snapshot)
    effective = replay_events([e for _, e in events])
    categories, products, evidence = ({}, [], [])
    for sid in dict.fromkeys((e.item_snapshot_id for e in effective)):
        snapshot = source.snapshots[sid]
        group = [e for e in effective if e.item_snapshot_id == sid]
        cid, path = category(snapshot)
        if cid:
            entry = categories.setdefault(cid, dict(description=path, snapshot_ids=[]))
            entry['snapshot_ids'].append(sid)
        products.append(dict(snapshot_id=sid, item_id=snapshot.item.item_id, category_id=cid, events=[dict(event_id=e.event_id, action=e.action, occurred_at=e.occurred_at.isoformat(), session_id=e.session_id) for e in group], action_counts=dict(Counter((e.action for e in group))), distinct_item_count=1, distinct_session_count=len({e.session_id for e in group})))
        for event in group:
            evidence.extend(event_evidence(event, snapshot))
    # Never carry v0 computed feature statistics into the v1 inference input.
    old = previous.model_dump(mode='json') if previous and previous.schema_version in ({'2.0', '3.0'} if version in {'v2', 'v3', 'v4'} else {'2.0'}) else None
    input_schema, extra = (InterpretationInput, {})
    if version in {'v2', 'v3', 'v4'}:
        from fashion_recommendation_v2.schemas.preference.interpretation.preference_interpretation import InterpretationInput_v2 as InputV2
        from fashion_recommendation_v2.preference.interpretation_attributes import detail_keys
        input_schema, extra = (InputV2, {'allowed_detail_keys': detail_keys(evidence)})
    return (input_schema(as_of=source.as_of, categories=categories, products=products, evidence=evidence, previous_profile=old, **extra), events[-1][0])
