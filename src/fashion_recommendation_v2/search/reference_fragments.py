"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- reference_fragments_v57 ----

"""Bounded, literal reference decomposition; keep full fact and path as provenance."""
import re as re_reference_fragments_v57
from fashion_recommendation_v2.search.condition_semantics import provenance_dimension_v30 as provenance_dimension_v30_reference_fragments_v57
FRAGMENT_GUIDANCE_reference_fragments_v57 = 'v57 permits literal reference fragments within fit/color/pattern and the explicit fit -> detail.skirt_silhouette, color -> detail.pattern_colors mappings. Values must be literal spans of source_text; source_text must quote the supplied full fact or a contiguous part. Skirt silhouette quotes retain skirt; pattern-color quotes retain floral/flower/pattern/print. Original source value and path remain in derived bindings. This scoped exception replaces whole-value equality only for these splits; no invented precision, paraphrased fragments, or new product identity is allowed.'

@_preserve_function('decomposed_facts', 'fashion_recommendation_v2.search.reference_fragments_v57')
def decomposed_facts_reference_fragments_v57(source, condition):
    if not source.similarity_reference:
        return []
    dimension = provenance_dimension_v30_reference_fragments_v57(condition.attribute, condition.value)
    value = condition.value
    values = list(value.values) if hasattr(value, 'key') else value if isinstance(value, list) else [value]
    facts = []
    for key, originals in source.similarity_reference.attributes.items():
        source_dimension = key.removeprefix('detail.')
        allowed = dimension == source_dimension and dimension in {'fit', 'color', 'pattern'} or (source_dimension, dimension) in {('fit', 'skirt_silhouette'), ('color', 'pattern_colors')}
        if not allowed:
            continue
        for index, original in enumerate(originals):
            if not condition.source_text or condition.source_text not in original:
                continue
            if dimension == 'skirt_silhouette' and 'skirt' not in condition.source_text.casefold():
                continue
            if dimension == 'pattern_colors' and (not re_reference_fragments_v57.search(r'floral|flower|pattern|print', condition.source_text, re_reference_fragments_v57.I)):
                continue
            for part in values:
                if not isinstance(part, str) or not part.strip() or part == original:
                    continue
                if re_reference_fragments_v57.search(r'(?<!\w)' + re_reference_fragments_v57.escape(part) + r'(?!\w)', condition.source_text, re_reference_fragments_v57.I):
                    facts.append(dict(value=part, source_value=original, path=f'similarity_reference.attributes.{key}[{index}]'))
    return facts
