"""Version-aware storage parsing, without changing v0 consumer schemas."""
from fashion_recommendation_v2.module_compat import import_module as _role_module
import json
from fashion_recommendation_v2.schemas.preference_profile import PreferenceProfile
from fashion_recommendation_v2.schemas.preference.interpretation.preference_interpretation import PreferenceProfileV1_v1 as PreferenceProfileV1


def parse_profile(payload):
    data = json.loads(payload)
    from fashion_recommendation_v2.schemas.preference.interpretation.preference_interpretation import PreferenceProfileV2_v2 as PreferenceProfileV2
    schema = {'1.0': PreferenceProfile, '2.0': PreferenceProfileV1, '3.0': PreferenceProfileV2}.get(data.get('schema_version'), PreferenceProfile)
    if data.get('schema_version') == '3.0' and data.get('interpretation_version') == 'preference-interpretation-v3':
        from fashion_recommendation_v2.schemas.preference.interpretation.preference_interpretation import PreferenceProfileV3
        schema = PreferenceProfileV3
    if data.get('schema_version') == '3.0' and data.get('interpretation_version') == 'preference-interpretation-v4':
        from fashion_recommendation_v2.schemas.preference.interpretation.preference_interpretation import PreferenceProfileV4
        schema = PreferenceProfileV4
    return schema.model_validate_json(payload)


def parse_evidence(payload):
    from fashion_recommendation_v2.schemas.preference import PreferenceEvidence
    from fashion_recommendation_v2.schemas.preference.interpretation.preference_interpretation import InterpretationEvidence
    data = json.loads(payload)
    schema = InterpretationEvidence if data.get('schema_version') == 'preference-evidence-v1' else PreferenceEvidence
    return schema.model_validate_json(payload)
