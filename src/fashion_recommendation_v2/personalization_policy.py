"""Request-local personalization policy; never mutate the user/session state."""
def effective_mode(mode, intent):
    return 'cold' if intent is not None and intent.relation_type == 'similarity' else mode


def similarity_input(source):
    intent = source.relation_intent
    if intent is None and getattr(source, 'ralationRatio', None) is not None:
        intent = source.ralationRatio.intent
    return source.model_copy(update={'personalization_mode': effective_mode(source.personalization_mode, intent)}, deep=True)
