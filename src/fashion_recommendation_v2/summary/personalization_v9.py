"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- personalization_v9 ----

"""Project only final selected Ranking v12 items; never infer taste or rerank."""
from fashion_recommendation_v2.schemas.summary import PersonalizationContext

@_preserve_function('attach_context', 'fashion_recommendation_v2.summary.personalization_v9')
def attach_context(source, items):
    record = source.final_ranking.personalization_v12
    if record is None:
        # Historical inputs retain their original meaning; missing is not Cold.
        return
    selected = {row.item_id for row in source.final_ranking.ranked_items}
    if {item['item_id'] for item in items} != selected:
        raise ValueError('Summary projection must contain exactly selected Ranking items')
    for item in items:
        key = item['item_id']
        entry = record['items'][key]
        context = PersonalizationContext(p_active=entry['p_active'], selection_kind=record['selection'][key]['kind'], inactive_reason=entry['inactive_reason'])
        item['personalization_context'] = context.model_dump()
        if not context.p_active:
            item['preference_support'] = []
