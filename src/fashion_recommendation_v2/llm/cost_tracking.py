"""Persistent, local estimates from API-reported usage (never prompt contents)."""
from fashion_recommendation_v2.module_compat import import_module as _role_module

import json
import logging
import os
import re
import sqlite3
import sys
from contextlib import closing
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from datetime import datetime
from datetime import timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
from threading import Lock

ROOT = Path(__file__).resolve().parents[3]
PRICING_SOURCE = 'https://developers.openai.com/api/docs/pricing'
PRICING_VERSION = '2026-09-20'
# USD / 1M tokens: uncached input, cached input, cache writes, output.
RATES = {
    'gpt-6-astra': ('10', '1', '12.5', '50'),
    'gpt-5.6-sol': ('4', '0.4', '5', '20'),
    'gpt-5.6-terra': ('2', '0.2', '2.5', '12'),
    'gpt-5.6-luna': ('0.2', '0.02', '0.25', '1.2'),
    'gpt-6-luna': ('0.1', '0.01', '0.125', '0.5'),
    # Nano has no separate cache-write premium: count writes as ordinary input.
    'gpt-4.1-nano': ('0.1', '0.025', '0.1', '0.4'),
}
PROCESS_RUN_ID = uuid4().hex
_RUN_REPORT = ContextVar('openai_cost_run_report', default=None)
_CALL_CONTEXT = ContextVar('openai_cost_call_context', default=None)


@contextmanager
def record_call_context(**metadata):
    records = {}
    token = _CALL_CONTEXT.set((metadata, records))
    try:
        yield records
    finally:
        _CALL_CONTEXT.reset(token)



@contextmanager
def record_run_costs(folder: Path, run_id: str):
    """Silence per-call console output and export this run, across all trackers.

    Keep an in-memory copy as well as the existing ledger, so a post-request
    ledger write failure cannot hide API-reported usage in the run report.
    Export on success, failure or interruption; unknown costs remain explicit.
    """
    report = {'run_id': run_id, 'records': {}, 'lock': Lock()}
    token = _RUN_REPORT.set(report)
    try:
        yield
    finally:
        _RUN_REPORT.reset(token)
        with report['lock']:
            records = list(report['records'].values())
        payload = {
            'run_id': run_id,
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'cost_type': 'estimate',
            'note': 'Estimates use stored pricing, not an invoice. Unknown costs are excluded from the known subtotal.',
            **summarize(records, group_by='operation'),
            'by_model': summarize(records, group_by='model')['groups'],
            'records': records,
        }
        folder.mkdir(parents=True, exist_ok=True)
        temporary = folder / 'openAI_cost.json.tmp'
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
        temporary.replace(folder / 'openAI_cost.json')


def ledger_path() -> Path:
    path = Path(os.environ.get('OPENAI_COST_DB', 'usage/openai_costs.sqlite3')).expanduser()
    return path if path.is_absolute() else ROOT / path


def estimate(model: str, usage: dict | None, tier: str | None = None) -> dict:
    """Reasoning/image tokens are already included in API input/output totals."""
    unknown = {'estimated_cost_usd': None, 'pricing_status': 'missing_usage'}
    if not isinstance(usage, dict):
        return unknown
    details = usage.get('input_tokens_details') or {}
    counts = [usage.get('input_tokens'), details.get('cached_tokens', 0),
              details.get('cache_write_tokens', 0), usage.get('output_tokens')]
    if any(type(n) is not int or n < 0 for n in counts) or sum(counts[1:3]) > counts[0]:
        return {**unknown, 'pricing_status': 'invalid_usage'}
    base_model = re.sub(r'-\d{4}-\d{2}-\d{2}$', '', model)
    base_model = {'gpt-5.6': 'gpt-5.6-sol'}.get(base_model, base_model)
    if base_model not in RATES:
        return {**unknown, 'pricing_status': 'unknown_model'}
    multiplier = {None: '1', 'default': '1', 'standard': '1',
                  'flex': '0.5', 'priority': '2', 'fast': '2'}.get(tier)
    if multiplier is None:
        return {**unknown, 'pricing_status': 'unknown_service_tier'}
    rates = [Decimal(v) * Decimal(multiplier) for v in RATES[base_model]]
    long_context = counts[0] > 272_000 and base_model != 'gpt-4.1-nano'
    if long_context:
        rates = [rate * factor for rate, factor in zip(rates, [2, 2, 2, Decimal('1.5')])]
    counts[0] -= counts[1] + counts[2]
    components = [Decimal(count) * rate / 1_000_000 for count, rate in zip(counts, rates)]
    return {
        'estimated_cost_usd': str(sum(components)), 'pricing_status': 'estimated',
        'pricing_model': base_model, 'long_context': long_context,
        'rates_usd_per_million': dict(zip(['input', 'cached_input', 'cache_write', 'output'], map(str, rates))),
        'cost_components_usd': dict(zip(['input', 'cached_input', 'cache_write', 'output'], map(str, components))),
    }


class CostTracker:
    def __init__(self, path: Path | None = None):
        self.path = path or ledger_path()
        self.storage_failed = False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=30)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS calls (call_id TEXT PRIMARY KEY, data TEXT NOT NULL)')

    def save(self, record: dict) -> None:
        with closing(sqlite3.connect(self.path, timeout=30)) as db, db:
            db.execute('INSERT OR REPLACE INTO calls VALUES (?, ?)',
                       (record['call_id'], json.dumps(record, ensure_ascii=False)))

    @staticmethod
    def _capture(record: dict) -> None:
        context = _CALL_CONTEXT.get()
        if context is not None:
            context[1][record['call_id']] = deepcopy(record)
        report = _RUN_REPORT.get()
        if report is not None:
            with report['lock']:
                report['records'][record['call_id']] = deepcopy(record)

    def start(self, model: str, operation: str) -> dict:
        if self.storage_failed:
            raise RuntimeError('OpenAI cost ledger could not be written; restore storage before further API calls.')
        record = {
            'call_id': uuid4().hex,
            'run_id': (_RUN_REPORT.get() or {}).get('run_id') or os.environ.get('OPENAI_COST_RUN_ID') or PROCESS_RUN_ID,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'script': Path(sys.argv[0]).name, 'operation': operation,
            'requested_model': model, 'model': model, 'status': 'pending',
            'usage': None, 'estimated_cost_usd': None, 'pricing_status': 'missing_usage',
            'pricing_version': ('2026-09-30' if re.sub(r'-\d{4}-\d{2}-\d{2}$', '', model)
                                in {'gpt-6-luna', 'gpt-4.1-nano'} else PRICING_VERSION),
            'pricing_source': PRICING_SOURCE,
        }
        if _CALL_CONTEXT.get() is not None:
            record['evaluation_context'] = deepcopy(_CALL_CONTEXT.get()[0])
        # Fail before making a paid request if the ledger cannot be written.
        self.save(record)
        self._capture(record)
        return record

    def _save_after_request(self, record: dict) -> None:
        self._capture(record)
        try:
            self.save(record)
        except (OSError, sqlite3.Error):
            # A storage outage must not turn a successful paid response into an
            # application retry. The pre-request pending row remains visible.
            self.storage_failed = True
            logging.getLogger(__name__).error(
                'OpenAI cost ledger write failed; cost may be missing for call %s. Further calls blocked.',
                record['call_id'],
            )

    def received(self, record: dict, body: dict, request_id: str | None) -> None:
        record.update(model=body.get('model') or record['requested_model'],
                      response_id=body.get('id'), request_id=request_id,
                      service_tier=body.get('service_tier'), usage=body.get('usage'),
                      status='response_received',
                      response_status=body.get('status'),
                      incomplete_details=body.get('incomplete_details'),
                      response_error_code=(body.get('error') or {}).get('code'),
                      response_max_output_tokens=body.get('max_output_tokens'),
                      response_output_statuses=[{'type': out.get('type'), 'status': out.get('status')}
                                                for out in body.get('output', [])])
        record.update(estimate(record['model'], record['usage'], record['service_tier']))
        self._save_after_request(record)
        cost = record['estimated_cost_usd']
        label = f'${Decimal(cost):.8f}' if cost is not None else f"unknown ({record['pricing_status']})"
        if _RUN_REPORT.get() is None:
            print(f"[OpenAI cost] {record['operation']} | {record['model']} | {label} USD | run={record['run_id']}", file=sys.stderr)

    def finish(self, record: dict, status: str, error: Exception | None = None) -> None:
        record['status'] = status
        if error is not None:
            # Exception messages can contain user content; only retain the class.
            record['error_type'] = type(error).__name__
        self._save_after_request(record)


def read_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=30)) as db:
        return [json.loads(row[0]) for row in db.execute('SELECT data FROM calls ORDER BY rowid')]


def summarize(records: list[dict], group_by: str = 'model') -> dict:
    groups = {}
    for record in records:
        key = record['timestamp'][:10] if group_by == 'day' else record[group_by]
        group = groups.setdefault(key, {'calls': 0, 'unknown_cost_calls': 0, 'estimated_cost_usd': Decimal(0),
                                        'input_tokens': 0, 'output_tokens': 0, 'cached_tokens': 0})
        group['calls'] += 1
        cost = record['estimated_cost_usd']
        if cost is None:
            group['unknown_cost_calls'] += 1
        else:
            group['estimated_cost_usd'] += Decimal(cost)
        usage = record.get('usage') or {}
        for field in ('input_tokens', 'output_tokens'):
            group[field] += usage.get(field) or 0
        group['cached_tokens'] += (usage.get('input_tokens_details') or {}).get('cached_tokens') or 0
    total = sum((g['estimated_cost_usd'] for g in groups.values()), Decimal(0))
    for group in groups.values():
        group['estimated_cost_usd'] = str(group['estimated_cost_usd'])
    return {'currency': 'USD', 'calls': len(records), 'estimated_cost_usd': str(total),
            'unknown_cost_calls': sum(g['unknown_cost_calls'] for g in groups.values()), 'groups': groups}
