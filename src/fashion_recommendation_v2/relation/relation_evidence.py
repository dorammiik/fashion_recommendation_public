"""Role-consolidated implementation; service contracts and behavior are preserved."""
from __future__ import annotations
from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function

# ---- relation_evidence ----
"""Relation v2 source definitions and pure, lossless saved-evidence projection.

Never fetch images, run Search, manufacture observations or mutate source objects.
Refs name original saved paths; only the separate derived packet is filtered.
"""
import hashlib
import json
from typing import get_args

from fashion_recommendation_v2.schemas.relation import EVIDENCE_FIELDS
from fashion_recommendation_v2.schemas.relation import Dimension
from fashion_recommendation_v2.search.condition_semantics import ALIASES
from fashion_recommendation_v2.search.condition_semantics import METADATA_ONLY_FACTS
from fashion_recommendation_v2.search.product_sources import present_field

DIMENSIONS = get_args(Dimension)
DIMENSION_KEYS = {
    'color': ('color', 'detail.color'),
    'pattern': ('pattern', 'detail.pattern', 'detail.pattern_scale', 'detail.pattern_distribution'),
    'silhouette': ('fit', 'detail.fit', 'detail.silhouette', 'detail.volume', 'detail.proportion'),
    'length': ('detail.length', 'detail.dress_length', 'detail.skirt_length'),
    'details': ('category', 'product_type', 'avoid_product_type', 'sleeve_length'),
    'style': ('theme', 'occasion', 'detail.theme', 'detail.occasion', 'detail.style'),
}
EXCLUDED_METADATA = {'price', 'size', 'brand', 'category_id_path', 'garment_care'}
EXCLUDED_FACTS = {'brand', 'size', 'garment_care', 'strength'}


@_preserve_function('canonical_hash', 'fashion_recommendation_v2.relation.relation_evidence')
def canonical_hash(value):
    if hasattr(value, 'model_dump'):
        value = value.model_dump(mode='json')
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':')).encode()).hexdigest()


@_preserve_function('key', 'fashion_recommendation_v2.relation.relation_evidence')
def key(attribute, value=None):
    name = 'detail.' + (value.key if hasattr(value, 'key') else value['key']) if attribute == 'detail' else attribute
    name = name.casefold().replace('-', '_').replace(' ', '_')
    return ALIASES.get(name, name)


@_preserve_function('dimensions', 'fashion_recommendation_v2.relation.relation_evidence')
def dimensions(name):
    for dimension, names in DIMENSION_KEYS.items():
        if name in names:
            return [dimension]
    # Other saved visual construction details remain available. Metadata-only
    # detail properties (size/composition etc.) never become visual structure.
    if name.startswith('detail.') and name not in METADATA_ONLY_FACTS:
        return ['details']
    return []


@_preserve_function('packet', 'fashion_recommendation_v2.relation.relation_evidence')
def packet_base(item, analysis, role, requirements=None, evidence_item=None):
    if analysis is not None and (analysis.item_id != item.item_id or analysis.image_url != item.image_url):
        raise ValueError('Relation v2 Search observation item/image identity mismatch.')
    evidence_item = evidence_item or item
    if (evidence_item.item_id, evidence_item.image_url) != (item.item_id, item.image_url):
        raise ValueError('Relation v2 evaluation snapshot item/image identity mismatch.')
    facts, limitations = [], []
    observations = {d: dict(dimension=d, status='observation_unavailable', evidence_refs=[],
        metadata_refs=[], unknown_refs=[], reasons=[]) for d in DIMENSIONS}
    conflicted = set()
    if analysis and analysis.evaluation_policy in {'v36', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45'}:
        from fashion_recommendation_v2.search.product_evaluation import attribute_key
        conflicted = {key(attribute_key(a)) for a in analysis.attributes if a.metadata_image_consistency.status in {'inconsistent', 'partially_consistent'}}
    elif analysis:
        conflicted = {ALIASES.get(c.attribute, c.attribute) for c in analysis.conflicts}

    def disputed(name):
        return name in conflicted or name.startswith('detail.') and 'detail' in conflicted

    def add(path, value, name, *, kind, status='known', image=False, reason=None):
        ref = role + ':' + path
        facts.append(dict(ref=ref, value=value, status=status, kind=kind))
        for dimension in dimensions(name):
            row = observations[dimension]
            if status == 'known':
                row['evidence_refs' if image else 'metadata_refs'].append(ref)
            elif status == 'unknown' and image:
                row['unknown_refs'].append(ref)
            if status == 'conflicted':
                row['reasons'].append('conflicting_evidence')
            if reason:
                row['reasons'].append(reason)

    # Keep metadata separate from observed image facts. Raw metadata is used to
    # validate citations only; it is never a back door into the model packet.
    for name in EVIDENCE_FIELDS:
        if name in EXCLUDED_METADATA:
            continue
        value = getattr(item, name, None)
        if value in (None, '', [], {}):
            continue
        if name == 'detail' and isinstance(value, dict):
            for detail_key, values in value.items():
                name_key = key('detail', {'key': detail_key})
                add('item.detail.' + detail_key, values, name_key, kind='metadata',
                    status='conflicted' if disputed(name_key) else 'known')
        else:
            add('item.' + name, value, name, kind='metadata',
                status='conflicted' if disputed(name) else 'known')

    if analysis is None:
        limitations.append(dict(kind='observation_unavailable', reason='missing_analysis'))
    elif analysis.evaluation_policy in {'v36', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45'}:
        from fashion_recommendation_v2.search.product_evaluation import validate_attribute
        from fashion_recommendation_v2.search.product_evaluation import attribute_key
        for index, row in enumerate(analysis.attributes):
            name = key(attribute_key(row))
            if row.attribute in EXCLUDED_FACTS:
                continue
            invalid = False
            try:
                validate_attribute(row, evidence_item, None)
            except ValueError:
                invalid = True
            for source_name in ('metadata', 'image_observation'):
                obs = getattr(row, source_name)
                path = f'search_analysis.attributes.{index}.{source_name}'
                is_image = source_name == 'image_observation'
                source_invalid = invalid or source_name not in row.code_validation.validated_sources
                state = ('unavailable' if source_invalid or obs is None else 'conflicted' if disputed(name)
                    else 'unknown' if obs.value is None else 'known')
                if obs is None:
                    limitations.append(dict(kind='observation_unavailable', source_path=path, reason='missing_observation'))
                    continue
                add(path, obs.model_dump(mode='json'), name, kind='search_observation', status=state,
                    image=is_image, reason='validation_failed' if source_invalid else None)
            if disputed(name):
                limitations.append(dict(kind='conflict', attribute=name,
                    metadata=row.metadata.model_dump(mode='json'),
                    image_observation=row.image_observation.model_dump(mode='json') if row.image_observation else None,
                    explanation=row.metadata_image_consistency.reason))
    else:
        # Visibility can explain an observed unknown, but satisfaction unknown
        # cannot: a saved factual description may be clear while request
        # compliance remains uncertain. Reuse the existing audit without calls.
        visibility = None
        if analysis.visual_confirmation_v5 and requirements is not None:
            try:
                from fashion_recommendation_v2.schemas.search.ranking_observation.search_ranking_observation import SearchImageObservationsOutputV5
                from fashion_recommendation_v2.schemas.search.ranking_observation.search_ranking_observation import validate_reviewed_observation
                if analysis.ranking_visual_error_v5:
                    raise ValueError(analysis.ranking_visual_error_v5)
                bundle = SearchImageObservationsOutputV5(
                    ranking_thumbnail_observation_v5=analysis.ranking_thumbnail_observation_v5,
                    visual_confirmation_v5=analysis.visual_confirmation_v5,
                    exposure_suitability=analysis.exposure_suitability)
                if analysis.visual_consistency_v5 is None:
                    raise ValueError('Missing saved observation audit.')
                validate_reviewed_observation(evidence_item, requirements, bundle, analysis.visual_consistency_v5)
                visibility = bundle.visual_confirmation_v5
            except (ValueError, TypeError, KeyError, AttributeError) as exc:
                limitations.append(dict(kind='observation_unavailable', reason='validation_failed',
                    source_path='search_analysis.visual_confirmation_v5', diagnostic=str(exc)))
        visibility_unknown = {c.requirement_id for c in visibility.requirement_checks
            if c.applicable and c.status == 'unknown'} if visibility else set()
        # Search can fill an omitted attribute with unknown. Therefore unknown
        # without an actual saved image observation is NOT observed uncertainty.
        for collection in ('attributes', 'product_facts_v26'):
            for index, feature in enumerate(getattr(analysis, collection) or []):
                name = key(feature.attribute, feature.value)
                if feature.attribute in EXCLUDED_FACTS:
                    continue
                path = f'search_analysis.{collection}.{index}'
                for image in feature.image_evidence:
                    if image.image_url != item.image_url:
                        raise ValueError('Relation v2 fact cites another image: ' + path)
                invalid = (any(not present_field(evidence_item, p, None) for p in feature.evidence_fields)
                    or any(not e.observation.strip() for e in feature.image_evidence)
                    or (name in METADATA_ONLY_FACTS and not feature.evidence_fields))
                has_image = bool(feature.image_evidence)
                has_metadata = bool(feature.evidence_fields and any(t.strip() for t in feature.evidence))
                status = ('conflicted' if disputed(name) else 'unavailable' if invalid or not (has_image or has_metadata)
                    else 'unknown' if feature.value == 'unknown' else 'known')
                # group/fixed condition IDs are code scores/context, not facts.
                value = feature.model_dump(mode='json', exclude={'group', 'fixed_by_requirement_ids'})
                add(path, value, name, kind='search_observation', status=status, image=has_image,
                    reason='validation_failed' if invalid else 'missing_observation' if status == 'unavailable' else None)
                if invalid:
                    limitations.append(dict(kind='observation_unavailable', reason='validation_failed', ref=role + ':' + path))

        definitions = getattr(requirements, 'condition_contract_v26', None) or {}
        by_id = {r.requirement_id: r for r in getattr(requirements, 'requirements', [])}
        for collection in ('judgments', 'alternative_judgments'):
            for index, judgment in enumerate(getattr(analysis, collection)):
                requirement = by_id.get(judgment.requirement_id)
                bound = definitions.get(judgment.requirement_id)
                name = (bound.key if hasattr(bound, 'key') else bound.get('key')) if bound else (
                    key(requirement.attribute, requirement.value) if requirement else '')
                # A reference item's past request is not supplied to Relation;
                # keep its factual image text, without guessing a dimension.
                for offset, image in enumerate(judgment.image_evidence):
                    path = f'search_analysis.{collection}.{index}.image_evidence.{offset}'
                    if image.image_url != item.image_url:
                        raise ValueError('Relation v2 judgment cites another image: ' + path)
                    invalid = not image.observation.strip() or (requirements is not None and requirement is None)
                    status = ('conflicted' if disputed(name) else 'unavailable' if invalid
                        else 'unknown' if judgment.requirement_id in visibility_unknown else 'known')
                    add(path, image.observation, name, kind='search_image_observation', status=status, image=True,
                        reason='validation_failed' if status == 'unavailable' else None)
        if visibility:
            # Only the saved uncertainty explanation is a limitation reference;
            # neither the visibility grade nor its numerical score is a fact.
            for index, check in enumerate(visibility.requirement_checks):
                if check.requirement_id not in visibility_unknown:
                    continue
                requirement = by_id[check.requirement_id]
                bound = definitions.get(check.requirement_id)
                name = bound.key if bound else key(requirement.attribute, requirement.value)
                add(f'search_analysis.visual_confirmation_v5.requirement_checks.{index}.evidence',
                    check.evidence, name, kind='search_image_observation', status='unknown', image=True)
        for index, conflict in enumerate(analysis.conflicts):
            if any(e.image_url != item.image_url for e in conflict.image_evidence):
                raise ValueError('Relation v2 conflict cites another image.')
            limitations.append(dict(kind='conflict', **conflict.model_dump(mode='json', exclude={'requirement_id'})))
            for dimension in dimensions(ALIASES.get(conflict.attribute, conflict.attribute)):
                observations[dimension]['reasons'].append('conflicting_evidence')

        # Preserve Search's diagnostics as limitations, never revive rejected
        # original facts from before a code projection.
        diagnostic = analysis.validation_v29 or {}
        for change in diagnostic.get('changes', []):
            if not any(token in change.get('reason', '') for token in ('unsupported', 'unverifiable', 'absent_metadata')):
                continue
            before = change.get('before')
            name = key(before['attribute'], before.get('value')) if isinstance(before, dict) and 'attribute' in before else ''
            limitations.append(dict(kind='observation_unavailable', reason='validation_failed',
                source_path='search_analysis.validation_v29', affected_path=change.get('path'), diagnostic=change.get('reason')))
            for dimension in dimensions(name):
                observations[dimension]['reasons'].append('validation_failed')
        if visibility:
            limitations.append(dict(kind='visibility', hidden_parts=visibility.hidden_parts,
                obstruction_causes=visibility.obstruction_causes))
        elif analysis.visual_confirmation_v5 and requirements is None:
            limitations.append(dict(kind='visibility_unavailable',
                reason='Original anchor requirements are not supplied; visibility audit cannot be revalidated.'))
        # relation_observation_v0 is deliberately NOT projected: v2 consumes
        # original Search evidence, not historical Relation-preparation extras.

    for row in observations.values():
        row['status'] = ('conflicted' if 'conflicting_evidence' in row['reasons'] else
            'observed' if row['evidence_refs'] else 'unknown' if row['unknown_refs'] else 'observation_unavailable')
        if row['status'] == 'observation_unavailable' and not row['reasons']:
            row['reasons'].append('missing_observation')
        row['reasons'] = list(dict.fromkeys(row['reasons']))
    return dict(item_id=item.item_id, category=None, facts=facts,
        observations=list(observations.values()), limitations=limitations)


@_preserve_function('packets', 'fashion_recommendation_v2.relation.relation_evidence')
def packets_base(source):
    anchor = (packet_base(source.anchor_item, source.anchor_search_analysis, 'anchor') if source.anchor_item else
        dict(item_id=None, category=source.intent.anchor_category, facts=[], observations=[],
            limitations=[dict(kind='category_anchor', reason='No specific item color, material, fit or image is supplied.')]))
    candidates = {c.item.item_id: packet_base(c.item, c.search_analysis, 'candidate',
        source.candidate_set.resolved_requirements, c.evaluation_item) for c in source.candidate_set.candidates}
    return anchor, candidates


@_preserve_function('evidence_input_hash', 'fashion_recommendation_v2.relation.relation_evidence')
def evidence_input_hash_base(source):
    # Bind the full immutable snapshots, including missing/invalid records; hash
    # them without sending excluded originals to the LLM.
    return canonical_hash(dict(version='v2', intent=source.intent.model_dump(mode='json'),
        anchor=source.anchor_item.model_dump(mode='json') if source.anchor_item else None,
        anchor_analysis=source.anchor_search_analysis.model_dump(mode='json') if source.anchor_search_analysis else None,
        candidate_set=source.candidate_set.model_dump(mode='json')))


@_preserve_function('validate_references', 'fashion_recommendation_v2.relation.relation_evidence')
def validate_references_base(source, evaluations):
    anchor, candidates = packets_base(source)
    for entry in evaluations:
        candidate = candidates[entry.item_id]
        facts = candidate['facts'] + anchor['facts']
        by_ref = {f['ref']: f for f in facts}
        if len(entry.evidence_fields) != len(set(entry.evidence_fields)) or any(r not in by_ref for r in entry.evidence_fields):
            raise ValueError('Relation v2 requires unique exact candidate/anchor fact references.')
        if entry.score is not None:
            known = [by_ref[r] for r in entry.evidence_fields if by_ref[r]['status'] == 'known']
            if not any(f['ref'].startswith('candidate:') for f in known):
                raise ValueError('Numeric relation score needs known candidate evidence; otherwise use null.')
            if source.anchor_item and not any(f['ref'].startswith('anchor:') for f in known):
                raise ValueError('Numeric relation score needs known anchor evidence; otherwise use null.')
        limited = any(f['status'] != 'known' for f in facts) or any(
            p['limitations'] or any(o['status'] != 'observed' or o['reasons'] or o['unknown_refs']
                for o in p['observations']) for p in (candidate, anchor))
        if limited and not entry.uncertainties:
            raise ValueError('Relation v2 missing/invalid/unknown/conflicting observations require uncertainties.')


# ---- relation_evidence_v3 ----
"""v3 facet source authority; reuse v2 identity/source checks without image calls."""
from types import SimpleNamespace as SimpleNamespace_v3
default_policy = _role_module('fashion_recommendation_v2.relation.relation_scoring_v3')
saved_v3 = _role_module('fashion_recommendation_v2.relation.relation_evidence')
from fashion_recommendation_v2.relation.relation_scoring import FACETS_v3 as FACETS
from fashion_recommendation_v2.relation.relation_scoring import WEIGHTS_v3 as WEIGHTS
from fashion_recommendation_v2.relation.relation_scoring import aggregate_v3 as aggregate
from fashion_recommendation_v2.relation.relation_scoring import evidence_refs
from fashion_recommendation_v2.relation.relation_scoring import policy_context_v3 as policy_context

# Used both to explain allowed sources and to validate the model's citations.
# Broad pattern observations may describe type/scale/distribution, but the model
# must independently mark each facet unknown when its specific detail is absent.
SOURCES_v3 = {
    'category_pairing': ('category', 'product_type', 'category_path'),
    'product_type': ('category', 'product_type', 'category_path'),
    'color': ('color', 'detail.color'),
    'pattern_type': ('pattern', 'detail.pattern'),
    'pattern_scale': ('pattern', 'detail.pattern', 'detail.pattern_scale'),
    'pattern_distribution': ('pattern', 'detail.pattern', 'detail.pattern_distribution'),
    'style': ('theme', 'detail.theme', 'detail.style'),
    'season': ('season', 'detail.season'),
    'use_context': ('occasion', 'detail.occasion'),
    'garment_length': ('detail.length', 'detail.dress_length', 'detail.skirt_length', 'detail.garment_length'),
    'sleeve_length': ('sleeve_length', 'detail.sleeve_length'),
    'material': ('material', 'detail.material', 'detail.fabric_composition'),
    'details': ('other_visible_detail_keys',),
}
EXCLUDED_DETAILS = {'detail.fit', 'detail.silhouette', 'detail.volume', 'detail.proportion',
    'detail.size', 'detail.size_type', 'detail.brand', 'detail.garment_care', 'detail.strength',
    'detail.gender', 'detail.audience', 'detail.price'}
NOT_APPLICABLE_SOURCES = {
    'pattern_scale': ('pattern', 'detail.pattern'),
    'pattern_distribution': ('pattern', 'detail.pattern'),
    'sleeve_length': ('category', 'product_type', 'category_path', 'sleeve_length', 'detail.sleeve_length'),
}


@_preserve_function('source_definition', 'fashion_recommendation_v2.relation.relation_evidence_v3')
def source_definition_v3():
    return dict(facet_sources=SOURCES_v3, not_applicable_sources=NOT_APPLICABLE_SOURCES,
        excluded_detail_keys=sorted(EXCLUDED_DETAILS),
        other_details='Visible structure keys excluding every key assigned to another facet and metadata-only facts.',
        category_anchor_ref='anchor:intent.anchor_category')


@_preserve_function('_fact_key', 'fashion_recommendation_v2.relation.relation_evidence_v3')
def _fact_key(fact, analysis, requirements):
    path = fact['ref'].split(':', 1)[1]
    if path == 'intent.anchor_category':
        return 'category'
    if analysis is not None and analysis.evaluation_policy in {'v36', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45'} and path.startswith('search_analysis.attributes.'):
        from fashion_recommendation_v2.search.product_evaluation import attribute_key
        return saved_v3.key(attribute_key(analysis.attributes[int(path.split('.')[2])]))
    if fact['kind'] == 'search_observation':
        value = fact['value']
        return saved_v3.key(value['attribute'], value['value'])
    if path.startswith('item.'):
        name = path.removeprefix('item.')
        return saved_v3.ALIASES.get(name, name)
    if fact['kind'] == 'search_image_observation' and analysis is not None and requirements is not None:
        pieces = path.split('.')
        if len(pieces) >= 5 and pieces[1] in {'judgments', 'alternative_judgments'}:
            judgment = getattr(analysis, pieces[1])[int(pieces[2])]
            bound = (getattr(requirements, 'condition_contract_v26', None) or {}).get(judgment.requirement_id)
            if bound is not None:
                return bound.key if hasattr(bound, 'key') else bound['key']
            requirement = next((r for r in requirements.requirements if r.requirement_id == judgment.requirement_id), None)
            if requirement is not None:
                return saved_v3.key(requirement.attribute, requirement.value)
    return None


@_preserve_function('_facets', 'fashion_recommendation_v2.relation.relation_evidence_v3')
def _facets(name):
    if name is None:
        return []
    matches = [facet for facet, keys in SOURCES_v3.items() if name in keys]
    if matches:
        return matches
    assigned = {key for keys in SOURCES_v3.values() for key in keys}
    if (name.startswith('detail.') and name not in assigned
            and name not in EXCLUDED_DETAILS and name not in saved_v3.METADATA_ONLY_FACTS):
        return ['details']
    return []


@_preserve_function('packets', 'fashion_recommendation_v2.relation.relation_evidence_v3')
def packets_v3(source, *, policy=default_policy):
    anchor, candidates = saved_v3.packets(source)
    if source.anchor_item is None:
        anchor['facts'].append(dict(ref='anchor:intent.anchor_category',
            value=source.intent.anchor_category, status='known', kind='metadata'))
    wanted = {f for name in policy.WEIGHTS[source.intent.relation_type] for f in FACETS[name]}

    def project(packet, analysis, requirements=None):
        refs = {f: [] for f in sorted(wanted)}
        inapplicable = {f: [] for f in sorted(wanted)}
        for fact in packet['facts']:
            name = _fact_key(fact, analysis, requirements)
            for facet in _facets(name):
                if facet in refs:
                    refs[facet].append(fact['ref'])
            for facet, keys in NOT_APPLICABLE_SOURCES.items():
                if facet in inapplicable and name in keys:
                    inapplicable[facet].append(fact['ref'])
        # Retain v2 observations as limitations/history; the facet table alone
        # authorizes v3 scoring. Unmapped facts cannot be scored via raw originals.
        packet['facet_evidence'] = [dict(facet=f, evidence_refs=values,
            not_applicable_evidence_refs=inapplicable[f]) for f, values in refs.items()]
        return packet

    project(anchor, source.anchor_search_analysis)
    by_id = {c.item.item_id: c for c in source.candidate_set.candidates}
    for item_id, packet in candidates.items():
        project(packet, by_id[item_id].search_analysis, source.candidate_set.resolved_requirements)
    return anchor, candidates


@_preserve_function('evidence_input_hash', 'fashion_recommendation_v2.relation.relation_evidence_v3')
def evidence_input_hash_v3(source, *, policy=default_policy, version='v3'):
    return saved_v3.canonical_hash(dict(version=version, original_evidence_sha256=saved_v3.evidence_input_hash(source),
        policy=policy.policy_context(), source_definition=source_definition_v3()))


@_preserve_function('validate_judgments', 'fashion_recommendation_v2.relation.relation_evidence_v3')
def validate_judgments_v3(source, entries, *, policy=default_policy, packet_provider=None):
    anchor, candidates = packets_v3(source, policy=policy) if packet_provider is None else packet_provider(source)
    for entry in entries:
        if entry.item_id not in candidates:
            raise ValueError('Unknown Relation candidate: ' + entry.item_id)
        # This also checks the exact criterion/facet inventory before aggregation.
        policy.aggregate(source.intent.relation_type, entry.criteria)
        candidate = candidates[entry.item_id]
        for criterion in entry.criteria:
            for facet in criterion.facets:
                states = []
                for side, packet, refs in (('anchor', anchor, facet.anchor_evidence),
                        ('candidate', candidate, facet.candidate_evidence)):
                    field = 'not_applicable_evidence_refs' if facet.state == 'not_applicable' else 'evidence_refs'
                    allowed = next((r[field] for r in packet['facet_evidence'] if r['facet'] == facet.facet), [])
                    by_ref = {f['ref']: f for f in packet['facts']}
                    if any(ref not in allowed for ref in refs):
                        raise ValueError(f'{entry.item_id}/{criterion.criterion}/{facet.facet}: invalid {side} evidence; allowed={allowed}')
                    chosen = [by_ref[ref]['status'] for ref in refs]
                    states.extend(chosen)
                    if facet.state in {'assessed', 'not_applicable'} and (not chosen or any(s != 'known' for s in chosen)):
                        raise ValueError(f'{entry.item_id}/{facet.facet}: {side} needs known, relevant evidence; missing/conflicted evidence cannot support a score or inapplicability.')
                if facet.state == 'unknown' and 'unknown' not in states:
                    raise ValueError('Observed unknown requires a saved unknown reference; use observation_unavailable for absent records.')
                if facet.state == 'conflicted' and 'conflicted' not in states:
                    raise ValueError('Conflicted state requires a saved conflicting reference.')
        limited = any(p['limitations'] or any(o['status'] != 'observed' or o['reasons'] or o['unknown_refs']
            for o in p['observations']) for p in (candidate, anchor))
        if limited and not entry.uncertainties:
            raise ValueError('Relevant saved observation limitations require uncertainties.')


@_preserve_function('validate_references', 'fashion_recommendation_v2.relation.relation_evidence_v3')
def validate_references_v3(source, evaluations, *, policy=default_policy, packet_provider=None):
    # Common final-score references still cannot cross candidate/anchor identity.
    anchor, candidates = packets_v3(source, policy=policy) if packet_provider is None else packet_provider(source)
    for entry in evaluations:
        allowed = {f['ref']: f for f in anchor['facts'] + candidates[entry.item_id]['facts']}
        if len(entry.evidence_fields) != len(set(entry.evidence_fields)) or any(ref not in allowed for ref in entry.evidence_fields):
            raise ValueError(f"Relation {policy.POLICY_ID.split('_')[1]} requires exact candidate/anchor references.")


@_preserve_function('validate_ratio', 'fashion_recommendation_v2.relation.relation_evidence_v3')
def validate_ratio_v3(source, ratio, *, policy=default_policy, breakdown_field='score_breakdowns_v3'):
    breakdowns = getattr(ratio, breakdown_field)
    if breakdowns is None or set(breakdowns) != {e.item_id for e in ratio.evaluations}:
        raise ValueError(f"Every {policy.POLICY_ID.split('_')[1]} evaluation needs its preserved score breakdown, and only evaluated IDs may have one.")
    validate_judgments_v3(source, [SimpleNamespace_v3(item_id=e.item_id,
        criteria=breakdowns[e.item_id].judgments, uncertainties=e.uncertainties) for e in ratio.evaluations], policy=policy)
    for entry in ratio.evaluations:
        breakdown = breakdowns[entry.item_id]
        expected = policy.aggregate(source.intent.relation_type, breakdown.judgments)
        if breakdown != expected or entry.score != expected.score or entry.evidence_fields != evidence_refs(breakdown.judgments):
            raise ValueError(f"Relation {policy.POLICY_ID.split('_')[1]} score/coverage/breakdown must match the code-owned aggregation.")


# ---- relation_evidence_v5 ----
"""Search source-separated facts only; each facet selects independently per side."""
from types import SimpleNamespace
saved_v5 = _role_module('fashion_recommendation_v2.relation.relation_evidence')
facets = _role_module('fashion_recommendation_v2.relation.relation_evidence_v3')
policy_v5 = _role_module('fashion_recommendation_v2.relation.relation_scoring_v5')
from fashion_recommendation_v2.search.product_evaluation import validate_attribute as validate_attribute_v5
from fashion_recommendation_v2.search.product_evaluation import attribute_key as attribute_key_v5
s = _role_module('fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v36')

from fashion_recommendation_v2.schemas.relation_scoring import METADATA_ONLY_RELATION_FACETS
METADATA_FACETS_v5 = METADATA_ONLY_RELATION_FACETS


@_preserve_function('source_definition', 'fashion_recommendation_v2.relation.relation_evidence_v5')
def source_definition_v5():
    return {**facets.source_definition(), 'exclusive_fact_root': 'search_analysis.attributes',
        'metadata_only_facets': sorted(METADATA_FACETS_v5),
        'selection': 'Per facet AND per side: valid sufficiently specific image; otherwise metadata; otherwise null. '
            'Known image records may lack this facet detail. Explain that fallback in metadata_fallbacks. '
            'Do not combine contradictory sources; conflicts stay in limitations. Category-only anchors use confirmed intent.'}


@_preserve_function('usable', 'fashion_recommendation_v2.relation.relation_evidence_v5')
def usable(value):
    if hasattr(value, 'model_dump'):
        value = value.model_dump(mode='json')
    if isinstance(value, dict):
        return usable(value.get('values')) if 'values' in value else any(usable(v) for v in value.values())
    if isinstance(value, list):
        return any(usable(v) for v in value)
    return value is not None and (not isinstance(value, str) or value.strip().casefold() not in {'', 'unknown', 'null', 'none', '알 수 없음', '불명'})


@_preserve_function('packet', 'fashion_recommendation_v2.relation.relation_evidence_v5')
def packet_v5(item, analysis, role, wanted, evidence_item=None):
    evidence_item = evidence_item or item
    if analysis is not None and (analysis.item_id, analysis.image_url) != (item.item_id, item.image_url):
        raise ValueError('Relation v5 Search item/image identity mismatch.')
    if (evidence_item.item_id, evidence_item.image_url) != (item.item_id, item.image_url):
        raise ValueError('Relation v5 evaluation snapshot identity mismatch.')
    result = dict(item_id=item.item_id, category=None, facts=[], observations=[], limitations=[], facet_evidence=[])
    refs, na = {f: [] for f in wanted}, {f: [] for f in wanted}
    if analysis is None or analysis.evaluation_policy not in {'v36', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45'}:
        result['limitations'].append(dict(kind='observation_unavailable', reason='source_separated_search_analysis_missing'))
    else:
        for index, row in enumerate(analysis.attributes):
            name = saved_v5.key(attribute_key_v5(row))
            eligible = set(facets._facets(name)) & wanted
            na_facets = {f for f, keys in facets.NOT_APPLICABLE_SOURCES.items() if name in keys} & wanted
            if not eligible and not na_facets:
                continue
            for source_name in ('metadata', 'image_observation'):
                if source_name == 'image_observation' and row.attribute in s.METADATA_ONLY:
                    continue  # A normal nonvisual field is not missing observation.
                allowed = eligible - METADATA_FACETS_v5 if source_name == 'image_observation' else eligible
                if not allowed and not na_facets:
                    continue
                obs = getattr(row, source_name)
                path = f'search_analysis.attributes.{index}.{source_name}'
                if obs is None:
                    result['limitations'].append(dict(kind='observation_unavailable', source_path=path, reason='missing_observation'))
                    continue
                error = None
                try:
                    if source_name not in row.code_validation.validated_sources:
                        raise ValueError('Search did not validate this source.')
                    # Source-local revalidation: failure on the other source cannot erase this fact.
                    probe = s.AttributeDraft(attribute=row.attribute,
                        metadata=obs if source_name == 'metadata' else s.MetadataObservation(value=None, evidence_fields=[], evidence=[]),
                        image_observation=obs if source_name == 'image_observation' else None,
                        metadata_image_consistency=s.ObservedConsistency(status='not_applicable', reason='source-local validation'))
                    validate_attribute_v5(probe, evidence_item, None)
                except ValueError as exc:
                    error = str(exc)
                ref = role + ':' + path
                status = 'unavailable' if error else 'known' if usable(obs.value) else 'unknown'
                result['facts'].append(dict(ref=ref, value=obs.model_dump(mode='json'), status=status,
                    kind='search_image_observation' if source_name == 'image_observation' else 'metadata'))
                for facet in allowed:
                    refs[facet].append(ref)
                for facet in na_facets:
                    na[facet].append(ref)
                if error or status == 'unknown':
                    result['limitations'].append(dict(kind='observation_unavailable' if error else 'unknown',
                        source_path=path, reason=error or 'saved_unknown_value'))
            if row.metadata_image_consistency.status in {'partially_consistent', 'inconsistent'}:
                result['limitations'].append(dict(kind='source_conflict', attribute=name,
                    status=row.metadata_image_consistency.status, reason=row.metadata_image_consistency.reason))
    result['facet_evidence'] = [dict(facet=f, evidence_refs=refs[f], not_applicable_evidence_refs=na[f]) for f in sorted(wanted)]
    return result


@_preserve_function('packets', 'fashion_recommendation_v2.relation.relation_evidence_v5')
def packets_v5(source):
    wanted = {f for criterion in policy_v5.WEIGHTS[source.intent.relation_type] for f in policy_v5.FACETS[criterion]}
    if source.anchor_item is not None:
        anchor = packet_v5(source.anchor_item, source.anchor_search_analysis, 'anchor', wanted)
    else:
        ref = 'anchor:intent.anchor_category'
        anchor = dict(item_id=None, category=source.intent.anchor_category,
            facts=[dict(ref=ref, value=source.intent.anchor_category, status='known', kind='metadata')],
            observations=[], limitations=[dict(kind='category_anchor', reason='Only confirmed category is supplied.')],
            facet_evidence=[dict(facet=f, evidence_refs=[ref] if f in {'category_pairing', 'product_type'} else [],
                not_applicable_evidence_refs=[ref] if f == 'sleeve_length' else []) for f in sorted(wanted)])
    return anchor, {c.item.item_id: packet_v5(c.item, c.search_analysis, 'candidate', wanted, c.evaluation_item)
        for c in source.candidate_set.candidates}


@_preserve_function('evidence_input_hash', 'fashion_recommendation_v2.relation.relation_evidence_v5')
def evidence_input_hash_v5(source):
    return saved_v5.canonical_hash(dict(version='v5', original_evidence_sha256=saved_v5.evidence_input_hash(source),
        policy=policy_v5.policy_context(), source_definition=source_definition_v5()))


@_preserve_function('validate_judgments', 'fashion_recommendation_v2.relation.relation_evidence_v5')
def validate_judgments_v5(source, entries):
    facets.validate_judgments(source, entries, policy=policy_v5, packet_provider=packets_v5)
    anchor, candidates = packets_v5(source)
    for entry in entries:
        fallback = {(r.facet, r.side): r.reason for r in entry.metadata_fallbacks}
        if len(fallback) != len(entry.metadata_fallbacks):
            raise ValueError('Duplicate metadata fallback explanation.')
        used = set()
        for criterion in entry.criteria:
            for facet in criterion.facets:
                for side, packet, refs in [('anchor', anchor, facet.anchor_evidence),
                        ('candidate', candidates[entry.item_id], facet.candidate_evidence)]:
                    kinds = {('image' if '.image_observation' in ref else 'metadata') for ref in refs}
                    if len(kinds) > 1:
                        raise ValueError('Select one source per facet/side; do not mix conflicting sources.')
                    if kinds != {'metadata'} or facet.facet in METADATA_FACETS_v5:
                        continue
                    allowed = next(r for r in packet['facet_evidence'] if r['facet'] == facet.facet)
                    field = 'not_applicable_evidence_refs' if facet.state == 'not_applicable' else 'evidence_refs'
                    known_image = any(f['ref'] in allowed[field] and '.image_observation' in f['ref'] and f['status'] == 'known' for f in packet['facts'])
                    if known_image:
                        key = (facet.facet, side)
                        if key not in fallback:
                            raise ValueError(f'{side}/{facet.facet}: explain why available image evidence is insufficient before using metadata.')
                        used.add(key)
        if set(fallback) != used:
            unused = sorted(set(fallback) - used)
            raise ValueError(f'Metadata fallback explanations must correspond to actual source selections: unused={unused}.')


@_preserve_function('validate_references', 'fashion_recommendation_v2.relation.relation_evidence_v5')
def validate_references_v5(source, evaluations):
    facets.validate_references(source, evaluations, policy=policy_v5, packet_provider=packets_v5)


@_preserve_function('validate_ratio', 'fashion_recommendation_v2.relation.relation_evidence_v5')
def validate_ratio_v5(source, ratio, *, judgment_validator=validate_judgments_v5):
    records = ratio.score_breakdowns_v5
    if records is None or set(records) != {e.item_id for e in ratio.evaluations}:
        raise ValueError('Every evaluated candidate needs a v5 breakdown.')
    judgment_validator(source, [SimpleNamespace(item_id=e.item_id, criteria=records[e.item_id].judgments,
        uncertainties=e.uncertainties, metadata_fallbacks=records[e.item_id].metadata_fallbacks_v5 or []) for e in ratio.evaluations])
    for entry in ratio.evaluations:
        actual = records[entry.item_id]
        expected = policy_v5.aggregate(source.intent.relation_type, actual.judgments)
        expected.metadata_fallbacks_v5 = actual.metadata_fallbacks_v5
        if actual.metadata_fallbacks_v5 is None or actual != expected or entry.score != expected.score or entry.evidence_fields != facets.evidence_refs(actual.judgments):
            raise ValueError('Relation v5 score/coverage/source selections must match preserved judgments.')


# ---- relation_evidence_v6 ----
"""Search observation provenance, without code-owned attribute-to-facet routing."""
saved = _role_module('fashion_recommendation_v2.relation.relation_evidence')
previous = _role_module('fashion_recommendation_v2.relation.relation_evidence_v5')
policy = _role_module('fashion_recommendation_v2.relation.relation_scoring_v5')
from fashion_recommendation_v2.search.product_evaluation import attribute_key
from fashion_recommendation_v2.search.product_evaluation import validate_attribute
search_schema = _role_module('fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_v36')

from fashion_recommendation_v2.schemas.relation_scoring import fallback_error

SEARCH_ROOT = 'search_analysis.attributes'
SOURCES = ('metadata', 'image_observation')
CATEGORY_REF = 'anchor:intent.anchor_category'
METADATA_FACETS = previous.METADATA_FACETS


@_preserve_function('reference', 'fashion_recommendation_v2.relation.relation_evidence_v6')
def reference(role, index, source):
    return f'{role}:{SEARCH_ROOT}.{index}.{source}'


@_preserve_function('source_definition', 'fashion_recommendation_v2.relation.relation_evidence_v6')
def source_definition():
    return dict(exclusive_fact_root=SEARCH_ROOT,
        reference_format=f'{{anchor|candidate}}:{SEARCH_ROOT}.{{original_index}}.{{metadata|image_observation}}',
        observation_sources=list(SOURCES), metadata_only_attributes=sorted(search_schema.METADATA_ONLY),
        metadata_only_facets=sorted(METADATA_FACETS), category_anchor_ref=CATEGORY_REF,
        selection='LLM selects relevant Search attribute keys and observations for each facet and side; '
            'there is no attribute-to-facet allowlist. Prefer sufficiently specific validated image evidence, '
            'otherwise metadata. Explain insufficient relevant known image observations in metadata_fallbacks; '
            'Except material/season: these metadata-only facets never permit metadata_fallbacks; '
            'put evidence in facet reason and missing information in uncertainties. '
            'For other facets a known image counterpart of selected metadata requires this explanation. '
            'Cross-key image relevance is selected by the LLM. Missing/unknown/invalid images need no entry. '
            'One source per facet/side. Original observations and conflicts are preserved; '
            'reference existence does not prove semantic relevance or sufficiency.')


@_preserve_function('packet', 'fashion_recommendation_v2.relation.relation_evidence_v6')
def packet(item, analysis, role, evidence_item=None):
    evidence_item = evidence_item or item
    if analysis is not None and (analysis.item_id, analysis.image_url) != (item.item_id, item.image_url):
        raise ValueError('Relation v6 Search item/image identity mismatch.')
    if (evidence_item.item_id, evidence_item.image_url) != (item.item_id, item.image_url):
        raise ValueError('Relation v6 evaluation snapshot identity mismatch.')
    result = dict(item_id=item.item_id, image_url=item.image_url, category=None,
        facts=[], observations=[], limitations=[])
    if analysis is None or analysis.evaluation_policy not in {'v36', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45'}:
        result['limitations'].append(dict(kind='observation_unavailable', reason='source_separated_search_analysis_missing'))
        return result
    for index, row in enumerate(analysis.attributes):
        # Preserve Search's original key, including detail keys; never normalize into a rubric key.
        key = attribute_key(row)
        for source in SOURCES:
            obs = getattr(row, source)
            path = f'{SEARCH_ROOT}.{index}.{source}'
            if obs is None:
                if source != 'image_observation' or row.attribute not in search_schema.METADATA_ONLY:
                    result['limitations'].append(dict(kind='observation_unavailable', source_path=path, reason='missing_observation'))
                continue
            error = None
            try:
                if source not in row.code_validation.validated_sources:
                    raise ValueError('Search did not validate this source.')
                probe = search_schema.AttributeDraft(attribute=row.attribute,
                    metadata=obs if source == 'metadata' else search_schema.MetadataObservation(value=None, evidence_fields=[], evidence=[]),
                    image_observation=obs if source == 'image_observation' else None,
                    metadata_image_consistency=search_schema.ObservedConsistency(status='not_applicable', reason='source-local validation'))
                validate_attribute(probe, evidence_item, None)
            except ValueError as exc:
                error = str(exc)
            status = 'unavailable' if error else 'known' if previous.usable(obs.value) else 'unknown'
            result['facts'].append(dict(ref=reference(role, index, source), attribute=row.attribute,
                attribute_key=key, value=obs.model_dump(mode='json'), status=status,
                kind='metadata' if source == 'metadata' else 'search_image_observation'))
            if error or status == 'unknown':
                result['limitations'].append(dict(kind='observation_unavailable' if error else 'unknown',
                    source_path=path, reason=error or 'saved_unknown_value'))
        if row.metadata_image_consistency.status in {'partially_consistent', 'inconsistent'}:
            result['limitations'].append(dict(kind='source_conflict', attribute=key,
                status=row.metadata_image_consistency.status, reason=row.metadata_image_consistency.reason))
    return result


@_preserve_function('packets', 'fashion_recommendation_v2.relation.relation_evidence_v6')
def packets(source):
    if source.anchor_item is not None:
        anchor = packet(source.anchor_item, source.anchor_search_analysis, 'anchor')
    else:
        anchor = dict(item_id=None, image_url=None, category=source.intent.anchor_category,
            facts=[dict(ref=CATEGORY_REF, attribute='category', attribute_key='category',
                value=source.intent.anchor_category, status='known', kind='metadata')],
            observations=[], limitations=[dict(kind='category_anchor', reason='Only confirmed category is supplied.')])
    return anchor, {c.item.item_id: packet(c.item, c.search_analysis, 'candidate', c.evaluation_item)
        for c in source.candidate_set.candidates}


@_preserve_function('evidence_input_hash', 'fashion_recommendation_v2.relation.relation_evidence_v6')
def evidence_input_hash(source):
    return saved.canonical_hash(dict(version='v6', original_evidence_sha256=saved.evidence_input_hash(source),
        policy=policy.policy_context(), source_definition=source_definition()))


@_preserve_function('validate_judgments', 'fashion_recommendation_v2.relation.relation_evidence_v6')
def validate_judgments(source, entries):
    anchor, candidates = packets(source)
    for entry in entries:
        if entry.item_id not in candidates:
            raise ValueError('Unknown Relation candidate: ' + entry.item_id)
        policy.aggregate(source.intent.relation_type, entry.criteria)
        candidate = candidates[entry.item_id]
        fallbacks = {}
        evaluated = {f.facet for c in entry.criteria for f in c.facets}
        for row in entry.metadata_fallbacks:
            if row.facet in METADATA_FACETS:
                raise fallback_error(entry.item_id, row.facet, row.side, 'metadata-only facet cannot have fallback.',
                    'Remove this entry; put evidence in facet reason and missing information in uncertainties.')
            if row.facet not in evaluated:
                raise fallback_error(entry.item_id, row.facet, row.side, 'facet is not evaluated for this relation.', 'Remove this entry.')
            if (row.facet, row.side) in fallbacks:
                raise fallback_error(entry.item_id, row.facet, row.side, 'Duplicate metadata fallback explanation.', 'Keep one explanation for this facet/side.')
            fallbacks[row.facet, row.side] = row.reason
        used = set()
        for criterion in entry.criteria:
            for facet in criterion.facets:
                states = []
                for side, evidence, refs in (('anchor', anchor, facet.anchor_evidence),
                        ('candidate', candidate, facet.candidate_evidence)):
                    by_ref = {f['ref']: f for f in evidence['facts']}
                    if any(ref not in by_ref for ref in refs):
                        raise ValueError(f'{entry.item_id}/{facet.facet}: invalid {side} Search observation reference.')
                    selected = [by_ref[ref] for ref in refs]
                    kinds = {f['kind'] for f in selected}
                    if len(kinds) > 1:
                        raise ValueError('Select one source per facet/side; do not mix conflicting sources.')
                    for fact in selected:
                        if fact['kind'] == 'search_image_observation' and (
                                fact['attribute'] in search_schema.METADATA_ONLY or facet.facet in METADATA_FACETS):
                            raise ValueError('Metadata-only attribute/facet cannot cite an image observation.')
                        if fact['ref'] == CATEGORY_REF and not (facet.facet in {'category_pairing', 'product_type'}
                                or facet.facet == 'sleeve_length' and facet.state == 'not_applicable'):
                            raise ValueError('Category anchor supplies no other garment features.')
                    chosen = [f['status'] for f in selected]
                    states.extend(chosen)
                    if facet.state in {'assessed', 'not_applicable'} and (not chosen or any(s != 'known' for s in chosen)):
                        raise ValueError(f'{entry.item_id}/{facet.facet}: {side} needs known evidence.')
                    if kinds == {'metadata'} and facet.facet not in METADATA_FACETS:
                        # Check the source counterpart, not a code-authored facet/attribute mapping.
                        known_image = any(by_ref.get(f['ref'].removesuffix('.metadata') + '.image_observation', {}).get('status') == 'known'
                            for f in selected if f['ref'].endswith('.metadata'))
                        if known_image:
                            key = (facet.facet, side)
                            if key not in fallbacks or not fallbacks[key].strip():
                                raise fallback_error(entry.item_id, facet.facet, side, 'explain why available image evidence is insufficient before using metadata.', 'Add a concrete fallback reason for this side, or select sufficient image evidence.')
                        key = (facet.facet, side)
                        if key in fallbacks:
                            if not fallbacks[key].strip() or not any(f['kind'] == 'search_image_observation' and f['status'] == 'known' for f in evidence['facts']):
                                raise fallback_error(entry.item_id, facet.facet, side, 'Metadata fallback requires a known image observation and concrete explanation.', 'Remove the entry if no known image observation exists; otherwise supply a concrete reason.')
                            used.add(key)
                if facet.state == 'unknown' and 'unknown' not in states:
                    raise ValueError('Observed unknown requires a saved unknown reference; use observation_unavailable for absent records.')
                if facet.state == 'conflicted' and 'conflicted' not in states:
                    raise ValueError('Conflicted state requires a saved conflicting reference.')
        if set(fallbacks) != used:
            facet_name, side = sorted(set(fallbacks) - used)[0]
            raise fallback_error(entry.item_id, facet_name, side, 'Metadata fallback explanations must correspond to actual source selections; this side did not select metadata.', 'Remove this entry from the image/empty side; explain only the side that selected metadata.')
        if (anchor['limitations'] or candidate['limitations']) and not entry.uncertainties:
            raise ValueError('Relevant saved observation limitations require uncertainties.')


@_preserve_function('validate_references', 'fashion_recommendation_v2.relation.relation_evidence_v6')
def validate_references(source, evaluations):
    from fashion_recommendation_v2.relation.relation_evidence import validate_references_v3 as validate
    validate(source, evaluations, policy=policy, packet_provider=packets)


@_preserve_function('validate_ratio', 'fashion_recommendation_v2.relation.relation_evidence_v6')
def validate_ratio(source, ratio):
    previous.validate_ratio(source, ratio, judgment_validator=validate_judgments)
