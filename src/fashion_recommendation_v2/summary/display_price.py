"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- display_price ----

"""Request-local display conversion, independent of copy generation and search budgets."""
from datetime import datetime
from zoneinfo import ZoneInfo
from fashion_recommendation_v2.schemas.summary import RecommendationResponse_summary_v12 as RecommendationResponse
from fashion_recommendation_v2.schemas.summary import won_amount_summary_v12 as won_amount
from fashion_recommendation_v2.schemas.price import FXRateSnapshot
from fashion_recommendation_v2.tools.price_client import FrankfurterFXClient
from fashion_recommendation_v2.tools.price_client import FXRateUnavailableError

@_preserve_function('fetch_display_fx', 'fashion_recommendation_v2.summary.display_price')
def fetch_display_fx(*, fx_client=None, current_date=None):
    today = current_date or datetime.now(ZoneInfo('Asia/Seoul')).date()
    try:
        fx = FXRateSnapshot.model_validate((fx_client or FrankfurterFXClient()).get_rate(base_currency='USD', quote_currency='KRW', current_date=today))
        if fx.base_currency != 'USD' or fx.quote_currency != 'KRW' or fx.requested_date != today or (not 0 <= (today - fx.rate_date).days <= 7):
            raise FXRateUnavailableError('Display FX currency/date mismatch')
    except (FXRateUnavailableError, OSError, ValueError, TypeError) as exc:
        return (None, f'{type(exc).__name__}: {exc}')
    return (fx, None)

@_preserve_function('apply_krw_prices', 'fashion_recommendation_v2.summary.display_price')
def apply_krw_prices(response, snapshot, *, version='v12'):
    response_type = RecommendationResponse
    if version == 'v13':
        from fashion_recommendation_v2.schemas.summary import RecommendationResponse_summary_v13 as response_type
    payload = response.model_dump()
    payload.update(summary_version=version, display_fx=None, display_fx_error=None)
    fx, error = snapshot
    has_usd = any((item.price and item.price.currency == 'USD' for item in response.recommendations))
    if has_usd:
        payload['display_fx'] = fx.model_dump() if fx else None
        payload['display_fx_error'] = error
    for item in payload['recommendations']:
        item['display_price_krw'] = won_amount(item['price']['value'], fx.rate) if fx and item['price'] and (item['price']['currency'] == 'USD') else None
    return response_type.model_validate(payload)

@_preserve_function('add_krw_prices', 'fashion_recommendation_v2.summary.display_price')
def add_krw_prices(response, *, fx_client=None, current_date=None):
    snapshot = fetch_display_fx(fx_client=fx_client, current_date=current_date) if any((item.price and item.price.currency == 'USD' for item in response.recommendations)) else (None, None)
    return apply_krw_prices(response, snapshot)
