"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- product_sources ----

"""Product metadata source paths shared by observation generation and code checks."""

@_preserve_function('evidence_fields', 'fashion_recommendation_v2.search.product_sources')
def evidence_fields(item, conversion):
    """Enumerate real, nonempty paths in the exact item representation sent to LLM."""
    paths = []

    def visit(value, prefix=''):
        for key, child in value.items():
            path = f'{prefix}.{key}' if prefix else key
            if child is None or child == [] or child == {} or (child == ''):
                continue
            paths.append(path)
            if isinstance(child, dict):
                visit(child, path)
    visit(item.model_dump(mode='json'))
    if conversion:
        paths.append('price_conversion')
    return paths

@_preserve_function('present_field', 'fashion_recommendation_v2.search.product_sources')
def present_field(item, path: str, conversion) -> bool:
    return path in evidence_fields(item, conversion)
