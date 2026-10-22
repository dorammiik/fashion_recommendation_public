"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- contracts ----

"""Explicit version wiring; v0 stays replayable, v1/v2 are opt-in for services."""
CONTRACTS = {'v0': dict(runner='agents.preference_runner.PreferenceRunner', schema='schemas.preference_profile.PreferenceProfile', prompt='prompts.preference.PREFERENCE_PROMPT'), 'v4': dict(runner='agents.preference_interpretation_runner.PreferenceAgent', schema='schemas.preference.interpretation.preference_interpretation_v4.PreferenceProfileV4', prompt='prompts.preference.interpretation.preference_interpretation_v4.PREFERENCE_INTERPRETATION_PROMPT', input_policy='preference-sources-v1+attributes-v2', cache_reuse=False), 'v3': dict(runner='agents.preference_interpretation_runner.PreferenceAgent', schema='schemas.preference.interpretation.preference_interpretation_v3.PreferenceProfileV3', prompt='prompts.preference.interpretation.preference_interpretation_v3.PREFERENCE_INTERPRETATION_PROMPT', input_policy='preference-sources-v1+attributes-v2', cache_reuse=False), 'v2': dict(runner='agents.preference_interpretation_runner.PreferenceAgent', schema='schemas.preference.interpretation.preference_interpretation_v2.PreferenceProfileV2', prompt='prompts.preference.interpretation.preference_interpretation_v2.PREFERENCE_INTERPRETATION_PROMPT', input_policy='preference-sources-v1+attributes-v2', cache_reuse=False), 'v1': dict(runner='agents.preference_interpretation_runner.PreferenceAgent', schema='schemas.preference.interpretation.preference_interpretation_v1.PreferenceProfileV1', prompt='prompts.preference.interpretation.preference_interpretation_v1.PREFERENCE_INTERPRETATION_PROMPT', input_policy='preference-sources-v1', cache_reuse=False)}

@_preserve_function('get_contract', 'fashion_recommendation_v2.preference.contracts')
def get_contract(version):
    if version not in CONTRACTS:
        raise ValueError('Unsupported Preference version: ' + version)
    return CONTRACTS[version]
