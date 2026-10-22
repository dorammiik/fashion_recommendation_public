"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- product_identity_v45 ----

"""Shared product identity semantics for request interpretation and evaluation."""
PRODUCT_IDENTITY_RULES = """
Preserve the user's original product-type distinction: Korean 셔츠 and 티셔츠 are
separate requested types. Do not broaden 셔츠 into a generic upper-body garment
that includes T-shirts merely because English 'T-shirt' contains 'shirt'. Retain
original source_text and explicitly allowed OR alternatives. A broad 상의 request
or an explicit 셔츠 또는 티셔츠 request may include T-shirts; do not narrow it.
Do not infer a garment type from a V neckline alone. Use the actual garment
construction and supplied product evidence. If both listing and image establish
a T-shirt when 셔츠 was requested, the product-type judgment is unmet. This takes
precedence over treating broad/specific terminology as an explainable difference.
If product identity is genuinely unresolved because sources conflict, keep unknown.
Never rewrite recorded product observations to fit a requested type.
"""
PRODUCT_IDENTITY_EXAMPLE = """
Representative example (product type): a request for 셔츠 with both listing and
image showing a V-neck T-shirt is unmet. For 상의 or explicitly allowed 셔츠/티셔츠,
do not reject that garment solely because it is a T-shirt.
"""
