"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- validation_reuse ----

"""Request-local successful validation proofs; no model/agent/prompt dependencies.

Keys include exact typed fields (including private/extra state), both operands,
validator identity and policy scope. No model construction or response rewriting.
Only pure validators returning their first argument may be decorated.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from dataclasses import field
from functools import wraps
from hashlib import sha256
import pickle
import sys
from io import BytesIO
from time import perf_counter
from threading import RLock
from pydantic import BaseModel
_LOCATION = ContextVar('validation_location', default=())

@_preserve_function('measure_processing', 'fashion_recommendation_v2.validation_reuse')
@contextmanager
def measure_processing(name):
    current = _ACTIVE.get()
    if current is None or current.closed or (not current.enabled):
        yield
        return
    token = _LOCATION.set((*_LOCATION.get(), name))
    started = perf_counter()
    outcome = 'completed'
    try:
        yield
    except BaseException:
        outcome = 'failed'
        raise
    finally:
        with current.lock:
            current.timings.append(dict(operation=name, location=list(_LOCATION.get()), seconds=perf_counter() - started, outcome=outcome, started_offset_seconds=started - current.started))
        _LOCATION.reset(token)

@_preserve_function('timed_processing', 'fashion_recommendation_v2.validation_reuse')
def timed_processing(name):

    def decorate(function):

        @wraps(function)
        def measured(*args, **kwargs):
            with measure_processing(name):
                return function(*args, **kwargs)
        return measured
    return decorate
_ACTIVE = ContextVar('validation_reuse', default=None)
MAX_PROOFS = 512
# Release selection is shared by the three entry points.
REUSE_RELEASES = {'orchestrator': 'v5', 'ranking': 'ranking_eval_v14', 'summary': 'v11'}

@_preserve_function('reuse_enabled', 'fashion_recommendation_v2.validation_reuse')
def reuse_enabled(role, version):
    return role == 'ranking' and version in {'ranking_eval_v15', 'ranking_eval_v16', 'ranking_eval_v17'} or version == REUSE_RELEASES[role] or (role == 'orchestrator' and version in {'v6', 'v7', 'v8', 'v9', 'v10', 'v11', 'v12'})

@_preserve_function('_snapshot', 'fashion_recommendation_v2.validation_reuse')
def _snapshot(value):
    if isinstance(value, BaseModel):
        current = _ACTIVE.get()
        if current is not None and (not current.closed):
            with current.lock:
                current.types[id(type(value))] = type(value)
        return ((type(value).__module__, type(value).__qualname__, id(type(value))), _snapshot(value.__dict__), _snapshot(value.__pydantic_extra__), _snapshot(value.__pydantic_private__))
    if isinstance(value, dict):
        return (dict, tuple(((_snapshot(k), _snapshot(v)) for k, v in value.items())))
    if isinstance(value, (tuple, list)):
        return (type(value), tuple((_snapshot(v) for v in value)))
    if isinstance(value, (set, frozenset)):
        return (type(value), frozenset((_snapshot(v) for v in value)))
    from datetime import date
    from datetime import datetime
    from decimal import Decimal
    from enum import Enum
    if value is None or isinstance(value, (str, int, float, bool, bytes, date, datetime, Decimal, Enum)):
        return (type(value), value)
    raise TypeError('Unsupported validation snapshot type')

@_preserve_function('_key', 'fashion_recommendation_v2.validation_reuse')
def _key(function, args, kwargs):
    try:
        stream = BytesIO()
        encoder = pickle.Pickler(stream, protocol=5)
        # Identity/aliasing is not part of a value proof.
        encoder.fast = True
        encoder.dump(_snapshot((args, kwargs)))
        return (function, sha256(stream.getvalue()).digest())
    except (TypeError, ValueError, RecursionError, AttributeError, pickle.PickleError):
        # Unsupported input is validated normally, never trusted.
        return None

@_preserve_class('Proofs', 'fashion_recommendation_v2.validation_reuse')
@dataclass
class Proofs:
    ranking_handoff: bool = False
    enabled: bool = True
    closed: bool = False
    successes: set = field(default_factory=set)
    types: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)
    started: float = field(default_factory=perf_counter)
    timings: list = field(default_factory=list)
    decisions: list = field(default_factory=list)
    lock: RLock = field(default_factory=RLock)

@_preserve_function('validation_scope', 'fashion_recommendation_v2.validation_reuse')
@contextmanager
def validation_scope(*, enabled=True):
    """Nested new-version agents share proofs; each outer call starts empty."""
    current = _ACTIVE.get()
    if current is not None and (not current.closed):
        yield current
        return
    current = Proofs(enabled=enabled)
    token = _ACTIVE.set(current)
    try:
        yield current
    finally:
        _ACTIVE.reset(token)
        with current.lock:
            current.closed = True
            current.successes.clear()
            current.types.clear()

@_preserve_function('validated_once', 'fashion_recommendation_v2.validation_reuse')
def validated_once(function):

    @wraps(function)
    def validate(*args, **kwargs):
        current = _ACTIVE.get()
        if current is None or current.closed or (not current.enabled):
            return function(*args, **kwargs)
        started = perf_counter()
        key = _key(function, args, kwargs)
        name = function.__module__ + '.' + function.__qualname__
        key_seconds = perf_counter() - started
        caller = sys._getframe(1)
        called_from = dict(file=caller.f_code.co_filename, function=caller.f_code.co_name, line=caller.f_lineno)
        del caller
        event = dict(validator=name, caller=called_from, location=list(_LOCATION.get()), fingerprint=key[1].hex() if key is not None else None, key_seconds=key_seconds, executed=False)
        with current.lock:
            previous = next((e for e in reversed(current.decisions) if e['validator'] == name), None)
            event['previous_fingerprint'] = previous['fingerprint'] if previous else None
            event['snapshot_changed_since_previous_call'] = key[1].hex() != previous['fingerprint'] if key is not None and previous and (previous['fingerprint'] is not None) else None
            current.decisions.append(event)
            stats = current.metrics.setdefault(name, dict(hits=0, misses=0, failures=0, key_seconds=0.0, validation_seconds=0.0))
            stats['key_seconds'] += perf_counter() - started
            if key is not None and key in current.successes:
                event.update(decision='reuse', reason='exact_successful_snapshot')
                stats['hits'] += 1
                return args[0]
            event.update(decision='validate', reason='unsupported_snapshot' if key is None else 'no_exact_successful_proof', executed=True)
            stats['misses'] += 1
        started = perf_counter()
        try:
            with measure_processing(name + '.actual_validation'):
                result = function(*args, **kwargs)
        except BaseException:
            event['outcome'] = 'failed'
            with current.lock:
                stats['failures'] += 1
            raise
        else:
            event['outcome'] = 'completed'
            # A validator that normalizes/mutates its input does not earn a proof.
            after_started = perf_counter()
            after_key = _key(function, args, kwargs) if key is not None and result is args[0] else None
            event['post_key_seconds'] = perf_counter() - after_started
            event['proof_stored'] = False
            if key is not None and result is args[0] and (after_key == key):
                with current.lock:
                    if current.closed:
                        return result
                    if len(current.successes) >= MAX_PROOFS:
                        current.successes.clear()
                    current.successes.add(key)
                    event['proof_stored'] = True
            return result
        finally:
            with current.lock:
                stats['validation_seconds'] += perf_counter() - started
    return validate

@_preserve_function('reuse_for', 'fashion_recommendation_v2.validation_reuse')
def reuse_for(role):

    def decorate(function):

        @wraps(function)
        def run(self, *args, **kwargs):
            version = getattr(getattr(self, 'brain', None), 'evaluation_version', None) if role == 'orchestrator' else getattr(self, 'policy_version' if role == 'ranking' else 'version', None)
            if not reuse_enabled(role, version):
                return function(self, *args, **kwargs)
            with validation_scope(enabled=role != 'orchestrator') as proofs:
                if role == 'orchestrator' and version in {'v10', 'v11', 'v12'}:
                    proofs.ranking_handoff = True
                try:
                    return function(self, *args, **kwargs)
                finally:
                    from copy import deepcopy
                    with proofs.lock:
                        self.validation_reuse_stats = deepcopy(proofs.metrics)
                    if role == 'orchestrator':
                        self._save('validation_reuse', self.validation_reuse_stats)
                    with proofs.lock:
                        self.processing_diagnostics = deepcopy(dict(timings=proofs.timings, validation_decisions=proofs.decisions, timing_semantics='Nested inclusive wall seconds; do not sum nested operations.'))
                    if role == 'orchestrator':
                        self._save('processing_diagnostics', self.processing_diagnostics)
        return run
    return decorate

@_preserve_function('enable_validation_reuse', 'fashion_recommendation_v2.validation_reuse')
def enable_validation_reuse():
    """Orchestrator starts reuse only at the Ranking handoff, never earlier."""
    current = _ACTIVE.get()
    if current is not None:
        current.enabled = True

@_preserve_function('handoff_validation', 'fashion_recommendation_v2.validation_reuse')
def handoff_validation(function):
    """Exact common-input proof, enabled only by Orchestrator v10."""
    cached = validated_once(function)

    @wraps(function)
    def validate(*args, **kwargs):
        current = _ACTIVE.get()
        if current is not None and current.ranking_handoff:
            return cached(*args, **kwargs)
        return function(*args, **kwargs)
    return validate

@_preserve_function('has_validation_proof', 'fashion_recommendation_v2.validation_reuse')
def has_validation_proof(validator, *args):
    current = _ACTIVE.get()
    if current is None or current.closed or (not current.enabled):
        return False
    key = _key(validator.__wrapped__, args, {})
    return key is not None and key in current.successes
