"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- summary_policy ----

"""Summary model selection shared by the service and the v7 eval profile."""
SUMMARY_MODEL = 'gpt-5.6-luna'

@_preserve_function('validate_v7_model_settings', 'fashion_recommendation_v2.summary.summary_policy')
def validate_v7_model_settings(model: str, reasoning_effort: str | None) -> None:
    # Preserve the existing API-default reasoning behavior; change only the model.
    if model != SUMMARY_MODEL or reasoning_effort is not None:
        raise ValueError(f'Summary v7 requires {SUMMARY_MODEL} with API-default reasoning.')
SUMMARY_V8_MODEL = 'gpt-6-luna'

@_preserve_function('validate_v8_model_settings', 'fashion_recommendation_v2.summary.summary_policy')
def validate_v8_model_settings(model: str, reasoning_effort: str | None) -> None:
    if model != SUMMARY_V8_MODEL or reasoning_effort is not None:
        raise ValueError(f'Summary v8 requires {SUMMARY_V8_MODEL} with API-default reasoning.')
SUMMARY_V9_MODEL = SUMMARY_V8_MODEL

@_preserve_function('validate_v9_model_settings', 'fashion_recommendation_v2.summary.summary_policy')
def validate_v9_model_settings(model: str, reasoning_effort: str | None) -> None:
    if model != SUMMARY_V9_MODEL or reasoning_effort is not None:
        raise ValueError(f'Summary v9 requires {SUMMARY_V9_MODEL} with API-default reasoning.')
SUMMARY_V10_MODEL = SUMMARY_V9_MODEL

@_preserve_function('validate_v10_model_settings', 'fashion_recommendation_v2.summary.summary_policy')
def validate_v10_model_settings(model: str, reasoning_effort: str | None) -> None:
    if model != SUMMARY_V10_MODEL or reasoning_effort is not None:
        raise ValueError(f'Summary v10 requires {SUMMARY_V10_MODEL} with API-default reasoning.')
# v11 keeps v10 generation/model policy; only request-local validation is reused.
SUMMARY_V11_MODEL = SUMMARY_V10_MODEL
validate_v11_model_settings = validate_v10_model_settings
# v12 preserves v11 copy generation; conversion is code-owned.
SUMMARY_V12_MODEL = SUMMARY_V11_MODEL
validate_v12_model_settings = validate_v11_model_settings
