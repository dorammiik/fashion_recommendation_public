"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- orchestrator_spans ----

"""Exact-quote coordinate derivation. Never mutate or paraphrase model output."""
from copy import deepcopy

@_preserve_function('derive_coordinates', 'fashion_recommendation_v2.orchestrator_spans')
def derive_coordinates(raw, query):
    derived = deepcopy(raw)
    records, errors = ([], [])
    if not isinstance(derived, dict):
        return (derived, records, errors)

    def resolve(span, path, allowed=None, lower=None, upper=None):
        if not isinstance(span, dict) or not isinstance(span.get('source_text'), str) or (not span['source_text'].strip()):
            return
        quote = span['source_text']
        matches = [(i, i + len(quote)) for i in range(len(query)) if query.startswith(quote, i)]
        if allowed is not None:
            matches = [(a, b) for a, b in matches if set(range(a, b)) <= allowed]
        if lower is not None:
            matches = [(a, b) for a, b in matches if a >= lower]
        if upper is not None:
            matches = [(a, b) for a, b in matches if b <= upper]
        hint = (span.get('start'), span.get('end'))
        chosen = matches[0] if len(matches) == 1 else hint if hint in matches else None
        if chosen is None:
            errors.append(dict(error_id=f'quote_{len(errors) + 1}', code='quote_location_ambiguous' if matches else 'quote_not_found', path=path, source_text=quote, message='Return an exact, unambiguous quote or valid occurrence hints.'))
            # The schema owns malformed/missing quotes.
            return
        span['start'], span['end'] = chosen
        records.append(dict(path=path, source_text=quote, model_start=hint[0], model_end=hint[1], start=chosen[0], end=chosen[1]))
        return chosen
    units = derived.get('semantic_units', [])
    groups = []
    for i, unit in enumerate(units if isinstance(units, list) else []):
        if not isinstance(unit, dict) or not isinstance(unit.get('spans'), list):
            continue
        groups.append((unit, [(s, f'semantic_units[{i}].spans[{j}]') for j, s in enumerate(unit['spans'])]))
    # Only within-unit order is guaranteed by the existing contract. Do not assume
    # semantic units themselves appear in textual order or choose the first match.
    resolved = {}
    for unit, spans in groups:
        for span, path in spans:
            before = len(errors)
            pos = resolve(span, path)
            if pos:
                resolved[path] = pos
            else:
                # Retry ambiguous quotes with proven neighbors.
                del errors[before:]
    for unit, spans in groups:
        for j, (span, path) in enumerate(spans):
            if path in resolved:
                continue
            lower = max((resolved[p][1] for _, p in spans[:j] if p in resolved), default=None)
            upper = min((resolved[p][0] for _, p in spans[j + 1:] if p in resolved), default=None)
            pos = resolve(span, path, lower=lower, upper=upper)
            if pos:
                resolved[path] = pos
    states = derived.get('unresolved_states', [])
    for i, state in enumerate(states if isinstance(states, list) else []):
        if not isinstance(state, dict) or not isinstance(state.get('evidence'), list):
            continue
        linked = [(u, spans) for u, spans in groups if u.get('state_id') == state.get('state_id')]
        allowed = {n for _, spans in linked for _, path in spans if path in resolved for n in range(*resolved[path])}
        complete = bool(linked) and all((path in resolved for _, spans in linked for _, path in spans))
        for j, span in enumerate(state['evidence']):
            resolve(span, f'unresolved_states[{i}].evidence[{j}]', allowed=allowed if complete else None)
    count = derived.get('count_evidence', [])
    for i, span in enumerate(count if isinstance(count, list) else []):
        resolve(span, f'count_evidence[{i}]')
    return (derived, records, errors)
