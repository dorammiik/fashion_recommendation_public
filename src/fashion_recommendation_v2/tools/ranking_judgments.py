"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- ranking_judgments_v6 ----

"""Derive Ranking relevance from saved evidence, without another model call.

An evidenced mismatch is unmet. Missing support, unresolved conflict and an
unobservable requested property are unknown, never proof of a mismatch. Q/V
are independent observations: a clearly visible mismatch still has V=met.
Generation and output validation both use this policy. Inputs are read-only.
"""
from fashion_recommendation_v2.schemas.product_evidence import RequirementJudgment
from fashion_recommendation_v2.schemas.ranking import RequirementDerivationV6
from fashion_recommendation_v2.search.condition_semantics import ALIASES
from fashion_recommendation_v2.search.condition_semantics import METADATA_ONLY_FACTS
from fashion_recommendation_v2.search.condition_semantics import definition
from fashion_recommendation_v2.search.condition_semantics import requirement_hash
from fashion_recommendation_v2.search.condition_semantics import validate_condition_contract
from fashion_recommendation_v2.search.product_sources import present_field
from fashion_recommendation_v2.search.planning_rules import requirement_alternatives

@_preserve_function('canonical_key', 'fashion_recommendation_v2.tools.ranking_judgments_v6')
def canonical_key(key):
    key = key.casefold().replace('-', '_').replace(' ', '_')
    key = ALIASES.get(key, key)
    return 'product_type' if key in {'category', 'avoid_product_type'} else key

@_preserve_function('same_property', 'fashion_recommendation_v2.tools.ranking_judgments_v6')
def same_property(a, b):
    a, b = (canonical_key(a), canonical_key(b))
    # A specific dress-length conflict is not evidence against an unrelated
    # legacy free-text detail. A broad detail conflict does cover detail keys.
    return a == b or (b == 'detail' and a.startswith('detail.'))

@_preserve_function('derive_soft_judgments', 'fashion_recommendation_v2.tools.ranking_judgments_v6')
def derive_soft_judgments(candidate, source, *, visual_checks=None):
    analysis = candidate.search_analysis
    item = candidate.evaluation_item or candidate.item
    snapshot = source.resolved_requirements
    requirements = {r.requirement_id: r for r in snapshot.requirements}
    if len(requirements) != len(snapshot.requirements):
        raise ValueError('Ranking v6 requires unique condition IDs.')
    if snapshot.condition_contract_v26 is not None:
        validate_condition_contract(snapshot)
    actual = [j.requirement_id for j in analysis.judgments]
    if len(actual) != len(set(actual)) or set(actual) != set(requirements):
        raise ValueError('Ranking v6 requires exactly the saved condition IDs.')
    by_id = {j.requirement_id: j for j in analysis.judgments}
    checks = {c.requirement_id: c for c in (analysis.visual_confirmation_v5.requirement_checks if visual_checks is None else visual_checks)}
    alternatives = {}
    expected_alternatives = {}
    # Search generation and validation use this same inventory. In particular,
    # StylistDetailValue.values is explicitly OR in the source schema; do not
    # mistake its object wrapper for a scalar or rewrite the saved requirement.
    for rid, value in requirement_alternatives(snapshot):
        # Retain the existing single-element list behavior as well.
        expected_alternatives.setdefault(rid, []).append(value)
    for entry in analysis.alternative_judgments:
        if entry.requirement_id not in requirements:
            raise ValueError('OR evidence references an unknown condition.')
        alternatives.setdefault(entry.requirement_id, []).append(entry)

    def project(judgment, requirement):
        rule = definition(requirement)
        # Identity errors must not be converted to mere uncertainty.
        if any((e.image_url != item.image_url for e in judgment.image_evidence)):
            raise ValueError('Ranking v6 judgment cites another image.')
        fields = [p for p in judgment.evidence_fields if present_field(item, p, source.price_conversion)]
        reasons = ['absent_metadata_path'] if fields != judgment.evidence_fields else []
        metadata = bool(fields and any((t.strip() for t in judgment.evidence)))
        images = [e for e in judgment.image_evidence if e.observation.strip()]
        supported = metadata or (images and rule.key not in METADATA_ONLY_FACTS)
        if not supported:
            reasons.append('insufficient_evidence')
        if any((c.requirement_id == requirement.requirement_id or same_property(rule.key, c.attribute) for c in analysis.conflicts)):
            reasons.append('unresolved_conflict')
        check = checks.get(requirement.requirement_id)
        # Do not use overall V/hidden_parts to downgrade unrelated conditions.
        if check is not None and check.applicable and (check.status == 'unknown'):
            reasons.append('not_observable')
        uncertain = any((r in reasons for r in ('insufficient_evidence', 'unresolved_conflict', 'not_observable')))
        if uncertain:
            derived = RequirementJudgment(requirement_id=judgment.requirement_id, status='unknown', evidence=['Ranking v6: ' + ', '.join(reasons) + '.'])
        else:
            # No exact-string comparison of fashion synonyms, no new polarity
            # interpretation, and no promotion of a saved unknown to unmet.
            derived = judgment.model_copy(deep=True, update={'evidence_fields': fields})
        return (derived, reasons)
    results, diagnostics = ([], [])
    for rid, requirement in requirements.items():
        if requirement.kind != 'soft':
            continue
        original = by_id[rid]
        derived, reasons = project(original, requirement)
        allowed = expected_alternatives.get(rid, requirement.value if isinstance(requirement.value, list) and (not requirement.unrestricted) else [])
        if allowed:
            entries = alternatives.get(rid, [])
            values = [a.value for a in entries]
            if len(values) != len(set(values)) or not set(values) <= set(allowed):
                raise ValueError('Ranking v6 OR evidence has duplicate/unknown alternatives.')
            projected = []
            for entry in entries:
                judgment = RequirementJudgment(**entry.model_dump(exclude={'value'}))
                alternative, causes = project(judgment, requirement)
                projected.append(alternative)
                reasons.extend(causes)
            statuses = [j.status for j in projected]
            complete = set(values) == set(allowed)
            status = 'met' if 'met' in statuses else 'unmet' if complete and statuses and all((s == 'unmet' for s in statuses)) else 'unknown'
            contributing = [j for j in projected if j.status == status]
            derived = RequirementJudgment(requirement_id=rid, status=status, evidence_fields=list(dict.fromkeys((p for j in contributing for p in j.evidence_fields))), evidence=[t for j in contributing for t in j.evidence] or ['Ranking v6: OR evidence is inconclusive.'], image_evidence=[e.model_copy(deep=True) for j in contributing for e in j.image_evidence])
            reasons.append('or_aggregation')
            if not complete:
                reasons.append('incomplete_or_evidence')
        elif alternatives.get(rid):
            raise ValueError('Ranking v6 alternative evidence requires an OR condition.')
        results.append(derived)
        diagnostics.append(RequirementDerivationV6(requirement_sha256=requirement_hash(requirement), source_judgment=original.model_copy(deep=True), derived_judgment=derived.model_copy(deep=True), reasons=list(dict.fromkeys(reasons)) or ['saved_judgment']))
    return (results, diagnostics)
