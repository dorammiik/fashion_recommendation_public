"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- product_validation ----

"""Shared definitions moved unchanged from their former owner."""
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_validation import EvaluationBatchInput
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_validation import EvaluationBatchOutput

@_preserve_class('InvalidEvaluation', 'fashion_recommendation_v2.search.product_validation')
class InvalidEvaluation(ValueError):

    def __init__(self, message: str, code: str='invalid_response', *, requirement_id=None, fields=None):
        self.code = code
        self.requirement_id = requirement_id
        self.fields = fields or []
        super().__init__(message)
from fashion_recommendation_v2.search.product_sources import evidence_fields
from fashion_recommendation_v2.search.product_sources import present_field as present_field_base

@_preserve_function('validate_observations', 'fashion_recommendation_v2.search.product_validation')
def validate_observations(observations, item):
    for obs in observations:
        if obs.attribute == 'size':
            raise ValueError('Size excluded from preference scoring')
        if any((not present_field_base(item, f, None) for f in obs.evidence_fields)):
            raise ValueError('Preference observation cites absent metadata')
        if any((e.image_url != item.image_url for e in obs.image_evidence)):
            raise ValueError('Preference observation cites another item image')
        if not (obs.evidence_fields and any((t.strip() for t in obs.evidence)) or obs.image_evidence):
            raise ValueError('Preference observation needs product evidence')
        if obs.attribute in ('material', 'brand', 'category_path', 'title_keywords') and (not obs.evidence_fields):
            raise ValueError('This attribute requires metadata, not visual inference')
        if obs.attribute == 'title_keywords' and 'title' not in obs.evidence_fields:
            raise ValueError('Title keywords require title evidence')
        if obs.attribute == 'category_path':
            values = obs.value if isinstance(obs.value, list) else [obs.value]
            if 'category_path' not in obs.evidence_fields or any((v != item.category_path for v in values)):
                raise ValueError('Category path must preserve the exact source metadata')

@_preserve_function('validate_evidence_batch', 'fashion_recommendation_v2.search.product_validation')
def validate_evidence_batch(result: EvaluationBatchOutput, request: EvaluationBatchInput, *, judgment_requirement_ids=None) -> None:
    expected_items = {entry.item.item_id: entry.item for entry in request.items}
    actual_ids = [entry.item_id for entry in result.items]
    if len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != set(expected_items):
        raise InvalidEvaluation('Missing, duplicate or unknown item judgments.', 'missing_assessments')
    expected_requirements = {entry.requirement_id for entry in request.resolved_requirements.requirements}
    expected_judgments = expected_requirements if judgment_requirement_ids is None else judgment_requirement_ids
    for output in result.items:
        actual = [entry.requirement_id for entry in output.judgments]
        if len(actual) != len(set(actual)) or set(actual) != expected_judgments:
            raise InvalidEvaluation(f'Missing, duplicate or unknown requirement judgments. Expected: {sorted(expected_judgments)}; received: {actual}', 'missing_assessments', requirement_id=next((key for key in sorted(expected_judgments) if actual.count(key) != 1), None))
        item = expected_items[output.item_id]
        for judgment in output.judgments:
            missing = [field for field in judgment.evidence_fields if not present_field_base(item, field, request.price_conversion)]
            if missing:
                raise InvalidEvaluation('Judgment cites an absent metadata field.', requirement_id=judgment.requirement_id, fields=missing)
            if any((e.image_url != item.image_url for e in judgment.image_evidence)):
                raise InvalidEvaluation('Judgment cites another image.', requirement_id=judgment.requirement_id)
            supported = judgment.evidence_fields and any((text.strip() for text in judgment.evidence)) or judgment.image_evidence
            if judgment.status != 'unknown' and (not supported):
                raise InvalidEvaluation('Non-unknown judgments require product evidence.', requirement_id=judgment.requirement_id)
            if judgment.status == 'unknown' and (not any((text.strip() for text in judgment.evidence))):
                raise InvalidEvaluation('Unknown judgments must explain missing information.', requirement_id=judgment.requirement_id)
        hard_ids = {r.requirement_id for r in request.resolved_requirements.requirements if r.kind == 'hard'}
        try:
            validate_observations(output.preference_features, item)
            allowed = {entry['attribute'] for entry in request.preference_vocabulary}
            if any((obs.attribute not in allowed for obs in output.preference_features)):
                raise ValueError('Preference observation outside requested attributes')
        except ValueError as exc:
            raise InvalidEvaluation(str(exc)) from exc
        for feature in output.diversity_features:
            if not set(feature.fixed_by_requirement_ids) <= hard_ids:
                raise InvalidEvaluation('Diversity feature references a non-hard or unknown requirement.')
            missing = [field for field in feature.evidence_fields if not present_field_base(item, field, request.price_conversion)]
            if missing:
                raise InvalidEvaluation('Diversity feature cites an absent metadata field.', fields=missing)
            if any((e.image_url != item.image_url for e in feature.image_evidence)):
                raise InvalidEvaluation('Diversity feature cites another image.')
            if not (feature.evidence_fields and any((t.strip() for t in feature.evidence)) or feature.image_evidence):
                raise InvalidEvaluation('Diversity features require product evidence.')
        for conflict in output.conflicts:
            if conflict.requirement_id is not None and conflict.requirement_id not in expected_requirements:
                raise InvalidEvaluation('Conflict cites an unknown requirement.')
            if any((not present_field_base(item, field, request.price_conversion) for field in conflict.evidence_fields)):
                raise InvalidEvaluation('Conflict cites an absent metadata field.', requirement_id=conflict.requirement_id, fields=[field for field in conflict.evidence_fields if not present_field_base(item, field, request.price_conversion)])
            if any((e.image_url != item.image_url for e in conflict.image_evidence)):
                raise InvalidEvaluation('Conflict cites another image.')
from fashion_recommendation_v2.llm.base import ImageInput

@_preserve_function('validate_analysis', 'fashion_recommendation_v2.search.product_validation')
def validate_analysis(analysis, item, requirements, conversion):
    if analysis.evaluation_policy in {'v36', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v57', 'v59'}:
        from fashion_recommendation_v2.search.product_evaluation import validate_analysis as validate_v36
        return validate_v36(analysis, item, requirements, conversion)
    from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_validation import EvaluationBatchInput
    from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_validation import EvaluationItem
    from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_validation import EvaluationBatchOutput
    from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_validation import ItemJudgments
    if analysis.evaluation_policy in {'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35'}:
        from fashion_recommendation_v2.search.evidence_projection import validate_product_facts
        from fashion_recommendation_v2.search.condition_semantics import validate_condition_contract
        validate_condition_contract(requirements)
        validate_product_facts(analysis, item)
    if analysis.item_id != item.item_id or analysis.image_url != item.image_url:
        raise ValueError('Search visual analysis item/image identity mismatch.')
    if item.image_url:
        ImageInput(item_id=item.item_id, image_url=item.image_url)
    request = EvaluationBatchInput(user_request='Validate saved Search evidence', resolved_requirements=requirements, price_conversion=conversion, items=[EvaluationItem(item=item, hard_constraint_assessments=[])])
    validate_evidence_batch(EvaluationBatchOutput(items=[ItemJudgments(item_id=item.item_id, judgments=analysis.judgments, conflicts=analysis.conflicts, diversity_features=analysis.known_attributes)]), request)
    for feature in analysis.known_attributes:
        if any((conflict.attribute == feature.attribute for conflict in analysis.conflicts)):
            raise ValueError('Unresolved conflicting attributes must be omitted from observed features.')
        if feature.attribute in {'material', 'gender'} and (not feature.evidence_fields):
            raise ValueError('Material and product gender require metadata evidence.')
    if not item.image_url and (analysis.thum_quality != 'low' or analysis.thumbnail_kind != 'unknown'):
        raise ValueError('Missing image must have unknown thumbnail kind and low quality.')


# ---- product_validation_v29 ----

"""Derive usable evidence without rewriting or relaxing the model response.

Only the explicitly supported evidence errors are localized. The resulting slot
must still pass the original typed output contract and all admission checks.
Identity, unknown fields, missing condition IDs and invalid types remain errors.
"""
from copy import deepcopy
from fashion_recommendation_v2.search.product_sources import present_field
from fashion_recommendation_v2.search.condition_semantics import METADATA_ONLY_FACTS
from fashion_recommendation_v2.search.condition_semantics import observation_key as key

@_preserve_function('related', 'fashion_recommendation_v2.search.product_validation_v29')
def related(a, b):
    return a == b or (a == 'detail' and b.startswith('detail.')) or (b == 'detail' and a.startswith('detail.'))

@_preserve_function('project_slot', 'fashion_recommendation_v2.search.product_validation_v29')
def project_slot(raw, item, context, core_schema):
    """Return a separate projection and diagnostics; never mutate raw/context."""
    from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import AttributeV10_v10 as AttributeV10
    from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import ProductFactDraftV26
    from fashion_recommendation_v2.schemas.visual_confirmation import VisualConfirmationV5
    required = {*core_schema.model_fields, 'product_facts_v26'}
    if not isinstance(raw, dict) or not required <= set(raw) <= required | {'visual_confirmation_v5'}:
        raise ValueError('Cannot project missing/unknown product fields or identity fields.')
    data, changes = (deepcopy(raw), [])
    requirements = {r['requirement_id']: r for r in context['resolved_requirements']['requirements']}
    definitions = context['resolved_requirements'].get('condition_contract_v26') or {}

    def condition_key(rid):
        # Use the same frozen definition used by Search and image observation,
        # including detail.features values bound to a known slit/cutout meaning.
        name = definitions.get(rid, {}).get('key', key(requirements[rid]))
        return 'category' if name in {'product_type', 'avoid_product_type'} else name
    # Validate keyed identity before any derivation: no guessed IDs or positions.
    for field in ('judgments', 'hard_condition_findings', 'alternative_judgments'):
        expected = core_schema.model_fields[field].annotation.model_fields
        if not isinstance(data[field], dict) or set(data[field]) != set(expected):
            raise ValueError(f'Missing/unknown condition IDs in {field}.')
        if field == 'alternative_judgments':
            for rid, spec in expected.items():
                if not isinstance(data[field][rid], dict) or set(data[field][rid]) != set(spec.annotation.model_fields):
                    raise ValueError('Missing/unknown OR alternative IDs.')

    def note(path, reason, before, after):
        changes.append(dict(path=path, reason=reason, before=deepcopy(before), after=deepcopy(after)))

    def citations(row, path):
        old = row['evidence_fields']
        if not isinstance(old, list) or any((not isinstance(p, str) for p in old)):
            raise ValueError('Evidence paths must remain a list of strings.')
        valid = [p for p in old if present_field(item, p, None)]
        if valid != old:
            note(path + '.evidence_fields', 'absent_metadata_path', old, valid)
            row['evidence_fields'] = valid
        # Image URLs are code-bound. Never delete or rewrite an unexpected URL.
        for image in row['image_evidence']:
            if set(image) != {'observation'} or not isinstance(image['observation'], str) or (not image['observation'].strip()):
                raise ValueError('Invalid image observation or unexpected image identity.')
        return bool(valid and any((t.strip() for t in row.get('evidence', row.get('metadata_evidence', [])))) or row['image_evidence'])
    disputed, disputed_ids = (set(), set())
    conflicts = []
    conflict_schema = core_schema.model_fields['conflicts'].annotation.__args__[0]
    for index, row in enumerate(data['conflicts']):
        path = f'conflicts.{index}'
        # Validate fields/status without constraining citations to the item yet.
        # Validate structure independently of the evidence-path enum first.
        from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import ConflictV10
        ConflictV10.model_validate(row)
        if row.get('requirement_id') is not None and row['requirement_id'] not in requirements:
            raise ValueError('Conflict cites an unknown requirement.')
        disputed.add(key(row))
        if row.get('requirement_id'):
            disputed_ids.add(row['requirement_id'])
        citations(row, path)
        if row['evidence_fields']:
            conflict_schema.model_validate(row)
            conflicts.append(row)
        else:
            note(path, 'unverifiable_conflict_kept_in_diagnostics; affected_values_unknown', raw['conflicts'][index], None)
    data['conflicts'] = conflicts
    for index, row in enumerate(data['attributes']):
        # Do not conceal unrelated shape/type/group errors by replacing a row.
        AttributeV10.model_validate(row)
        path = f'attributes.{index}'
        supported = citations(row, path)
        is_disputed = any((related(key(row), d) for d in disputed))
        if row['value'] != 'unknown' and (is_disputed or not supported or (row['attribute'] in {'material', 'gender'} and (not row['evidence_fields']))):
            before = deepcopy(row)
            row.update(value='unknown', evidence_fields=[], image_evidence=[], evidence=['Code: conflicting or unsupported observation.'], fixed_by_requirement_ids=[])
            note(path, 'conflicting_or_unsupported_attribute', before, row)
        elif row['value'] != 'unknown':
            fixed = [rid for rid, req in requirements.items() if req['kind'] == 'hard' and (not req.get('unrestricted')) and (key(req) == key(row)) and isinstance(req['value'], str) and (req['value'] == row['value'])]
            if row['fixed_by_requirement_ids'] != fixed:
                note(path + '.fixed_by_requirement_ids', 'code_exact_hard_value_binding', row['fixed_by_requirement_ids'], fixed)
                row['fixed_by_requirement_ids'] = fixed
    # Existing unknown-with-evidence validation is deliberately unchanged.
    facts = []
    for index, row in enumerate(data['product_facts_v26']):
        path = f'product_facts_v26.{index}'
        # The known-fact evidence validator is evaluated after source projection.
        # Type/attribute/value/identity errors remain fatal, including duplicate facts.
        fields = ProductFactDraftV26.model_fields
        if set(row) != set(fields):
            raise ValueError('Missing/unknown product fact fields.')
        from pydantic import TypeAdapter
        for name, field in fields.items():
            TypeAdapter(field.annotation).validate_python(row[name])
        if (row['attribute'] == 'detail') != isinstance(row['value'], dict):
            raise ValueError('Only detail uses the key/values shape.')
        supported = citations(row, path)
        if any((related(key(row), d) for d in disputed)) or not supported or (key(row) in METADATA_ONLY_FACTS and (not row['evidence_fields'])):
            note(path, 'conflicting_or_unsupported_product_fact', raw['product_facts_v26'][index], None)
        else:
            ProductFactDraftV26.model_validate(row)
            facts.append(row)
    data['product_facts_v26'] = facts

    def judgment(row, rid, path):
        from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import JudgmentV10_v10 as JudgmentV10
        JudgmentV10.model_validate(dict(requirement_id=rid, **row))
        supported = citations(row, path)
        if rid in disputed_ids or any((related(condition_key(rid), d) for d in disputed)) or (not supported):
            if row['status'] != 'unknown':
                old = deepcopy(row)
                row.update(status='unknown', evidence_fields=[], image_evidence=[], evidence=['Code: no validated evidence for this condition, or unresolved conflict.'])
                note(path, 'unsupported_condition_judgment', old, row)
        if row['status'] == 'unknown' and (not any((t.strip() for t in row['evidence']))):
            row['evidence'] = ['Code: condition evidence unavailable.']
    for rid, row in data['judgments'].items():
        judgment(row, rid, f'judgments.{rid}')
    for rid, alternatives in data['alternative_judgments'].items():
        for aid, row in alternatives.items():
            judgment(row, rid, f'alternative_judgments.{rid}.{aid}')
        statuses = [r['status'] for r in alternatives.values()]
        status = 'met' if 'met' in statuses else 'unmet' if all((s == 'unmet' for s in statuses)) else 'unknown'
        old = deepcopy(data['judgments'][rid])
        contributing = [r for r in alternatives.values() if r['status'] == status]
        aggregate = dict(status=status, evidence_fields=list(dict.fromkeys((p for r in contributing for p in r['evidence_fields']))), image_evidence=[deepcopy(e) for r in contributing for e in r['image_evidence']], evidence=[e for r in contributing for e in r['evidence']] or ['Code: OR alternatives are not conclusively satisfied.'])
        if old != aggregate:
            data['judgments'][rid] = aggregate
            note(f'judgments.{rid}', 'code_OR_aggregation', old, aggregate)
    # Findings cannot promote unsupported judgments or silently reverse OR logic.
    # Preserve a declared clear hard mismatch unless verified OR alternatives resolve it.
    for rid, finding in data['hard_condition_findings'].items():
        core_schema.model_fields['hard_condition_findings'].annotation.model_fields[rid].annotation.model_validate(finding)
        status = data['judgments'][rid]['status']
        expected = 'matched' if status == 'met' else 'clear_mismatch' if status == 'unmet' else 'insufficient_evidence'
        if finding['finding'] != 'matched' and status == 'met' and (rid not in data['alternative_judgments']):
            note(f'judgments.{rid}.status', 'hard_finding_disagrees_with_met_judgment', 'met', 'unknown')
            data['judgments'][rid]['status'] = 'unknown'
            expected = 'insufficient_evidence'
        derived = dict(finding=expected, evidence='Code: derived from the validated condition judgment.')
        if finding['finding'] != expected:
            note(f'hard_condition_findings.{rid}', 'code_condition_finding', finding, derived)
            data['hard_condition_findings'][rid] = derived
    # photo_type and support remain separate. Only the redundant root is derived.
    observation = core_schema.model_fields['thumbnail_observation_v8'].annotation.model_validate(data['thumbnail_observation_v8'])
    if data['thumbnail_kind'] != observation.photo_type:
        note('thumbnail_kind', 'canonical_photo_type', data['thumbnail_kind'], observation.photo_type)
        data['thumbnail_kind'] = observation.photo_type
    ranking_error = None
    try:
        VisualConfirmationV5.model_validate(data.get('visual_confirmation_v5'))
    except ValueError as exc:
        ranking_error = str(exc)
        note('visual_confirmation_v5', 'auxiliary_ranking_observation_invalid', data.get('visual_confirmation_v5'), None)
        data['visual_confirmation_v5'] = None
    core_schema.model_validate({k: data[k] for k in core_schema.model_fields})
    return (data, dict(status='projected' if changes else 'passed', changes=changes), ranking_error)
