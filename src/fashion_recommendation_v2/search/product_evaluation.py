"""Role-consolidated implementation; service contracts and behavior are preserved."""
from __future__ import annotations
from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function

# ---- product_evaluation_v32 ----
"""Expand compact evidence into a separate, fully validated execution projection."""
from copy import deepcopy as deepcopy_v32
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import ATTRIBUTE_GROUPS_v32
from fashion_recommendation_v2.search.product_validation import project_slot as project_v29_v32

from fashion_recommendation_v2.search.audience_policy import GENDER_ALIASES
from fashion_recommendation_v2.search.audience_policy import canonical_gender

@_preserve_function('expand_slot', 'fashion_recommendation_v2.search.product_evaluation_v32')
def expand_slot_v32(raw, schema):
    """No source response is mutated; missing IDs/types/extra fields stay errors."""
    # Visibility remains auxiliary: its failure must not hide unrelated errors.
    from pydantic import create_model
    from fashion_recommendation_v2.schemas.base import StrictBaseModel
    from fashion_recommendation_v2.schemas.product_evidence import ProductFactV26
    from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import FactV32_v32 as FactV32
    recoverable_fact = create_model('RecoverableFactV32', __base__=FactV32,
        attribute=(ProductFactV26.model_fields['attribute'].annotation, ...))
    fields = {k: (f.annotation, deepcopy_v32(f)) for k, f in schema.model_fields.items()
              if k != 'visual_confirmation_v5'}
    fields['product_facts_v26'] = (list[recoverable_fact], ...)
    checked = create_model('AdmissionWireV32', __base__=StrictBaseModel, **fields)
    if not isinstance(raw, dict):
        raise ValueError('Expected product object.')
    allowed = set(schema.model_fields)
    if not allowed - {'visual_confirmation_v5'} <= set(raw) <= allowed:
        raise ValueError('Missing/unknown compact product fields.')
    checked.model_validate({k: v for k, v in raw.items() if k != 'visual_confirmation_v5'})
    data, changes = deepcopy_v32(raw), []
    data.setdefault('visual_confirmation_v5', None)
    table = {}
    for rid, row in enumerate(data.pop('evidence'), 1):
        table[rid] = {**row, 'image_evidence': [dict(observation=text) for text in row['image_evidence']]}
    used = set()

    def expand(row, path, *, conflict=False):
        ids = row.pop('evidence_ids')
        if any(i not in table for i in ids):
            raise ValueError(f'{path}: unknown product-local evidence IDs.')
        if len(ids) != len(set(ids)):
            changes.append(dict(path=path, reason='identical_evidence_reference_repeated', evidence_ids=deepcopy_v32(ids)))
            ids = list(dict.fromkeys(ids))
        used.update(ids)
        values = {field: [] for field in ('evidence_fields', 'evidence', 'image_evidence')}
        for rid in ids:
            for field, entries in table[rid].items():
                for entry in entries:
                    if entry not in values[field]:
                        values[field].append(deepcopy_v32(entry))
        if conflict:
            values['metadata_evidence'] = values.pop('evidence')
        row.update(values)
        changes.append(dict(path=path, reason='expanded_product_local_evidence', evidence_ids=ids))
        return row

    for field in ('attributes', 'product_facts_v26', 'conflicts'):
        for index, row in enumerate(data[field]):
            expand(row, f'{field}.{index}', conflict=field == 'conflicts')
    for rid, row in data['judgments'].items():
        expand(row, 'judgments.' + rid)
    for rid, alternatives in data['alternative_judgments'].items():
        for aid, row in alternatives.items():
            expand(row, f'alternative_judgments.{rid}.{aid}')
    if used != set(table):
        # Unused but structurally valid observations do not invalidate used evidence.
        # Preserve them in the original response and explicitly record their IDs.
        changes.append(dict(path='evidence', reason='unreferenced_evidence_not_used',
                            evidence_ids=sorted(set(table) - used)))
    canonicalize_facts_v32(data, changes)
    photo = data['thumbnail_observation_v8']
    data['thumbnail_kind'] = photo['photo_type']
    data['thumbnail_evidence'] = photo['evidence']
    return data, changes


@_preserve_function('canonicalize_facts', 'fashion_recommendation_v2.search.product_evaluation_v32')
def canonicalize_facts_v32(data, changes):
    """Shared exact-value projection for compact and observation-based contracts."""
    for row in data['attributes']:
        row['group'] = ATTRIBUTE_GROUPS_v32[row['attribute']]
        row['fixed_by_requirement_ids'] = []
        if row['attribute'] == 'gender':
            before = deepcopy_v32(row['value'])
            row['value'] = canonical_gender(before)
            if before != row['value']:
                changes.append(dict(path='attributes.gender.value', reason='canonical_audience_alias', before=before, after=row['value']))

    # One fact location per attribute. Recovery never merges unequal values or
    # changes OR lists/types. Retain every distinct citation in the derived row.
    def combine(target, incoming, path):
        if type(target['value']) is not type(incoming['value']) or target['value'] != incoming['value']:
            raise ValueError(f'{path}: conflicting duplicate values; no automatic merge.')
        for field in ('evidence_fields', 'evidence', 'image_evidence'):
            for value in incoming[field]:
                if value not in target[field]: target[field].append(deepcopy_v32(value))
        changes.append(dict(path=path, reason='identical_fact_merged_preserving_all_evidence'))
    attrs = {}
    for row in data['attributes']:
        name = row['attribute']
        if name in attrs: combine(attrs[name], row, 'attributes.' + name)
        else: attrs[name] = row
    facts = {}
    for row in data['product_facts_v26']:
        name = row['attribute']
        if name in ATTRIBUTE_GROUPS_v32:
            if name == 'gender': row['value'] = canonical_gender(row['value'])
            if name in attrs:
                combine(attrs[name], row, 'product_facts_v26.' + name)
            else:
                attrs[name] = dict(row, group=ATTRIBUTE_GROUPS_v32[name], fixed_by_requirement_ids=[])
                changes.append(dict(path='product_facts_v26.' + name, reason='known_dimension_projected_to_attributes'))
        else:
            key = 'detail.' + row['value']['key'] if isinstance(row['value'], dict) else name
            if key in facts: combine(facts[key], row, 'product_facts_v26.' + key)
            else: facts[key] = row
    data['attributes'], data['product_facts_v26'] = list(attrs.values()), list(facts.values())


@_preserve_function('project_slot', 'fashion_recommendation_v2.search.product_evaluation_v32')
def project_slot_v32(raw, item, context, core_schema, wire_schema):
    expanded, changes = expand_slot_v32(raw, wire_schema)
    data, diagnostic, ranking_error = project_v29_v32(expanded, item, context, core_schema)
    diagnostic['wire_version'] = 'v32'
    diagnostic['changes'] = changes + diagnostic['changes']
    diagnostic['status'] = 'projected'
    return data, diagnostic, ranking_error


@_preserve_function('evaluation_context', 'fashion_recommendation_v2.search.product_evaluation_v32')
def evaluation_context(context):
    """Keep product/source paths intact; emit only one condition-definition table."""
    data = deepcopy_v32(context)
    # These are exactly represented by the keyed output schema/alternative map.
    # Keep requirements with original attributes/values/quotes and all items intact.
    for field in ('required_judgment_ids', 'required_hard_finding_ids', 'required_alternatives'):
        data.pop(field, None)
    return data


# ---- product_evaluation_v42 ----
"""Validate native fixed-slot responses before constructing separate consumer records."""
from copy import deepcopy
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import product_schema_v42
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import fixed_keys_v42 as fixed_keys


@_preserve_function('consumer_projection', 'fashion_recommendation_v2.search.product_evaluation_v42')
def consumer_projection_v42(raw, requirements):
    # Validate original structure, including all required keys, BEFORE deriving any record.
    product_schema_v42(requirements).model_validate(raw)
    keys = set(fixed_keys(requirements))
    extras = raw['additional_details']
    for row in extras:
        key = 'detail.' + row['key']
        if key in keys:
            raise ValueError('Duplicate fixed/additional attribute key.')
        keys.add(key)
    for judgment in [*raw['judgments'], *raw['alternative_judgments']]:
        refs = judgment['attribute_keys']
        if len(refs) != len(set(refs)) or not set(refs) <= keys:
            raise ValueError('Condition references a missing/duplicate attribute key.')
    result = {k: deepcopy(v) for k,v in raw.items() if k not in {'attributes','additional_details'}}
    observations = list(raw['attributes'].items()) + [('detail.'+r['key'], {k:v for k,v in r.items() if k!='key'}) for r in extras]
    rows = []
    for key, observation in observations:
        row = deepcopy(observation)
        row['attribute'] = 'detail' if key.startswith('detail.') else key
        row['fixed_attribute_key'] = key
        if key.startswith('detail.'):
            for source in ('metadata','image_observation'):
                obs = row.get(source)
                if obs and obs['value'] is not None:
                    value = obs['value']
                    obs['value'] = {'key':key[len('detail.'):], 'values':value if isinstance(value,list) else [value]}
        rows.append(row)
    result['attributes'] = rows
    return result


# ---- product_evaluation_v36 ----
"""v36 boundary validation and explicit projections, without semantic reinterpretation."""
from copy import deepcopy as deepcopy_v36
from typing import get_args
s = _role_module('fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v36')
from fashion_recommendation_v2.schemas.product_evidence import DiversityFeature
from fashion_recommendation_v2.schemas.product_evidence import ProductFactV26
from fashion_recommendation_v2.schemas.product_evidence import DIVERSITY_ATTRIBUTE_GROUPS
from fashion_recommendation_v2.schemas.product_evidence import ImageEvidence
from fashion_recommendation_v2.schemas.stylist import StylistDetailValue_base as StylistDetailValue
from fashion_recommendation_v2.search.product_sources import present_field
from fashion_recommendation_v2.search.planning_rules import requirement_alternatives


@_preserve_function('attribute_key', 'fashion_recommendation_v2.search.product_evaluation_v36')
def attribute_key(row):
    fixed = getattr(row, 'fixed_attribute_key', None)
    if fixed is not None:
        expected = 'detail.' if row.attribute == 'detail' else row.attribute
        if (row.attribute == 'detail' and not fixed.startswith(expected)) or (row.attribute != 'detail' and fixed != expected):
            raise ValueError('Fixed attribute identity mismatch.')
        if row.attribute == 'detail':
            for obs in (row.metadata, row.image_observation):
                if obs and obs.value is not None and (not isinstance(obs.value, StylistDetailValue) or 'detail.' + obs.value.key != fixed):
                    raise ValueError('Fixed detail key differs from observation.')
        return fixed
    if row.attribute != 'detail':
        return row.attribute
    values = [o.value for o in (row.metadata, row.image_observation) if o and o.value is not None]
    keys = {v.key for v in values if isinstance(v, StylistDetailValue)}
    if len(keys) != 1 or any(not isinstance(v, StylistDetailValue) for v in values):
        raise ValueError('detail requires one explicit key and preserved values on each source.')
    return 'detail.' + next(iter(keys))


@_preserve_function('validate_attribute', 'fashion_recommendation_v2.search.product_evaluation_v36')
def validate_attribute(row, item, conversion):
    key = attribute_key(row)
    if row.attribute != 'detail' and any(isinstance(o.value, StylistDetailValue)
            for o in (row.metadata, row.image_observation) if o):
        raise ValueError('Only detail accepts key/values.')
    meta = row.metadata
    if any(not present_field(item, p, conversion) for p in meta.evidence_fields):
        raise ValueError(f'{key}: absent metadata source path.')
    if meta.value is not None and not (meta.evidence_fields and any(t.strip() for t in meta.evidence)):
        raise ValueError(f'{key}: metadata value requires an existing source and explanation.')
    image = row.image_observation
    if image and image.value is not None and not (item.image_url and any(t.strip() for t in image.evidence)):
        raise ValueError(f'{key}: image value requires image evidence.')
    if row.attribute in s.METADATA_ONLY and image is not None:
        raise ValueError(f'{key}: image observation is not part of this field contract.')
    if row.attribute in s.METADATA_ONLY and row.metadata_image_consistency.status not in {'not_applicable', 'observation_unavailable'}:
        raise ValueError('Metadata-only attributes have no visual comparison.')
    return key


@_preserve_function('row_evidence', 'fashion_recommendation_v2.search.product_evaluation_v36')
def row_evidence(row, image_url):
    meta, image = row.metadata, row.image_observation
    valid = row.code_validation.validated_sources
    return dict(evidence_fields=list(meta.evidence_fields) if 'metadata' in valid else [],
        evidence=list(meta.evidence) if 'metadata' in valid else [],
        image_evidence=[ImageEvidence(image_url=image_url, observation=t)
            for t in (image.evidence if image and 'image_observation' in valid else []) if t.strip()])


@_preserve_function('available_sources', 'fashion_recommendation_v2.search.product_evaluation_v36')
def available_sources(row):
    return ['metadata'] + (['image_observation'] if row.image_observation is not None else [])


@_preserve_function('merge_identical_attribute', 'fashion_recommendation_v2.search.product_evaluation_v36')
def merge_identical_attribute(first, second):
    """Retain v32's exact-value duplicate recovery without guessing identity."""
    if (first.code_validation.status != 'passed' or second.code_validation.status != 'passed'
            or first.metadata_image_consistency.status != second.metadata_image_consistency.status):
        raise ValueError('Duplicate attribute records disagree or have invalid evidence.')
    for name in ('metadata', 'image_observation'):
        a, b = getattr(first, name), getattr(second, name)
        if (a is None) != (b is None) or a and (type(a.value) is not type(b.value) or a.value != b.value):
            raise ValueError('Duplicate attribute values/types differ; no semantic merge.')
    merged = first.model_copy(deep=True)
    for name in ('metadata', 'image_observation'):
        a, b = getattr(merged, name), getattr(second, name)
        if a is None:
            continue
        a.evidence = list(dict.fromkeys([*a.evidence, *b.evidence]))
        if name == 'metadata':
            a.evidence_fields = list(dict.fromkeys([*a.evidence_fields, *b.evidence_fields]))
    merged.metadata_image_consistency.reason = '\n'.join(dict.fromkeys([
        first.metadata_image_consistency.reason, second.metadata_image_consistency.reason]))
    return merged


@_preserve_function('unavailable_row', 'fashion_recommendation_v2.search.product_evaluation_v36')
def unavailable_row(value, item, conversion, error):
    """Keep independently validated sources in the derived record, never repair raw."""
    if not isinstance(value, dict) or value.get('attribute') not in get_args(s.AttributeName):
        raise ValueError('Unidentifiable attribute record.')
    name = value['attribute']
    v42 = _role_module('fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v42')
    fixed = {'fixed_attribute_key': value['fixed_attribute_key']} if 'fixed_attribute_key' in value else {}
    draft_cls = v42.DerivedDraft if fixed else s.AttributeDraft
    row_cls = v42.DerivedObservation if fixed else s.AttributeObservation
    meta = s.MetadataObservation(value=None, evidence_fields=[], evidence=[])
    image, valid = None, []
    for source, cls in (('metadata', s.MetadataObservation), ('image_observation', s.ImageObservation)):
        try:
            obs = cls.model_validate(value.get(source))
            if name in s.METADATA_ONLY and source == 'image_observation':
                continue
            probe = draft_cls(**fixed, attribute=name, metadata=obs if source == 'metadata' else meta,
                image_observation=obs if source == 'image_observation' else None,
                metadata_image_consistency=s.ObservedConsistency(status='not_applicable', reason=error))
            validate_attribute(probe, item, conversion)
        except (ValueError, TypeError):
            continue
        if source == 'metadata':
            meta = obs
        else:
            image = obs
        valid.append(source)
    row = row_cls(**fixed, attribute=name, metadata=meta, image_observation=image,
        metadata_image_consistency=s.Consistency(status='observation_unavailable', reason=error),
        code_validation=s.AttributeValidation(status='failed', errors=[error], validated_sources=valid))
    attribute_key(row)  # A broken detail key cannot be guessed.
    return row


@_preserve_function('bind_judgment', 'fashion_recommendation_v2.search.product_evaluation_v36')
def bind_judgment(draft, rows, image_url, *, alternative=False):
    if len(draft.attribute_keys) != len(set(draft.attribute_keys)) or not set(draft.attribute_keys) <= set(rows):
        raise ValueError('Condition references a missing/duplicate attribute key.')
    fields, evidence, images = [], [draft.reason], []
    for key in draft.attribute_keys:
        proof = row_evidence(rows[key], image_url)
        fields.extend(proof['evidence_fields']); evidence.extend(proof['evidence']); images.extend(proof['image_evidence'])
    if draft.status != 'unknown' and not (fields or images):
        raise ValueError('A confirmed condition requires validated product evidence.')
    if draft.uncertainty_reason != 'none' and draft.status != 'unknown':
        raise ValueError('Unresolved condition uncertainty must remain unknown.')
    v40 = _role_module('fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v40')
    cls = (v40.Alternative if isinstance(draft, v40.AlternativeDraft) else s.Alternative) if alternative else s.Judgment
    return cls(**draft.model_dump(exclude={'reason'}), evidence_fields=list(dict.fromkeys(fields)),
        evidence=list(dict.fromkeys(evidence)), image_evidence=list({e.model_dump_json(): e for e in images}.values()))


@_preserve_function('child_category', 'fashion_recommendation_v2.search.product_evaluation_v36')
def child_category(item, rows, requirements):
    from fashion_recommendation_v2.tools.age_scope import children_requested
    from fashion_recommendation_v2.tools.age_scope import _CHILD_TERMS
    from fashion_recommendation_v2.tools.age_scope import _CHILD_VALUES
    if children_requested(requirements):
        return False
    values = [item.category_path or '']
    for row in rows:
        if row.attribute != 'category' or row.code_validation.status != 'passed':
            continue
        for obs in (row.metadata, row.image_observation):
            if obs and obs.value:
                values.extend(obs.value if isinstance(obs.value, list) else [str(obs.value)])
    return any(_CHILD_TERMS.search(v) or v.casefold().strip() in _CHILD_VALUES for v in values)


@_preserve_function('admission_checks', 'fashion_recommendation_v2.search.product_evaluation_v36')
def admission_checks(analysis, item, requirements):
    hard = {r.requirement_id for r in requirements.requirements if r.kind == 'hard'}
    by_id = {j.requirement_id: j.status for j in analysis.judgments}
    from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import HARD_PASS_STATUSES_v40 as HARD_PASS_STATUSES
    accepted = HARD_PASS_STATUSES if getattr(analysis, 'evaluation_policy', 'v36') in {'v40', 'v41', 'v42', 'v43', 'v44', 'v45'} else {'met'}
    checks = dict(evaluation_valid=analysis.code_validation.status == 'passed',
        image_available=bool(item.image_url), hard_conditions_pass=all(by_id.get(k) in accepted for k in hard),
        photo_pass=analysis.thumbnail_observation_v8.passes(),
        exposure_pass=analysis.exposure_suitability.status == 'allowed',
        childrenswear_pass=not child_category(item, analysis.attributes, requirements))
    return s.AdmissionChecks(**checks, overall_pass=all(checks.values()))


@_preserve_function('validate_analysis', 'fashion_recommendation_v2.search.product_evaluation_v36')
def validate_analysis(analysis, item, requirements, conversion):
    from fashion_recommendation_v2.search.condition_semantics import validate_condition_contract
    validate_condition_contract(requirements)
    routing = requirements.condition_routing_v37
    if routing is not None and routing.relative_requirement_ids:
        facts = routing.anchor_comparison.get('attributes', {})
        for rid in routing.relative_requirement_ids:
            requirement = next(r for r in requirements.requirements if r.requirement_id == rid)
            key = (requirement.value.key if hasattr(requirement.value, 'key') else
                   requirement.value.get('key') if isinstance(requirement.value, dict) else requirement.attribute)
            values = facts.get(key) or facts.get('detail.' + key)
            usable = values and any(str(v).strip().casefold() not in {'', 'unknown', 'none', 'null'} for v in (values if isinstance(values, list) else [values]))
            if not usable and any(j.requirement_id == rid and j.status != 'unknown' for j in analysis.judgments):
                raise ValueError(f'{rid}: relative comparison lacks matching anchor evidence; must remain unknown.')
    if analysis.item_id != item.item_id or analysis.image_url != item.image_url:
        raise ValueError('v36 item/image identity mismatch.')
    rows = {}
    for row in analysis.attributes:
        key = attribute_key(row)
        if key in rows:
            raise ValueError('Duplicate attribute key.')
        rows[key] = row
        if row.code_validation.status == 'passed':
            validate_attribute(row, item, conversion)
            if row.code_validation.validated_sources != available_sources(row):
                raise ValueError('Validated attribute source inventory mismatch.')
        elif row.metadata_image_consistency.status != 'observation_unavailable':
            raise ValueError('Failed observation must have a code-owned unavailable record.')
        else:
            validate_attribute(row, item, conversion)
    v40 = _role_module('fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v40')
    if analysis.evaluation_policy in {'v42', 'v43', 'v44', 'v45'}:
        from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import fixed_keys_v42 as fixed_keys
        if not set(fixed_keys(requirements)) <= set(rows):
            raise ValueError('Missing fixed attribute observations.')
    graded = analysis.evaluation_policy in {'v40', 'v41', 'v42', 'v43', 'v44', 'v45'}
    expected = {r.requirement_id for r in requirements.requirements}
    actual = [j.requirement_id for j in analysis.judgments]
    if set(actual) != expected or len(actual) != len(expected):
        raise ValueError('Missing/duplicate/unknown condition judgments.')
    alternatives = [(a.requirement_id, a.value) for a in analysis.alternative_judgments]
    if set(alternatives) != set(requirement_alternatives(requirements)) or len(alternatives) != len(set(alternatives)):
        raise ValueError('Every original OR alternative needs exactly one judgment.')
    for j in [*analysis.judgments, *analysis.alternative_judgments]:
        if analysis.evaluation_policy in {'v43', 'v44', 'v45'} and not set(j.attribute_keys) <= set(fixed_keys(requirements)):
            raise ValueError('Condition reference outside fixed attribute inventory.')
        if not set(j.attribute_keys) <= set(rows):
            raise ValueError('Unknown attribute reference.')
        if any(not present_field(item, p, conversion) for p in j.evidence_fields):
            raise ValueError('Condition cites absent metadata.')
        if any(e.image_url != item.image_url for e in j.image_evidence):
            raise ValueError('Condition cites another image.')
        if j.status != 'unknown' and not ((j.evidence_fields and j.evidence) or j.image_evidence):
            raise ValueError('Non-unknown condition needs evidence.')
        requirement = next(r for r in requirements.requirements if r.requirement_id == j.requirement_id)
        if requirement.attribute != 'price':
            draft_cls = (v40.AlternativeDraft if graded else s.AlternativeDraft) if isinstance(j, s.Alternative) else s.JudgmentDraft
            data = j.model_dump(exclude={'evidence', 'evidence_fields', 'image_evidence'})
            rebound = bind_judgment(draft_cls(**data, reason=j.evidence[0]), rows, item.image_url,
                alternative=isinstance(j, s.Alternative))
            if rebound != j:
                raise ValueError('Condition evidence must match its declared attribute sources.')
    by_id = {j.requirement_id: j for j in analysis.judgments}
    for rid in {a.requirement_id for a in analysis.alternative_judgments}:
        states = [a.status for a in analysis.alternative_judgments if a.requirement_id == rid]
        expected_status = 'met' if 'met' in states else 'unmet' if all(v == 'unmet' for v in states) else 'unknown'
        if graded:
            from fashion_recommendation_v2.search.product_semantics import aggregate_alternatives_v40 as aggregate_alternatives
            expected_status = aggregate_alternatives(states)
        if by_id[rid].status != expected_status:
            raise ValueError('OR aggregate disagrees with its option judgments.')
    hard = {r.requirement_id for r in requirements.requirements if r.kind == 'hard' and r.attribute != 'price'}
    findings = {f.requirement_id: f for f in analysis.hard_condition_findings}
    if set(findings) != hard or len(findings) != len(analysis.hard_condition_findings):
        raise ValueError('Hard findings must cover exactly the non-price hard conditions.')
    for rid, f in findings.items():
        allowed = {'matched': {'met'}, 'clear_mismatch': {'unmet'}, 'insufficient_evidence': {'unknown'}}
        if graded:
            allowed = v40.HARD_FINDING_STATUSES
        if by_id[rid].status not in allowed[f.finding]:
            raise ValueError('Hard finding contradicts its condition judgment.')
    checks = admission_checks(analysis, item, requirements)
    if checks != analysis.admission_checks:
        raise ValueError('Stored admission checks do not match code policy.')
    if analysis.semantic_review is not None:
        validate_provenance(analysis, item, requirements, conversion)


@_preserve_function('project', 'fashion_recommendation_v2.search.product_evaluation_v36')
def project(raw, item, requirements, conversion, price_checks, *, evaluation_policy="v36"):
    """Preserve raw externally; isolate only attribute-local structural/source errors."""
    v42 = _role_module('fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v42')
    if evaluation_policy in {'v43', 'v44', 'v45'}:
        from fashion_recommendation_v2.search.product_evaluation import consumer_projection
        raw = consumer_projection(raw, requirements)
    elif evaluation_policy == 'v42':
        from fashion_recommendation_v2.search.product_evaluation import consumer_projection_v42 as consumer_projection
        raw = consumer_projection(raw, requirements)  # Separate derived records; native response stays untouched.
    if evaluation_policy not in {'v36', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45'}:
        raise ValueError('Unsupported product evaluation policy.')
    v40 = _role_module('fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v40')
    v41 = _role_module('fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v41')
    schema = v41 if evaluation_policy == 'v41' else v40 if evaluation_policy in {'v40', 'v42', 'v43', 'v44', 'v45'} else s
    if not isinstance(raw, dict) or set(raw) != set(schema.ProductDraft.model_fields):
        raise ValueError('Missing or unknown product response fields.')
    if not isinstance(raw['attributes'], list):
        raise ValueError('attributes must be a list.')
    rows, diagnostics = {}, []
    for value in raw['attributes']:
        projected = deepcopy_v36(value)
        if isinstance(projected, dict) and projected.get('attribute') == 'gender' and isinstance(projected.get('metadata'), dict):
            from fashion_recommendation_v2.search.audience_policy import canonical_gender
            before = projected['metadata'].get('value')
            after = canonical_gender(before)
            if before != after:
                projected['metadata']['value'] = after
                diagnostics.append(dict(attribute='gender', rule='exact_gender_alias', original=deepcopy_v36(value),
                    before=before, after=after))
        try:
            row = (v42.DerivedDraft if evaluation_policy in {'v42', 'v43', 'v44', 'v45'} else s.AttributeDraft).model_validate(projected)
            key = validate_attribute(row, item, conversion)
            result = (v42.DerivedObservation if evaluation_policy in {'v42', 'v43', 'v44', 'v45'} else s.AttributeObservation)(**row.model_dump(), code_validation=s.AttributeValidation(
                status='passed', validated_sources=available_sources(row)))
        except (ValueError, TypeError) as exc:
            # A known structural location is required; never guess a broken key.
            result = unavailable_row(projected, item, conversion, str(exc))
            key = attribute_key(result)
            diagnostics.append(dict(attribute=key, error=str(exc), original=deepcopy_v36(value)))
        if key in rows:
            result = merge_identical_attribute(rows[key], result)
            diagnostics.append(dict(attribute=key, rule='identical_fact_merged_preserving_all_evidence',
                original=deepcopy_v36(value)))
        rows[key] = result
    # Missing observations are code diagnostics, never fabricated model facts.
    for key in get_args(s.AttributeName):
        if key == 'detail' or key in rows:
            continue
        rows[key] = s.AttributeObservation(attribute=key,
            metadata=s.MetadataObservation(value=None, evidence_fields=[], evidence=[]), image_observation=None,
            metadata_image_consistency=s.Consistency(status='observation_unavailable', reason='Attribute response missing.'),
            code_validation=s.AttributeValidation(status='failed', errors=['missing_response']))
    judgments = [bind_judgment(s.JudgmentDraft.model_validate(j), rows, item.image_url) for j in raw['judgments']]
    alternatives = [bind_judgment(schema.AlternativeDraft.model_validate(j), rows, item.image_url, alternative=True)
                    for j in raw['alternative_judgments']]
    price_ids = {c.requirement_id for c in price_checks}
    if price_ids & {j.requirement_id for j in judgments}:
        raise ValueError('Price judgments are code-owned.')
    judgments += [s.Judgment(**c.model_dump(), attribute_keys=[], uncertainty_reason=(
        'insufficient_evidence' if c.status == 'unknown' else 'none')) for c in price_checks]
    data = {k: deepcopy_v36(raw[k]) for k in ('hard_condition_findings', 'thumbnail_observation_v8',
        'exposure_suitability', 'admission_judgment')}
    # Compute gates separately from, and without rewriting, the LLM's gate claims.
    from types import SimpleNamespace
    temporary = SimpleNamespace(evaluation_policy=evaluation_policy, attributes=list(rows.values()), judgments=judgments,
        thumbnail_observation_v8=s.ThumbnailObservationV1.model_validate(data['thumbnail_observation_v8']),
        exposure_suitability=s.ExposureSuitability.model_validate(data['exposure_suitability']),
        code_validation=s.CodeValidation(status='passed'))
    v43 = _role_module('fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v43')
    v44 = _role_module('fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v44')
    v45 = _role_module('fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v45')
    analysis_cls = v45.SearchItemAnalysisV45 if evaluation_policy == 'v45' else v44.SearchItemAnalysisV44 if evaluation_policy == 'v44' else v43.SearchItemAnalysisV43 if evaluation_policy == 'v43' else v42.SearchItemAnalysisV42 if evaluation_policy == 'v42' else v41.SearchItemAnalysisV41 if evaluation_policy == 'v41' else v40.SearchItemAnalysisV40 if evaluation_policy == 'v40' else s.SearchItemAnalysisV36
    analysis = analysis_cls(item_id=item.item_id, image_url=item.image_url,
        attributes=list(rows.values()), judgments=judgments, alternative_judgments=alternatives,
        code_validation=temporary.code_validation, admission_checks=admission_checks(temporary, item, requirements), **data)
    validate_analysis(analysis, item, requirements, conversion)
    return analysis, diagnostics


@_preserve_function('semantic_entries', 'fashion_recommendation_v2.search.product_evaluation_v36')
def semantic_entries(analysis):
    """Derived consumer facts, without changing the source-separated observations."""
    result = []
    for index, row in enumerate(analysis.attributes):
        if row.code_validation.status != 'passed' or row.metadata_image_consistency.status in {'inconsistent', 'partially_consistent'}:
            continue
        image = row.image_observation
        # Use visible evidence for visual facts; metadata-only facts keep their source.
        obs = image if image and image.value is not None else row.metadata
        values = (obs.value.values if isinstance(obs.value, StylistDetailValue)
            else obs.value if isinstance(obs.value, list) else [obs.value])
        if not values or any(v is None or not v.strip() or v.strip().casefold() in {'unknown', 'n/a', 'unspecified'} for v in values):
            continue
        proof = row_evidence(row, analysis.image_url)
        fact = ProductFactV26(attribute=row.attribute, value=obs.value, **proof)
        source = 'image_observation' if obs is image else 'metadata'
        result.append((f'search_analysis.attributes.{index}.{source}', fact))
    return result


@_preserve_function('diversity_features', 'fashion_recommendation_v2.search.product_evaluation_v36')
def diversity_features(analysis, requirements):
    from fashion_recommendation_v2.search.condition_semantics import observation_key as key
    features = []
    for _, fact in semantic_entries(analysis):
        if fact.attribute not in DIVERSITY_ATTRIBUTE_GROUPS or fact.attribute == 'detail':
            continue
        # Preserve exact hard-value exclusion from the previous diversity policy.
        fixed = [r.requirement_id for r in requirements.requirements
            if r.kind == 'hard' and not r.unrestricted and isinstance(r.value, str)
            and r.value == fact.value and key(r.model_dump()) == key(fact.model_dump())]
        if fact.attribute in {'gender', 'material'} and not fact.evidence_fields:
            continue
        features.append(DiversityFeature(attribute=fact.attribute, value=fact.value,
            group=DIVERSITY_ATTRIBUTE_GROUPS[fact.attribute], fixed_by_requirement_ids=fixed,
            **fact.model_dump(exclude={'attribute', 'value'})))
    return features


@_preserve_function('validate_provenance', 'fashion_recommendation_v2.search.product_evaluation_v36')
def validate_provenance(analysis, item, requirements, conversion):
    from fashion_recommendation_v2.search.observation_review import observation_hash
    from fashion_recommendation_v2.schemas.visual_confirmation import VisualConsistencyDecisionV5
    from fashion_recommendation_v2.tools.price_translate import filter_requirement
    review = analysis.semantic_review
    target = review['target']
    if review['target_sha256'] != observation_hash(item, requirements, target):
        raise ValueError('Original v36 response/item/requirements hash mismatch.')
    checks = [filter_requirement(item, r, conversion) for r in requirements.requirements if r.attribute == 'price']
    expected, _ = project(target['model_response'][target['target_slot']], item, requirements, conversion, checks,
        evaluation_policy=analysis.evaluation_policy)
    if expected.model_dump(exclude={'semantic_review'}) != analysis.model_dump(exclude={'semantic_review'}):
        raise ValueError('Stored v36 projection differs from the preserved original response.')
    questions = review_questions(analysis)
    if review['questions'] != questions or review['source'] != ('llm' if questions else 'code'):
        raise ValueError('Conditional Q review route mismatch.')
    attempts = review['attempts']
    if not questions:
        if attempts or review['status'] != 'passed':
            raise ValueError('Code-only review cannot claim a model response.')
    else:
        if not attempts or len(attempts) > 2:
            raise ValueError('Q review requires a bounded attempt record.')
        for previous in attempts[:-1]:
            if not previous.get('error', '').startswith('TimeoutError:'):
                raise ValueError('Only a review timeout can be retried.')
        final = attempts[-1]
        if final.get('code_validation') == 'passed':
            decision = VisualConsistencyDecisionV5.model_validate(final['model_response'])
            status = 'passed' if decision.status == 'consistent' else 'failed'
        else:
            status = 'unavailable'
        if status != review['status']:
            raise ValueError('Stored Q review status differs from its original decision.')


@_preserve_function('review_questions', 'fashion_recommendation_v2.search.product_evaluation_v36')
def review_questions(analysis):
    # Reuse Q suspicion routing only; no old V is generated or stored.
    from types import SimpleNamespace
    from fashion_recommendation_v2.search.observation_review import visual_review_questions
    neutral = SimpleNamespace(overall_form_evidence='', overall_form_status='unknown', requirement_checks=[])
    return visual_review_questions(SimpleNamespace(ranking_thumbnail_observation_v5=analysis.thumbnail_observation_v8,
        visual_confirmation_v5=neutral), SimpleNamespace(requirements=[]))


# ---- product_evaluation_v33 ----
"""Lossless original response and a separate observation-to-consumer projection."""
from copy import deepcopy as deepcopy_v33
from typing import get_args as get_args_v33
from typing import Union
from pydantic import create_model
from fashion_recommendation_v2.schemas.base import StrictBaseModel
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import ATTRIBUTE_GROUPS_v32 as ATTRIBUTE_GROUPS
canonicalize_facts = canonicalize_facts_v32
from fashion_recommendation_v2.search.product_validation import project_slot as project_v29


@_preserve_function('empty_evidence', 'fashion_recommendation_v2.search.product_evaluation_v33')
def empty_evidence():
    return dict(evidence_fields=[], evidence=[], image_evidence=[])


@_preserve_function('merge_evidence', 'fashion_recommendation_v2.search.product_evaluation_v33')
def merge_evidence(target, evidence):
    for field, entries in evidence.items():
        for entry in entries:
            if entry not in target[field]:
                target[field].append(deepcopy_v33(entry))


@_preserve_function('expand_slot', 'fashion_recommendation_v2.search.product_evaluation_v33')
def expand_slot(raw, schema):
    if not isinstance(raw, dict):
        raise ValueError('Expected product object.')
    allowed = set(schema.model_fields)
    if not allowed - {'visual_confirmation_v5'} <= set(raw) <= allowed:
        raise ValueError('Missing/unknown observation product fields.')
    # Auxiliary Ranking observation failure still preserves valid Search evidence.
    fields = {
        k: (f.annotation, deepcopy_v33(f)) for k, f in schema.model_fields.items()
        if k != 'visual_confirmation_v5'}
    # Retain v32's exact known-dimension relocation recovery. Generation still
    # requests each fact in its canonical location; unrelated shape errors fail.
    from fashion_recommendation_v2.schemas.product_evidence import ProductFactV26
    from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import FactV33
    fact = create_model('RecoverableFactV33', __base__=FactV33,
        attribute=(ProductFactV26.model_fields['attribute'].annotation, ...))
    variants = [model if get_args_v33(model.model_fields['source'].annotation) == ('unavailable',)
        else create_model('Admission' + model.__name__, __base__=model, product_facts_v26=(list[fact], ...))
        for model in get_args_v33(get_args_v33(schema.model_fields['observations'].annotation)[0])]
    fields['observations'] = (list[Union[tuple(variants)]], ...)
    checked = create_model('AdmissionWireV33', __base__=StrictBaseModel, **fields)
    checked.model_validate({k: v for k, v in raw.items() if k != 'visual_confirmation_v5'})
    data, changes = deepcopy_v33(raw), []
    data.setdefault('visual_confirmation_v5', None)
    observations = data.pop('observations')
    data['attributes'], data['product_facts_v26'] = [], []
    for row in data['judgments'].values():
        row.update(empty_evidence())
    for options in data['alternative_judgments'].values():
        for row in options.values():
            row.update(empty_evidence())
    for index, observation in enumerate(observations):
        text = observation['observation']
        if not text.strip():
            raise ValueError(f'observations.{index}: observation must not be blank.')
        evidence = empty_evidence()
        if observation['source'] == 'metadata':
            evidence.update(evidence_fields=deepcopy_v33(observation['evidence_fields']), evidence=[text])
        elif observation['source'] == 'image':
            evidence['image_evidence'] = [dict(observation=text)]
        else:
            # An uncertainty explanation is not metadata or image proof. Keep
            # explicit unknown values; existing judgment gates remain in force.
            evidence['evidence'] = [text]
        for field in ('attributes', 'product_facts_v26'):
            for fact in observation[field]:
                row = {**deepcopy_v33(fact), **deepcopy_v33(evidence)}
                if field == 'attributes':
                    row.update(group=ATTRIBUTE_GROUPS[row['attribute']], fixed_by_requirement_ids=[])
                data[field].append(row)
        for rid in observation['requirement_ids']:
            merge_evidence(data['judgments'][rid], evidence)
        for target in observation['alternative_targets']:
            merge_evidence(data['alternative_judgments'][target['requirement_id']][target['alternative_id']], evidence)
        changes.append(dict(path=f'observations.{index}', reason='observation_bound_to_local_facts_and_input_ids',
            source=observation['source'], requirement_ids=deepcopy_v33(observation['requirement_ids']),
            alternative_targets=deepcopy_v33(observation['alternative_targets'])))
    canonicalize_facts(data, changes)
    photo = data['thumbnail_observation_v8']
    data['thumbnail_kind'], data['thumbnail_evidence'] = photo['photo_type'], photo['evidence']
    return data, changes


@_preserve_function('project_slot', 'fashion_recommendation_v2.search.product_evaluation_v33')
def project_slot(raw, item, context, core_schema, wire_schema):
    expanded, changes = expand_slot(raw, wire_schema)
    data, diagnostic, ranking_error = project_v29(expanded, item, context, core_schema)
    diagnostic.update(wire_version='v33', status='projected')
    diagnostic['changes'] = changes + diagnostic['changes']
    return data, diagnostic, ranking_error


# ---- product_evaluation_v43 ----
"""Validate the native v43 contract before deriving the unchanged consumer view."""
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import product_schema_v43 as product_schema
previous_projection = consumer_projection_v42


@_preserve_function('consumer_projection', 'fashion_recommendation_v2.search.product_evaluation_v43')
def consumer_projection(raw, requirements):
    product_schema(requirements).model_validate(raw)
    return previous_projection(raw, requirements)
