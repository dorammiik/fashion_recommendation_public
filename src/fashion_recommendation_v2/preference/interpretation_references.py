"""Stable profile references and hashes; independent of Search observation extraction."""
from fashion_recommendation_v2.module_compat import import_module as _role_module
from hashlib import sha256
import json

def fingerprint(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def category(snapshot):
    # Stable source category, not a new t_shirt semantic classifier.
    path = snapshot.item.category_path
    if not path:
        return None, None
    return 'category_'+fingerprint(path)[:20], path


def validate_references(interpretations, evidence, categories):
    from fashion_recommendation_v2.schemas.preference.interpretation.preference_interpretation import Interpretation as InterpretationV2
    from fashion_recommendation_v2.preference.interpretation_attributes import validate_detail_keys
    validate_detail_keys([i for i in interpretations if isinstance(i, InterpretationV2)], evidence)
    ids = {e.evidence_id for e in evidence}
    for interpretation in interpretations:
        refs = {*interpretation.supporting_evidence_refs, *interpretation.counter_evidence_refs}
        if not refs <= ids:
            raise ValueError('Unknown or ineffective evidence reference')
        if not set(interpretation.scope.categories) <= set(categories):
            raise ValueError('Unknown category reference')
