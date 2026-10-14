"""Lossless request-span diagnostics shared by generation, correction and saved-state checks."""
from fashion_recommendation_v2.module_compat import import_module as _role_module
from collections import defaultdict
from copy import deepcopy
from pydantic import ValidationError
from pydantic import TypeAdapter
from typing import Annotated
from typing import get_args

ASSESSMENT_QUERY_PATH = 'user_query'
CHARACTER_OFFSETS_PATH = 'character_offsets'

TERMINAL_PERIOD_RULE = '''
v9 원문 전체 포함 규칙의 유일한 예외: 코드가 독립적인 문장 종료 마침표로
확인한 누락은 경고로 기록하고 진행한다. 그 외 문자 누락은 계속 오류다.
마침표도 가능하면 원문 그대로 포함한다. 인용문과 start/end의 불일치는
이 예외와 무관하게 오류다. 괄호·따옴표 안의 마침표, 소수점·범위·약어·
말줄임표처럼 의미가 있거나 문장 종료인지 불확실한 기호는 예외로 보지 않는다.
교정 시 이미 정확한 구간을 유지하며 전체 인용·누락·중복·의존관계를 재확인한다.
'''


def independent_terminal_period(query, position):
    """Conservative Korean request sentence ending; ambiguous punctuation stays strict."""
    import re
    if query[position] != '.' or position == 0:
        return False
    if position + 1 < len(query) and not query[position + 1].isspace():
        return False
    # Quoted/bracketed requests require the original strict punctuation ownership.
    if any(c in query for c in '()[]{}<>\"\'“”‘’「」『』'):
        return False
    return bool(re.search(r'[가-힣](?:다|요|줘|까|자|네|죠|어|음|함)$', query[:position]))


def apply_terminal_period_policy(report, query, version):
    from fashion_recommendation_v2.orchestrator_policy import ASSESSMENT_CONTRACTS
    contract = ASSESSMENT_CONTRACTS.get(version)
    if not contract or not contract.terminal_period_warning:
        return report
    errors, warnings = [], []
    for error in report['errors']:
        start, end = error.get('start'), error.get('end')
        if (error['code'] == 'uncovered_characters' and isinstance(start, int)
                and end == start + 1 and independent_terminal_period(query, start)):
            warnings.append(dict(error, code='uncovered_terminal_period', action='record_only',
                                 reason='Independent sentence-ending period; original response preserved'))
        else:
            errors.append(error)
    report['errors'] = errors
    report['warnings'] = warnings
    return report


def character_offsets(request):
    return [f'{i}:{char}' for i, char in enumerate(getattr(request, ASSESSMENT_QUERY_PATH))]


def validate_segmentation(assessment, query, *, version=None):
    from fashion_recommendation_v2.orchestrator_policy import ASSESSMENT_CONTRACTS
    contract = ASSESSMENT_CONTRACTS.get(version)
    if contract is not None and contract.collected_validation:
        raw = assessment.model_dump(mode='json') if hasattr(assessment, 'model_dump') else assessment
        result, report = collect_segmentation(raw, query, schema=type(assessment))
        apply_terminal_period_policy(report, query, version)
        if report['errors'] or report['deferred_checks']:
            raise AssessmentValidationError(report)
        return result
    return _validate_segmentation_legacy(assessment, query)


def _validate_segmentation_legacy(assessment, query):
    """Reject gaps/overlaps and cross-unit deletion hazards; no semantic inference."""
    assessment = assessment.validate_against(query)
    units = assessment.semantic_units
    if not units or len({u.unit_id for u in units}) != len(units):
        raise ValueError('Semantic units must be present with unique IDs.')
    states = {s.state_id: s for s in assessment.unresolved_states}
    by_id = {u.unit_id: u for u in units}
    covered = {}
    for unit in units:
        if (unit.kind == 'unresolved_condition') != (unit.state_id is not None):
            raise ValueError('Only unresolved units must carry a state_id.')
        if unit.state_id is not None and unit.state_id not in states:
            raise ValueError('Unit references an unknown state.')
        if len(unit.depends_on) != len(set(unit.depends_on)) or any(
            key not in by_id or key == unit.unit_id for key in unit.depends_on
        ):
            raise ValueError('Invalid semantic dependency.')
        previous = -1
        for span in unit.spans:
            span.validate_against(query)
            if span.start < previous:
                raise ValueError('Unit spans must be ordered and disjoint.')
            previous = span.end
            for index in range(span.start, span.end):
                if index in covered:
                    raise ValueError('Source spans overlap; preserve shared meaning as one unit.')
                covered[index] = unit
    if any(not char.isspace() and i not in covered for i, char in enumerate(query)):
        raise ValueError('All non-whitespace request characters must be recorded.')
    for state_id, state in states.items():
        assigned = [u for u in units if u.state_id == state_id]
        if not assigned:
            raise ValueError('Every unresolved state needs a semantic unit.')
        for span in state.evidence:
            if any(covered.get(i) is None or covered[i].state_id != state_id
                   for i in range(span.start, span.end) if not query[i].isspace()):
                raise ValueError('State evidence must belong to its assigned units.')
    if assessment.decision == 'proceed':
        for unit in units:
            if unit.state_id is not None and not unit.independently_removable:
                raise ValueError('Unresolved meaning cannot be safely separated; regroup the units.')
            for key in unit.depends_on:
                dependency = by_id[key]
                if dependency.state_id is not None and dependency.state_id != unit.state_id:
                    raise ValueError('Removing an unresolved condition could change retained meaning.')
    return assessment


def validate_similarity_assessment(request, assessment):
    """A resolved product similarity phrase cannot itself require Stylist."""
    intent = assessment.relation_intent
    if not intent or intent.relation_type != 'similarity':
        return
    anchors = [r for r in request.reference_items if r.item.item_id == intent.anchor_item_id
               and (intent.anchor_rank is None or r.rank == intent.anchor_rank)]
    if len(anchors) != 1:
        raise ValueError('Similarity requires exactly one supplied matching reference.')
    # Keep independently ambiguous additions eligible for Stylist. Only the
    # supplied known-reference relationship must belong to clear/context units.
    starts = [i for i in range(len(request.user_query))
              if request.user_query.startswith(intent.source_text, i)]
    unresolved = {i for u in assessment.semantic_units if u.kind == 'unresolved_condition'
                  for span in u.spans for i in range(span.start, span.end)}
    if not starts or all(any(i in unresolved for i in range(start, start + len(intent.source_text)))
                         for start in starts):
        raise ValueError('Known-product similarity is a clear condition, not a Stylist unresolved state; '
                         'separate other ambiguous additions and cite only the known relationship.')


class AssessmentValidationError(ValueError):
    def __init__(self, report):
        self.report = deepcopy(report)
        super().__init__('; '.join(f"{e['code']} at {e['path']}" + (": " + e['message'] if e.get('message') else "") for e in report['errors'])
            or 'Required assessment checks are deferred.')


class Diagnostics:
    def __init__(self):
        self.errors, self.deferred = [], []
        self.next_id = 1

    def error(self, code, path, **details):
        entry = dict(code=code, path=path, **details)
        for existing in self.errors:
            if {k:v for k,v in existing.items() if k != 'error_id'} == entry:
                return existing['error_id']
        error_id = f'error_{self.next_id:03d}'
        self.next_id += 1
        self.errors.append(dict(error_id=error_id, **entry))
        return error_id

    def causes(self, path):
        return [e['error_id'] for e in self.errors if e['path'] == path
            or e['path'].startswith(path + '.') or e['path'].startswith(path + '[')
            or path.startswith(e['path'] + '.') or path.startswith(e['path'] + '[')]

    def defer(self, check, path, causes, reason='Required preceding data is invalid or ambiguous.'):
        entry = dict(check=check, path=path, reason=reason, prerequisite_error_ids=list(dict.fromkeys(causes)))
        if not entry['prerequisite_error_ids']:
            raise RuntimeError(f'Missing diagnostic prerequisite for {check}: {path}')
        if entry not in self.deferred:
            self.deferred.append(entry)

    def report(self):
        return dict(errors=self.errors, deferred_checks=self.deferred)


def diagnostic_path(location):
    path = ''
    for part in location:
        path += f'[{part}]' if isinstance(part, int) else ('.' if path else '') + str(part)
    return path or '$'


def ranges(indices):
    """Compact consecutive code-point positions without dropping punctuation/space."""
    start = end = None
    for index in sorted(set(indices)):
        if end is not None and index != end:
            yield start, end
            start = None
        if start is None:
            start = index
        end = index + 1
    if start is not None:
        yield start, end


def collect_segmentation(raw, query, *, schema):
    """Inspect the original value, never construct a repaired/partial assessment.

    A bounded numeric interval is usable for geometry even when its quote is
    wrong. Unavailable/out-of-range intervals cannot establish gaps or ownership.
    Malformed IDs defer only the references whose targets cannot be established.
    """
    diagnostics = Diagnostics()
    result = None
    try:
        result = schema.model_validate(raw)
    except ValidationError as exc:
        for error in exc.errors(include_url=False, include_context=False, include_input=False):
            diagnostics.error('schema_validation_error', diagnostic_path(error['loc']),
                message=error['msg'], schema_error_type=error['type'])
    if not isinstance(raw, dict):
        causes = [e['error_id'] for e in diagnostics.errors]
        for check in ('span_quotes', 'coverage', 'overlap_and_order', 'id_references', 'state_evidence', 'dependency_safety'):
            diagnostics.defer(check, '$', causes, 'No structured assessment object is available.')
        return None, diagnostics.report()

    # All field types, defaults and bounds come from the actual output schema.
    # These probes create no corrected response and never replace original fields.
    unit_schema = get_args(schema.model_fields['semantic_units'].annotation)[0]
    state_schema = get_args(schema.model_fields['unresolved_states'].annotation)[0]
    span_schema = get_args(unit_schema.model_fields['spans'].annotation)[0]

    def valid_field(row, model, field):
        if not isinstance(row, dict):
            return False
        definition = model.model_fields[field]
        if field not in row:
            return not definition.is_required()
        annotation = Annotated[definition.annotation, *definition.metadata] if definition.metadata else definition.annotation
        try:
            TypeAdapter(annotation).validate_python(row[field], strict=True)
            return True
        except ValidationError:
            return False

    def rows(field):
        value = raw.get(field, [])
        if not isinstance(value, list):
            return []
        return value

    units, states = rows('semantic_units'), rows('unresolved_states')
    geometry, unit_intervals = [], defaultdict(list)
    unknown_geometry = []
    state_spans = defaultdict(list)
    unit_ids, state_ids = defaultdict(list), defaultdict(list)
    unknown_unit_ids, unknown_state_ids, unknown_state_links = [], [], []

    def invalid_causes(path):
        return diagnostics.causes(path) or diagnostics.causes('$')

    def span_check(span, path, *, unit_id=None, state_id=None):
        details = {k:v for k,v in dict(unit_id=unit_id, state_id=state_id).items() if isinstance(v, str)}
        if not isinstance(span, dict) or not all(valid_field(span, span_schema, f) for f in ('start', 'end')):
            causes = invalid_causes(path)
            diagnostics.defer('span_range_and_quote', path, causes)
            return None, False, causes
        start, end = span['start'], span['end']
        details.update(start=start, end=end)
        if end <= start:
            # SourceSpan's schema already owns this bound.
            causes = invalid_causes(path)
            diagnostics.defer('span_quote', path, causes, 'Span interval is reversed or empty.')
            return None, False, causes
        if end > len(query):
            cause = diagnostics.error('span_out_of_bounds', path, **details,
                source_text=span.get('source_text') if isinstance(span.get('source_text'), str) else None,
                message=f'Interval exceeds {ASSESSMENT_QUERY_PATH} length {len(query)}.')
            diagnostics.defer('span_quote', path, [cause], 'A complete in-range slice is unavailable.')
            return None, False, [cause]
        if not valid_field(span, span_schema, 'source_text'):
            causes = invalid_causes(path + '.source_text')
            diagnostics.defer('span_quote', path, causes)
            return (start, end), False, causes
        if query[start:end] != span['source_text']:
            cause = diagnostics.error('span_text_mismatch', path, **details,
                source_text=span['source_text'], actual_text=query[start:end])
            return (start, end), False, [cause]
        return (start, end), True, []

    if not isinstance(raw.get('semantic_units'), list):
        unknown_geometry.extend(invalid_causes('semantic_units'))
        unknown_unit_ids.extend(invalid_causes('semantic_units'))
        unknown_state_links.extend(invalid_causes('semantic_units'))
    elif not units:
        if not diagnostics.causes('semantic_units'):
            diagnostics.error('missing_semantic_units', 'semantic_units', message='Semantic units must be present with unique IDs.')
    if not isinstance(raw.get('unresolved_states', []), list):
        unknown_state_ids.extend(invalid_causes('unresolved_states'))

    for index, unit in enumerate(units):
        path = f'semantic_units[{index}]'
        if not isinstance(unit, dict):
            causes = invalid_causes(path)
            unknown_geometry.extend(causes)
            unknown_unit_ids.extend(causes)
            unknown_state_links.extend(causes)
            diagnostics.defer('unit_structure', path, causes)
            continue
        uid = unit.get('unit_id')
        if valid_field(unit, unit_schema, 'unit_id'):
            unit_ids[uid].append(index)
        else:
            unknown_unit_ids.extend(invalid_causes(path + '.unit_id'))
        if not valid_field(unit, unit_schema, 'state_id'):
            unknown_state_links.extend(invalid_causes(path + '.state_id'))
        spans = unit.get('spans')
        if not isinstance(spans, list):
            causes = invalid_causes(path + '.spans')
            unknown_geometry.extend(causes)
            diagnostics.defer('unit_span_geometry', path + '.spans', causes)
            continue
        previous = None
        for n, span in enumerate(spans):
            span_path = f'{path}.spans[{n}]'
            interval, quoted, causes = span_check(span, span_path, unit_id=uid)
            if interval is None:
                unknown_geometry.extend(causes)
                diagnostics.defer('unit_span_order', path + '.spans', causes)
                continue
            start, end = interval
            if previous is not None and start < previous[0]:
                diagnostics.error('spans_out_of_order', span_path, unit_id=uid if isinstance(uid,str) else None,
                    start=start, end=end, related_paths=[previous[2]])
            previous = (start, end, span_path)
            row = dict(start=start, end=end, path=span_path, index=index, unit_id=uid if isinstance(uid,str) else None)
            geometry.append(row)
            unit_intervals[index].append(row)

    # Pairwise intersections are independent of ordering and count/state citations.
    for n, current in enumerate(geometry):
        for previous in geometry[:n]:
            start, end = max(current['start'], previous['start']), min(current['end'], previous['end'])
            if start < end:
                diagnostics.error('overlapping_spans', current['path'], start=start, end=end,
                    actual_text=query[start:end], related_paths=[previous['path'], current['path']],
                    related_unit_ids=[u for u in (previous['unit_id'], current['unit_id']) if u is not None])
    covered = defaultdict(list)
    for row in geometry:
        for position in range(row['start'], row['end']):
            covered[position].append(row['index'])
    if unknown_geometry:
        diagnostics.defer('coverage', 'semantic_units', unknown_geometry,
            'Unknown span intervals may cover apparent gaps; do not infer missing characters.')
    else:
        for start, end in ranges(i for i,c in enumerate(query) if not c.isspace() and i not in covered):
            diagnostics.error('uncovered_characters', 'semantic_units', start=start, end=end, actual_text=query[start:end])

    for index, state in enumerate(states):
        path = f'unresolved_states[{index}]'
        if not isinstance(state, dict):
            causes = invalid_causes(path)
            unknown_state_ids.extend(causes)
            diagnostics.defer('state_evidence', path, causes)
            continue
        sid = state.get('state_id')
        if valid_field(state, state_schema, 'state_id'):
            state_ids[sid].append(index)
        else:
            causes = invalid_causes(path + '.state_id')
            unknown_state_ids.extend(causes)
            diagnostics.defer('state_unit_assignment_and_evidence_membership', path, causes)
        if not isinstance(state.get('evidence'), list):
            diagnostics.defer('state_evidence', path + '.evidence', invalid_causes(path + '.evidence'))
            continue
        for n, span in enumerate(state['evidence']):
            span_path = f'{path}.evidence[{n}]'
            interval, quoted, causes = span_check(span, span_path, state_id=sid)
            state_spans[index].append((span_path, interval, quoted, causes))
    count_spans = raw.get('count_evidence', [])
    if isinstance(count_spans, list):
        for index, span in enumerate(count_spans):
            span_check(span, f'count_evidence[{index}]')
    else:
        diagnostics.defer('count_evidence_quotes', 'count_evidence', invalid_causes('count_evidence'))

    for name, identities, field in [('semantic_units', unit_ids, 'unit_id'), ('unresolved_states', state_ids, 'state_id')]:
        for identity, indices in identities.items():
            if len(indices) > 1:
                # Replace the same root schema diagnostic with a located diagnostic.
                if field == 'state_id':
                    diagnostics.errors[:] = [e for e in diagnostics.errors if e.get('message') != 'Value error, Assessment state IDs must be unique.']
                diagnostics.error('duplicate_' + field, name, referenced_id=identity,
                    related_paths=[f'{name}[{i}].{field}' for i in indices])

    for index, unit in enumerate(units):
        if not isinstance(unit, dict):
            continue
        path, uid, sid = f'semantic_units[{index}]', unit.get('unit_id'), unit.get('state_id')
        valid_sid = valid_field(unit, unit_schema, 'state_id')
        if not valid_sid or not valid_field(unit, unit_schema, 'kind'):
            diagnostics.defer('state_assignment', path, invalid_causes(path))
        if valid_sid and valid_field(unit, unit_schema, 'kind'):
            if (unit['kind'] == 'unresolved_condition') != (sid is not None):
                diagnostics.error('invalid_state_assignment', path, message='Only unresolved units must carry a state_id.')
        if valid_sid and sid is not None and sid not in state_ids:
            if unknown_state_ids:
                diagnostics.defer('state_reference', path + '.state_id', unknown_state_ids)
            else:
                diagnostics.error('unknown_state', path + '.state_id', referenced_id=sid)
        if raw.get('decision') == 'proceed' and valid_sid and sid is not None:
            if valid_field(unit, unit_schema, 'independently_removable'):
                if not unit['independently_removable']:
                    diagnostics.error('unsafe_unresolved_unit', path, unit_id=uid if isinstance(uid,str) else None,
                        message='Unresolved meaning cannot be safely separated; regroup the units.')
            else:
                diagnostics.defer('removal_safety', path, invalid_causes(path + '.independently_removable'))
        if not isinstance(unit.get('depends_on', []), list):
            diagnostics.defer('dependency_references', path + '.depends_on', invalid_causes(path + '.depends_on'))
            continue
        seen = set()
        for n, ref in enumerate(unit.get('depends_on', [])):
            dep_path = path + '.depends_on'
            if not isinstance(ref, str) or not ref.strip():
                diagnostics.defer('dependency_reference', f'{dep_path}[{n}]', invalid_causes(f'{dep_path}[{n}]'))
                continue
            if ref in seen:
                diagnostics.error('duplicate_dependency', dep_path, referenced_id=ref)
                continue
            seen.add(ref)
            if ref == uid:
                diagnostics.error('self_dependency', dep_path, referenced_id=ref)
                continue
            targets = unit_ids.get(ref, [])
            if not targets:
                if unknown_unit_ids:
                    diagnostics.defer('dependency_reference', f'{dep_path}[{n}]', unknown_unit_ids)
                else:
                    diagnostics.error('unknown_dependency', dep_path, referenced_id=ref)
                continue
            if len(targets) > 1:
                diagnostics.defer('dependency_safety', f'{dep_path}[{n}]', diagnostics.causes('semantic_units'),
                    'Referenced unit ID is ambiguous.')
                continue
            target = units[targets[0]]
            target_path = f'semantic_units[{targets[0]}].state_id'
            if not valid_sid or not valid_field(target, unit_schema, 'state_id'):
                diagnostics.defer('dependency_safety', f'{dep_path}[{n}]',
                    invalid_causes(path + '.state_id') + invalid_causes(target_path))
            elif raw.get('decision') == 'proceed' and target.get('state_id') is not None and target['state_id'] != sid:
                diagnostics.error('unsafe_dependency', dep_path, referenced_id=ref,
                    message='Removing an unresolved condition could change retained meaning.')

    for sid, indices in state_ids.items():
        if len(indices) > 1:
            for index in indices:
                diagnostics.defer('state_evidence_membership', f'unresolved_states[{index}].evidence',
                    diagnostics.causes('unresolved_states'), 'State ID is ambiguous.')
            continue
        index = indices[0]
        path = f'unresolved_states[{index}]'
        assigned = [n for n,u in enumerate(units) if isinstance(u,dict)
            and valid_field(u, unit_schema, 'state_id') and u.get('state_id') == sid]
        if not assigned:
            if unknown_state_links:
                diagnostics.defer('state_unit_assignment', path, unknown_state_links)
            else:
                diagnostics.error('state_without_unit', path, state_id=sid)
        for span_path, interval, quoted, causes in state_spans[index]:
            if not quoted or interval is None:
                diagnostics.defer('state_evidence_membership', span_path, causes)
                continue
            invalid = []
            uncertain = []
            for pos in range(*interval):
                if query[pos].isspace():
                    continue  # Preserve the existing ownership rule for evidence whitespace.
                owners = covered.get(pos, [])
                if not owners and unknown_geometry:
                    uncertain.extend(unknown_geometry)
                elif len(owners) > 1:
                    uncertain.extend(diagnostics.causes('semantic_units'))
                elif any(not valid_field(units[o], unit_schema, 'state_id') for o in owners):
                    uncertain.extend(unknown_state_links)
                elif not owners or units[owners[0]].get('state_id') != sid:
                    invalid.append(pos)
            if uncertain:
                diagnostics.defer('state_evidence_membership', span_path, uncertain)
            for start, end in ranges(invalid):
                diagnostics.error('state_evidence_outside_unit', span_path, state_id=sid,
                    start=start, end=end, actual_text=query[start:end])
    if result is None:
        diagnostics.defer('schema_cross_field_contract', '$', [e['error_id'] for e in diagnostics.errors
            if e['code'] == 'schema_validation_error'] or [e['error_id'] for e in diagnostics.errors],
            'Complete schema validation must run again after structural or cross-field errors are corrected.')
    if not valid_field(raw, schema, 'decision'):
        diagnostics.defer('dependency_and_removal_safety', 'semantic_units', invalid_causes('decision'))
    return result, diagnostics.report()


def inspect_received_response(snapshot, query, *, schema, error=None):
    """Return diagnostics and a lossless correction envelope, never a repaired payload."""
    import json
    raw = snapshot.get('model_response')
    text = snapshot.get('model_response_text')
    previous = None
    parsing_error = None
    if raw is not None or text is not None:
        previous = dict(model_response=deepcopy(raw), model_response_text=text, parsing_error=None)
        if raw is None and text is not None:
            try:
                raw = json.loads(text)
            except (ValueError, TypeError) as exc:
                parsing_error = str(exc)
                previous['parsing_error'] = parsing_error
    if previous is None or parsing_error:
        diagnostics = Diagnostics()
        if parsing_error:
            diagnostics.error('parsing_error', '$', message=parsing_error)
        elif isinstance(error, ValidationError):
            for row in error.errors(include_url=False, include_context=False, include_input=False):
                diagnostics.error('schema_validation_error', diagnostic_path(row['loc']),
                    message=row['msg'], schema_error_type=row['type'])
        else:
            diagnostics.error('response_unavailable', '$', message=str(error) if error else 'No API assessment response was received.')
        causes = [e['error_id'] for e in diagnostics.errors]
        for check in ('schema', 'span_quotes', 'coverage', 'overlap_and_order', 'id_references', 'state_evidence', 'dependency_safety'):
            diagnostics.defer(check, '$', causes, 'No parseable response is available; the failed response is not an assessment.')
        return None, diagnostics.report(), previous
    result, report = collect_segmentation(raw, query, schema=schema)
    if error is not None and not report['errors']:
        report['errors'].append(dict(error_id='error_transport', code='response_error', path='$', message=str(error)))
    # An SDK/API failure is never promoted to a successful model response.
    return result, report, previous


REMOVAL_GUIDANCE_V8 = """
해당 구절을 제외했을 때 남은 명확한 조건의 의미·부정·OR·범위가 유지되는지 다시 판단하라.
단순 수식 관계와 의미 보존에 필요한 의존관계를 구분하라.
명확한 상품 조건을 미해결 단위에 합쳐 오류를 해결하지 말라.
분리 가능하다고 판단한 경우에만 independently_removable을 수정하라.
실제로 의미가 훼손되면 true로 강제하지 않는다.
수정 후 원문 포함·인용 위치·상태 연결·의존관계를 모두 다시 확인하라.
"""


def add_removal_feedback(report):
    """Enrich v8 diagnostics only; preserve error identity and the received response."""
    for error in report['errors']:
        if error['code'] == 'unsafe_unresolved_unit':
            unit = error.get('unit_id') or error['path']
            error['message'] = (f'{unit}은 미해결 단위인데 independently_removable=false로 기록됐다.\n'
                                + REMOVAL_GUIDANCE_V8.strip())
