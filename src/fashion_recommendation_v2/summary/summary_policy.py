"""Summary model selection shared by the service and the v7 eval profile."""

SUMMARY_MODEL = 'gpt-5.6-luna'


def validate_v7_model_settings(model: str, reasoning_effort: str | None) -> None:
    # Preserve the existing API-default reasoning behavior; change only the model.
    if model != SUMMARY_MODEL or reasoning_effort is not None:
        raise ValueError(f'Summary v7 requires {SUMMARY_MODEL} with API-default reasoning.')


SUMMARY_V8_MODEL = 'gpt-6-luna'

def validate_v8_model_settings(model: str, reasoning_effort: str | None) -> None:
    if model != SUMMARY_V8_MODEL or reasoning_effort is not None:
        raise ValueError(f'Summary v8 requires {SUMMARY_V8_MODEL} with API-default reasoning.')


SUMMARY_V9_MODEL = SUMMARY_V8_MODEL

def validate_v9_model_settings(model: str, reasoning_effort: str | None) -> None:
    if model != SUMMARY_V9_MODEL or reasoning_effort is not None:
        raise ValueError(f'Summary v9 requires {SUMMARY_V9_MODEL} with API-default reasoning.')


SUMMARY_V10_MODEL = SUMMARY_V9_MODEL


def validate_v10_model_settings(model: str, reasoning_effort: str | None) -> None:
    if model != SUMMARY_V10_MODEL or reasoning_effort is not None:
        raise ValueError(f'Summary v10 requires {SUMMARY_V10_MODEL} with API-default reasoning.')


# v11 keeps v10 generation/model policy; only request-local validation is reused.
SUMMARY_V11_MODEL = SUMMARY_V10_MODEL
validate_v11_model_settings = validate_v10_model_settings
