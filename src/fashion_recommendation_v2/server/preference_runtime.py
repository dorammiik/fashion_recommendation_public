"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- preference_runtime ----

"""Independent maintenance and worker loops. Processor is injected in the Agent stage."""
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
import logging
from threading import Event
from threading import Lock
from threading import Thread
from typing import Callable
from fashion_recommendation_v2.schemas.preference import InteractionEvent
from fashion_recommendation_v2.schemas.preference import ItemSnapshot
from fashion_recommendation_v2.schemas.preference import PreferenceEvidence
from fashion_recommendation_v2.schemas.preference import PreferenceJob
from fashion_recommendation_v2.schemas.preference import PreferenceStorageConfig
from fashion_recommendation_v2.schemas.preference_profile import PreferenceProfile
from fashion_recommendation_v2.schemas.preference.interpretation.preference_interpretation import PreferenceProfileV1_v1 as PreferenceProfileV1
from fashion_recommendation_v2.schemas.preference.interpretation.preference_interpretation import InterpretationEvidence
from fashion_recommendation_v2.schemas.preference.interpretation.preference_interpretation import PreferenceProfileV2_v2 as PreferenceProfileV2
from fashion_recommendation_v2.schemas.preference.interpretation.preference_interpretation import PreferenceProfileV3
from fashion_recommendation_v2.schemas.preference.interpretation.preference_interpretation import PreferenceProfileV4
from fashion_recommendation_v2.storage import StoreConflict
from fashion_recommendation_v2.storage import UserUnavailable
log = logging.getLogger(__name__)

@_preserve_class('UpdateInput', 'fashion_recommendation_v2.server.preference_runtime')
@dataclass(frozen=True)
class UpdateInput:
    job: PreferenceJob
    previous_profile: PreferenceProfile | PreferenceProfileV1 | PreferenceProfileV2 | PreferenceProfileV3 | PreferenceProfileV4 | None
    events: list[tuple[int, InteractionEvent]]
    effective_events: list[InteractionEvent]
    snapshots: dict[str, ItemSnapshot]
    evidence: list[PreferenceEvidence | InterpretationEvidence]
    as_of: datetime
    analyses: dict = field(default_factory=dict)

@_preserve_class('UpdateOutput', 'fashion_recommendation_v2.server.preference_runtime')
@dataclass(frozen=True)
class UpdateOutput:
    profile: PreferenceProfile | PreferenceProfileV1 | PreferenceProfileV2 | PreferenceProfileV3 | PreferenceProfileV4
    evidence: list[PreferenceEvidence | InterpretationEvidence]
    analyses: list = field(default_factory=list)

@_preserve_class('PreferenceRuntime', 'fashion_recommendation_v2.server.preference_runtime')
class PreferenceRuntime:

    def __init__(self, service, processor: Callable[[UpdateInput], UpdateOutput] | None=None):
        self.service, self.processor = (service, processor)
        self.config = PreferenceStorageConfig()
        self._stop = Event()
        self._worker_lock = Lock()
        self._maintenance_lock = Lock()
        self._commit_lock = Lock()
        self._threads = []
        self._next_scan = None
        self._next_purge = None

    @property
    def running(self):
        return bool(self._threads and (not self._stop.is_set()) and all((t.is_alive() for t in self._threads)))

    def maintenance_once(self):
        """Clock injection makes cadence testable without sleeping."""
        from datetime import timedelta
        with self._maintenance_lock:
            now = self.service.clock()
            result = {}
            with self.service.store() as store:
                if self._next_purge is None or now >= self._next_purge:
                    result['purge'] = store.purge_expired(now=now)
                    self._next_purge = now + timedelta(seconds=self.config.expiry_scan_seconds)
                if self._next_scan is None or now >= self._next_scan:
                    result['queued'] = store.enqueue_pending(now=now)
                    self._next_scan = now + timedelta(seconds=self.config.pending_scan_seconds)
            return result

    def _heartbeat(self, job, finished, lost):
        interval = max(0.1, self.config.job_lease_seconds / 3)
        while not finished.wait(interval):
            if self._stop.is_set():
                return
            try:
                with self.service.store() as store:
                    # Store error class only: exception text may contain personal data.
                    store.renew_job(job.job_id, job.lease_token, now=self.service.clock())
            except Exception:
                lost.set()
                log.warning('Preference lease renewal failed')
                return

    def worker_once(self):
        if self.processor is None:
            # Never claim/acknowledge unprocessed history.
            return 'processor_not_configured'
        if self._stop.is_set() or not self._worker_lock.acquire(blocking=False):
            return 'busy_or_stopped'
        job, heartbeat = (None, None)
        finished, lost = (Event(), Event())
        try:
            with self.service.store() as store:
                job = store.claim_job(now=self.service.clock())
                if job is None:
                    return 'idle'
                lookup = store.lookup_profile(job.user_id, now=self.service.clock())
                if lookup.status == 'failed':
                    raise StoreConflict('Cannot refresh a corrupt/unavailable profile')
                events = store.events(job.user_id, now=self.service.clock(), through=job.target_cursor)
                effective = store.effective_events(job.user_id, now=self.service.clock(), through=job.target_cursor)
                snapshots = {e.item_snapshot_id: store.get_snapshot(job.user_id, e.item_snapshot_id, now=self.service.clock()) for _, e in events}
                source = UpdateInput(job, lookup.preference_profile, events, effective, snapshots, store.get_evidence(job.user_id, now=self.service.clock()), self.service.clock(), {} if getattr(self.processor, 'version', 'v0') in {'v1', 'v2', 'v3', 'v4'} else store.get_analyses(job.user_id, now=self.service.clock()))
            heartbeat = Thread(target=self._heartbeat, args=(job, finished, lost), daemon=True)
            heartbeat.start()
            output = self.processor(source)
            with self._commit_lock:
                if self._stop.is_set() or lost.is_set():
                    raise StoreConflict('Worker stopped or lost lease')
                with self.service.store() as store:
                    store.save_profile(output.profile, output.evidence, job_id=job.job_id, lease_token=job.lease_token, expected_version=source.previous_profile.profile_version if source.previous_profile else 0, now=self.service.clock(), analyses=output.analyses)
            return 'completed'
        except Exception as exc:
            status = 'failed'
            if job is not None:
                try:
                    with self.service.store() as store:
                        job_status = store.retry_job(job.job_id, job.lease_token, type(exc).__name__, now=self.service.clock(), exhausted=getattr(exc, 'preference_retry_exhausted', False))
                        if job_status == 'stopped':
                            status = 'stopped'
                except (StoreConflict, UserUnavailable):
                    # Expired/deleted user or another worker owns it now.
                    pass
            log.warning('Preference update %s (%s)', status, type(exc).__name__)
            return status
        finally:
            finished.set()
            if heartbeat is not None:
                heartbeat.join(timeout=1)
            self._worker_lock.release()

    def _maintenance_loop(self):
        while not self._stop.wait(1):
            try:
                self.maintenance_once()
            except Exception as exc:
                log.warning('Preference maintenance failed (%s)', type(exc).__name__)

    def _worker_loop(self):
        while not self._stop.is_set():
            try:
                result = self.worker_once()
            except Exception as exc:
                log.warning('Preference worker unavailable (%s)', type(exc).__name__)
                result = 'failed'
            # Failure cooldown avoids a paid retry storm. Pending work stays durable.
            if self._stop.wait(60 if result == 'failed' else 1):
                break

    def start(self):
        if self._threads:
            raise RuntimeError('Create a new runtime after stopping')
        # Startup expiry sweep before accepting HTTP traffic.
        self.maintenance_once()
        self._threads = [Thread(target=self._maintenance_loop, daemon=True, name='preference-maintenance'), Thread(target=self._worker_loop, daemon=True, name='preference-worker')]
        for thread in self._threads:
            thread.start()

    def stop(self):
        with self._commit_lock:
            self._stop.set()
        for thread in self._threads:
            thread.join(timeout=2)
# A blocked processor may finish later; it cannot commit after stop.
# On process exit, unfinished leases are reclaimed on the next startup.
