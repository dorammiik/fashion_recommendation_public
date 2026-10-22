"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- personalization_policy ----

"""Request-local personalization policy; never mutate the user/session state."""

@_preserve_function('effective_mode', 'fashion_recommendation_v2.personalization_policy')
def effective_mode(mode, intent):
    return 'cold' if intent is not None and intent.relation_type == 'similarity' else mode

@_preserve_function('similarity_input', 'fashion_recommendation_v2.personalization_policy')
def similarity_input(source):
    intent = source.relation_intent
    if intent is None and getattr(source, 'ralationRatio', None) is not None:
        intent = source.ralationRatio.intent
    return source.model_copy(update={'personalization_mode': effective_mode(source.personalization_mode, intent)}, deep=True)
