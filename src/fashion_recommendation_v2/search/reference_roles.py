"""One role policy shared by v31 requirements instructions and projections."""
from fashion_recommendation_v2.module_compat import import_module as _role_module
from fashion_recommendation_v2.search.requirement_sources import reference_facts_v30
from fashion_recommendation_v2.search.requirement_sources import condition_values_v30

ROLE_SEMANTICS = """
Source and role are independent. source=reference identifies the evidence origin.
role=target means a condition applies to the new product being searched for.
role=anchor means an existing garment used as pairing context, not a target condition.
For a similar-dress request, floral pattern from the reference dress is
source=reference, role=target. For a top to wear with an existing skirt, the skirt
is role=anchor. Do not label similarity preferences anchor merely because their
source is a reference. Structure, classify and repair use this same distinction.
Never revive excluded original/provenance-only conditions as target constraints.
"""


def target_role_evidence(source, condition):
    # This slot is supplied by the similarity producer, not inferred from words
    # in original_user_query or a pairing garment's general metadata.
    if source.similarity_reference is None or condition.polarity != 'positive':
        return []
    if condition.attribute in {'price', 'product_type', 'avoid_product_type'}:
        return []
    facts = reference_facts_v30(source, condition)
    values = condition_values_v30(condition)
    if not values or any(value not in [f['value'] for f in facts] for value in values):
        return []
    selected = [f for f in facts if f['value'] in values]
    if not condition.source_text.strip() or not any(condition.source_text in f['value'] for f in selected):
        return []
    return selected
