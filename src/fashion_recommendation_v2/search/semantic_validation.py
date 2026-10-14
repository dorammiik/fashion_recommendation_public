"""Run-local v31 semantic observations and backward-compatible v30 A/B gates.

No product validator, transport/schema validator, or budget consults this switch.
Default/unscoped execution remains the original blocking implementation.
"""
from fashion_recommendation_v2.module_compat import import_module as _role_module
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from functools import wraps
from pydantic import ValidationError
import inspect
import json
from typing import get_args
from fashion_recommendation_v2.schemas.search.planning.search_planning import SemanticWarningV31

_SCOPE = ContextVar('search_semantic_scope', default=None)


def observed(stage):
    """Run-local v31 policy. Nested helpers reuse the ledger, never change budgets."""
    def decorate(function):
        signature = inspect.signature(function)
        @wraps(function)
        def invoke(*args, **kwargs):
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            arguments = bound.arguments
            owner = arguments.get('self', arguments.get('brain', arguments.get('runner')))
            context = arguments.get('context') or {}
            version = arguments.get('search_policy_version', arguments.get('version',
                context.get('search_policy_version', getattr(owner, 'search_policy_version', None))))
            if version not in {'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
                return function(*args, **kwargs)
            parent = _SCOPE.get()
            records = experiment_records() if parent else []
            if owner is not None:
                owner.semantic_validation_history = records
            plan = arguments.get('query_plan', arguments.get('plan'))
            scope = dict(release=version, stage=stage, query_plan=plan.model_dump(mode='json') if plan is not None else None)
            if parent and scope['query_plan'] is None and stage != 'requirements':
                scope['query_plan'] = parent.get('query_plan')
            token = _SCOPE.set(scope)
            try:
                with validation_experiment('B', records):
                    return function(*args, **kwargs)
            finally:
                _SCOPE.reset(token)
        return invoke
    return decorate

OBSERVED_RULES = frozenset(get_args(SemanticWarningV31.model_fields['rule'].annotation))
_SESSION = ContextVar('search_code_validation_test', default=None)


def experiment_records():
    session = _SESSION.get()
    return session[1] if session is not None else []


def record_only():
    session = _SESSION.get()
    return session is not None and session[0] == 'B'


@contextmanager
def validation_experiment(variant, records):
    if variant not in {'A', 'B'}:
        raise ValueError('code_validation_test variant must be A or B.')
    token = _SESSION.set((variant, records))
    try:
        yield
    finally:
        _SESSION.reset(token)


def semantic_failure(rule, message, **evidence):
    if rule not in OBSERVED_RULES:
        raise ValueError('Unregistered experimental semantic rule: ' + rule)
    session = _SESSION.get()
    if session is not None:
        variant, records = session
        record = dict(rule=rule, variant=variant,
            action='record_only' if variant == 'B' else 'blocked', message=message,
            evidence=deepcopy(evidence))
        if _SCOPE.get() is not None:
            record.update(**deepcopy(_SCOPE.get()))
            if evidence.get('query_plan') is not None:
                record['query_plan'] = deepcopy(evidence['query_plan'])
        records.append(record)
        if variant == 'B':
            return
    raise ValueError(message)


def semantic_call(rule, function, *args, fallback=None, **kwargs):
    try:
        return function(*args, **kwargs)
    except ValidationError:
        raise  # Pydantic types/required fields/allowed values stay strict.
    except ValueError as exc:
        semantic_failure(rule, str(exc), check=function.__name__)
        return fallback(*args, **kwargs) if callable(fallback) else fallback


def semantic_only(rule, *, fallback=None):
    """For functions whose entire responsibility is one approved semantic rule."""
    def decorate(function):
        @wraps(function)
        def checked(*args, **kwargs):
            return semantic_call(rule, function, *args, fallback=fallback, **kwargs)
        return checked
    return decorate


def inspection_warnings(branches, records):
    """Only warnings for this executed plan, plus request-wide requirements warnings.

    Repeated checks share an ID/count; all original observations remain in the ledger.
    Unexecuted or repaired-away plans cannot contaminate another query's inspection.
    """
    from hashlib import sha256
    grouped = {}
    for row in records:
        if row.get('release') not in {'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
            continue
        owners = [b['attempt_id'] for b in branches if row.get('stage') == 'requirements'
                  or row.get('query_plan') == b['plan'].model_dump(mode='json')]
        if not owners:
            continue
        key = json.dumps({k: row.get(k) for k in ('rule', 'stage', 'message', 'evidence', 'query_plan')},
                         sort_keys=True, ensure_ascii=False)
        if key not in grouped:
            grouped[key] = dict(warning_id='semantic_' + sha256(key.encode()).hexdigest()[:16],
                rule=row['rule'], stage=row['stage'], message=row['message'],
                evidence=deepcopy(row['evidence']), attempt_ids=owners, occurrences=0)
        grouped[key]['occurrences'] += 1
    return [SemanticWarningV31.model_validate(row).model_dump(mode='json') for row in grouped.values()]
