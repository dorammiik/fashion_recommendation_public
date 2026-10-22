"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- preference_service ----

"""Trusted service boundary: browser events reference server-published snapshots."""
from datetime import datetime
from datetime import timezone
from hashlib import sha256
from pathlib import Path
from secrets import token_urlsafe
from uuid import uuid4
from uuid import uuid5
from uuid import NAMESPACE_URL
from fashion_recommendation_v2.schemas.preference import InteractionEvent
from fashion_recommendation_v2.schemas.preference import ItemSnapshot
from fashion_recommendation_v2.schemas.preference import PreferenceRequest
from fashion_recommendation_v2.schemas.summary import SummaryAgentInput_base as SummaryAgentInput
from fashion_recommendation_v2.schemas.summary_response import RecommendationResponse
from fashion_recommendation_v2.schemas.summary_response import validate_summary_response
from fashion_recommendation_v2.storage import PreferenceStore
from fashion_recommendation_v2.storage import UserUnavailable

@_preserve_function('utc_now', 'fashion_recommendation_v2.server.preference_service')
def utc_now():
    return datetime.now(timezone.utc)

@_preserve_function('token_hash', 'fashion_recommendation_v2.server.preference_service')
def token_hash(token):
    return sha256(token.encode()).hexdigest()

@_preserve_function('csrf_token', 'fashion_recommendation_v2.server.preference_service')
def csrf_token(token):
    return sha256(('preference-csrf:' + token).encode()).hexdigest()

@_preserve_class('PreferenceService', 'fashion_recommendation_v2.server.preference_service')
class PreferenceService:

    def __init__(self, db_path, *, artifact_root=None, clock=utc_now):
        self.db_path = Path(db_path)
        self.artifact_root = artifact_root
        self.clock = clock
        with self.store():
            pass

    def store(self):
        return PreferenceStore(self.db_path, artifact_root=self.artifact_root)

    def bootstrap(self, cookie):
        with self.store() as store:
            if cookie:
                try:
                    return (store.resolve_cookie(token_hash(cookie), now=self.clock()), cookie, False)
                except UserUnavailable:
                    pass
            token = token_urlsafe(32)
            return (store.create_cookie_identity(token_hash(token), now=self.clock()), token, True)

    def authenticate(self, cookie):
        if not cookie:
            raise UserUnavailable('Cookie required')
        with self.store() as store:
            return store.resolve_cookie(token_hash(cookie), now=self.clock())

    def start_session(self, user_id, previous_session_id=None):
        with self.store() as store:
            return store.transition_session(user_id, previous_session_id, now=self.clock())

    def end_session(self, user_id, session_id):
        with self.store() as store:
            return store.end_session(user_id, session_id, now=self.clock())

    def register_request(self, user_id, session_id, query, *, parent_request_id=None):
        """Low-level server adapter; RecommendationService owns Brain-based conversation routing."""
        request = PreferenceRequest(request_id=uuid4().hex, user_id=user_id, session_id=session_id, user_query=query, kind='followup' if parent_request_id else 'new', parent_request_id=parent_request_id, created_at=self.clock())
        with self.store() as store:
            store.add_request(request, now=self.clock())
        return request

    def publish_recommendation(self, user_id: str, request_id: str, source: SummaryAgentInput, response: RecommendationResponse):
        """Called by trusted recommendation backend BEFORE exposing Top N.

        Browser cannot submit arbitrary products/image evidence. IDs are stable on retries.
        RecommendationService calls this after validated Orchestrator completion.
        """
        source = SummaryAgentInput.model_validate_json(source.model_dump_json())
        response = validate_summary_response(response, source)
        items = {c.item.item_id: c.item for c in source.candidate_set.candidates}
        analyses = {c.item.item_id: c.search_analysis if source.candidate_set.search_policy_version in {'v26', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'} else None for c in source.candidate_set.candidates}
        ranked = {r.item_id: r for r in source.final_ranking.ranked_items}
        with self.store() as store:
            request = store.get_request(user_id, request_id, now=self.clock())
            snapshots = []
            for rec in response.recommendations:
                item = ranked[rec.item_id]
                observations = []
                for entry in [*item.requirement_assessments, *item.diversity_features, *item.preference_observations, *item.conflicts]:
                    for observation in entry.image_evidence:
                        if observation not in observations:
                            observations.append(observation)
                sid = uuid5(NAMESPACE_URL, f'{user_id}/{request_id}/{response.response_id}/{rec.item_id}').hex
                snapshots.append(ItemSnapshot(item_snapshot_id=sid, user_id=user_id, session_id=request.session_id, request_id=request_id, recommendation_id=response.response_id, rank=rec.rank, item=items[rec.item_id], search_analysis=analyses[rec.item_id], image_observations=observations, captured_at=self.clock()))
            store.add_snapshots(snapshots, now=self.clock())
            return [{'item_id': s.item.item_id, 'rank': s.rank, 'item_snapshot_id': s.item_snapshot_id} for s in snapshots]

    def record_event(self, user_id, payload):
        with self.store() as store:
            snap = store.get_snapshot(user_id, payload.item_snapshot_id, now=self.clock())
            event = InteractionEvent(event_id=payload.event_id, user_id=user_id, session_id=snap.session_id, request_id=snap.request_id, recommendation_id=snap.recommendation_id, rank=snap.rank, item_id=snap.item.item_id, item_snapshot_id=snap.item_snapshot_id, action=payload.action, operation=payload.operation, target_event_id=payload.target_event_id, occurred_at=payload.occurred_at, received_at=self.clock())
            seq, inserted = store.append_event(event, now=self.clock())
            # Delayed events after session end should not wait for a new session.
            if store.get_session(user_id, snap.session_id, now=self.clock()).ended_at is not None:
                store.end_session(user_id, snap.session_id, now=self.clock())
            return {'event_id': event.event_id, 'receipt_sequence': seq, 'inserted': inserted, 'profile_updated': False}
