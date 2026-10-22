"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- orchestrator_quotes ----

"""Quote/ID projections for v12; no occurrence selection or synthetic offsets."""

@_preserve_function('quote_based', 'fashion_recommendation_v2.orchestrator_quotes')
def quote_based(assessment):
    return getattr(assessment, 'quote_contract', None) == 'v12'

@_preserve_function('unit_quotes', 'fashion_recommendation_v2.orchestrator_quotes')
def unit_quotes(units):
    return [span.source_text for unit in units for span in unit.spans]

@_preserve_function('related_units', 'fashion_recommendation_v2.orchestrator_quotes')
def related_units(assessment, quote):
    """Connect relation wording to classified units through verbatim quotations."""
    return [unit for unit in assessment.semantic_units if any((quote in span.source_text or span.source_text in quote for span in unit.spans))]

@_preserve_function('retained_query', 'fashion_recommendation_v2.orchestrator_quotes')
def retained_query(query, assessment, omitted):
    if not omitted:
        return query
    # Select entire units by state identity. Never delete all matching substrings
    # from the original: a repeated word may also belong to a retained unit.
    return '\n'.join(unit_quotes((u for u in assessment.semantic_units if u.state_id not in omitted))).strip()
