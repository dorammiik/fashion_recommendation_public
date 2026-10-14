from fashion_recommendation_v2.module_compat import import_module as _role_module
from datetime import date
from decimal import Decimal
from io import BytesIO
from urllib.error import URLError
from urllib.parse import parse_qs
from urllib.parse import urlparse

import pytest
from pydantic import ValidationError

from fashion_recommendation_v2.tools.price_translate import PriceFXRuntime
from fashion_recommendation_v2.schemas.price import FXRateSnapshot
from fashion_recommendation_v2.schemas.price import PriceConstraint
from fashion_recommendation_v2.schemas.search.planning.search_planning import SearchQueryPlan
from fashion_recommendation_v2.tools.price_client import FrankfurterFXClient
from fashion_recommendation_v2.tools.price_client import FXRateUnavailableError


DAY = date(2024, 5, 19)  # Sunday: a Friday rate is valid.


class FixedFXClient:
    def __init__(self, rate="0.0007142857142857142857142857143"):
        self.rate = Decimal(rate)
        self.calls = []

    def get_rate(self, *, base_currency, quote_currency, current_date):
        self.calls.append((base_currency, quote_currency, current_date))
        return FXRateSnapshot(
            base_currency=base_currency, quote_currency=quote_currency,
            rate=self.rate, requested_date=current_date,
            rate_date=current_date, provider="test",
        )


@pytest.mark.parametrize("kwargs", [
    {}, {"max_amount": "-1"}, {"max_amount": "NaN"}, {"max_amount": "Infinity"},
    {"max_amount": "30,000"}, {"max_amount": 30000},
    {"min_amount": "30000", "max_amount": "20000"},
])
def test_invalid_original_budgets_are_rejected(kwargs):
    with pytest.raises(ValidationError):
        PriceConstraint(currency="KRW", **kwargs)


def test_rounding_preserves_both_budget_bounds_and_original_plan():
    client = FixedFXClient()
    runtime = PriceFXRuntime(client)
    original = PriceConstraint(currency="KRW", min_amount="20000", max_amount="30000")
    conversion = runtime.convert(constraint=original, current_date=DAY)
    assert conversion.min_amount == Decimal("14.29")
    assert conversion.max_amount == Decimal("21.42")
    assert client.calls == [("KRW", "USD", DAY)]
    plan = SearchQueryPlan(
        query="black trousers", category_ids=["63863"],
        aspect_filters={"Size": ["L"]}, price_constraint=original,
    )
    executed = runtime.apply(plan, conversion)
    assert executed.aspect_filters == {"Size": ["L"], "PriceMin": 14.29, "PriceMax": 21.42}
    assert executed.price_constraint == original
    assert plan.aspect_filters == {"Size": ["L"]}
    assert runtime.apply(executed, conversion) == executed  # no double conversion
    assert executed.model_dump(mode="json")["price_conversion"]["original"]["max_amount"] == "30000"
    with pytest.raises(ValidationError):
        original.max_amount = "50000"


@pytest.mark.parametrize("currency,expected", [("USD", "30.12"), ("JPY", "30")])
def test_same_currency_skips_lookup_and_respects_minor_units(currency, expected):
    client = FixedFXClient()
    result = PriceFXRuntime(client).convert(
        constraint=PriceConstraint(currency=currency, max_amount="30.129"),
        current_date=DAY, target_currency=currency,
    )
    assert result.max_amount == Decimal(expected)
    assert result.fx.provider == "identity"
    assert client.calls == []


def test_zero_upper_bound_and_unrepresentable_interval():
    runtime = PriceFXRuntime(FixedFXClient())
    assert runtime.convert(
        constraint=PriceConstraint(currency="KRW", max_amount="0"), current_date=DAY,
    ).max_amount == Decimal("0.00")
    with pytest.raises(ValueError, match="No representable"):
        runtime.convert(
            constraint=PriceConstraint(currency="USD", min_amount="1.001", max_amount="1.002"),
            current_date=DAY,
        )


def test_frankfurter_requests_bounded_history_and_selects_latest_prior_rate(monkeypatch):
    calls = []

    def open_request(request, *, timeout):
        calls.append((request, timeout))
        return BytesIO(b'''[
          {"date":"2024-05-17","base":"EUR","quote":"KRW","rate":1400},
          {"date":"2024-05-17","base":"EUR","quote":"USD","rate":1.05},
          {"date":"2024-05-20","base":"EUR","quote":"KRW","rate":1000},
          {"date":"2024-05-18","base":"EUR","quote":"USD","rate":1.06},
          {"date":"2024-05-16","base":"EUR","quote":"KRW","rate":1300},
          {"date":"2024-05-16","base":"EUR","quote":"USD","rate":1.04}
        ]''')

    monkeypatch.setattr("fashion_recommendation_v2.tools.price_client.urlopen", open_request)
    rate = FrankfurterFXClient().get_rate(base_currency="KRW", quote_currency="USD", current_date=DAY)
    assert rate.rate == Decimal("0.00075")
    assert rate.requested_date == DAY
    assert rate.rate_date == date(2024, 5, 17)
    assert rate.provider == "frankfurter:ecb"
    parsed = urlparse(calls[0][0].full_url)
    assert parsed.path == "/v2/providers/ecb/rates"
    assert parse_qs(parsed.query) == {
        "base": ["EUR"], "quotes": ["KRW,USD"], "from": ["2024-05-12"], "to": ["2024-05-19"],
    }
    assert calls[0][1] == 10.0


@pytest.mark.parametrize("payload", [
    b"[]", b"not json", b'{"error":"unavailable"}',
    b'[{"date":"2024-05-11","base":"EUR","quote":"KRW","rate":0.001}]',
    b'[{"date":"2024-05-20","base":"EUR","quote":"KRW","rate":0.001}]',
    b'[{"date":"2024-05-17","base":"USD","quote":"KRW","rate":1400}]',
    b'[{"date":"2024-05-17","base":"EUR","quote":"KRW","rate":0}]',
    b'[{"date":"2024-05-17","base":"EUR","quote":"KRW","rate":"NaN"}]',
])
def test_invalid_or_stale_fx_response_fails_without_dropping_budget(monkeypatch, payload):
    monkeypatch.setattr(
        "fashion_recommendation_v2.tools.price_client.urlopen", lambda *a, **kw: BytesIO(payload),
    )
    with pytest.raises(FXRateUnavailableError):
        PriceFXRuntime().convert(
            constraint=PriceConstraint(currency="KRW", max_amount="30000"), current_date=DAY,
        )


def test_fx_network_failure_is_explicit(monkeypatch):
    def offline(*args, **kwargs):
        raise URLError("offline")

    monkeypatch.setattr("fashion_recommendation_v2.tools.price_client.urlopen", offline)
    with pytest.raises(FXRateUnavailableError, match="offline"):
        FrankfurterFXClient().get_rate(base_currency="KRW", quote_currency="USD", current_date=DAY)


@pytest.mark.parametrize("base,quote,expected", [
    ("EUR", "USD", Decimal("1.05")), ("USD", "EUR", Decimal("1") / Decimal("1.05")),
])
def test_native_eur_leg_needs_no_separate_eur_quote(monkeypatch, base, quote, expected):
    monkeypatch.setattr(
        "fashion_recommendation_v2.tools.price_client.urlopen",
        lambda *a, **kw: BytesIO(
            b'[{"date":"2024-05-17","base":"EUR","quote":"USD","rate":1.05}]'
        ),
    )
    rate = FrankfurterFXClient().get_rate(base_currency=base, quote_currency=quote, current_date=DAY)
    assert abs(rate.rate - expected) < Decimal("1e-27")


@pytest.mark.parametrize("rate_day", ["2024-05-11", "2024-05-20"])
def test_complete_pair_outside_allowed_date_window_is_not_used(monkeypatch, rate_day):
    import json

    payload = json.dumps([
        {"date": rate_day, "base": "EUR", "quote": "KRW", "rate": 1400},
        {"date": rate_day, "base": "EUR", "quote": "USD", "rate": 1.05},
    ]).encode()
    monkeypatch.setattr(
        "fashion_recommendation_v2.tools.price_client.urlopen", lambda *a, **kw: BytesIO(payload),
    )
    with pytest.raises(FXRateUnavailableError, match="No published rate"):
        FrankfurterFXClient().get_rate(base_currency="KRW", quote_currency="USD", current_date=DAY)


def test_runtime_validates_injected_fx_snapshot():
    class WrongClient:
        def get_rate(self, **kwargs):
            return FXRateSnapshot(
                base_currency="USD", quote_currency="KRW", rate=Decimal("1400"),
                requested_date=DAY, rate_date=DAY, provider="wrong-pair",
            )

    with pytest.raises(FXRateUnavailableError):
        PriceFXRuntime(WrongClient()).convert(
            constraint=PriceConstraint(currency="KRW", max_amount="30000"), current_date=DAY,
        )


def test_price_conversion_reaches_ebay_http_filter(monkeypatch):
    from test_ebay_client import FakeHTTPResponse
    from test_ebay_client import make_client
    from fashion_recommendation_v2.tools.ebay_search import EBaySearchTool

    client = make_client()
    monkeypatch.setattr(client, "_get_access_token", lambda: "test-token")
    requests = []

    def open_request(request, **kwargs):
        requests.append(request)
        return FakeHTTPResponse({"itemSummaries": []})

    monkeypatch.setattr("fashion_recommendation_v2.tools.ebay_client.urlopen", open_request)
    runtime = PriceFXRuntime(FixedFXClient())
    original = PriceConstraint(currency="KRW", max_amount="30000")
    plan = runtime.apply(
        SearchQueryPlan(query="black trousers", category_ids=["63863"], price_constraint=original),
        runtime.convert(constraint=original, current_date=DAY),
    )
    result = EBaySearchTool(client).search(attempt_id="price-test", plan=plan, limit=5)
    assert result.success
    field_filter = parse_qs(urlparse(requests[0].full_url).query)["filter"][0]
    assert "price:[..21.42]" in field_filter
    assert "priceCurrency:USD" in field_filter


def test_ebay_rejects_unconverted_budget_and_mismatched_currency():
    from test_ebay_client import make_client
    from fashion_recommendation_v2.tools.ebay_search import EBaySearchTool

    tool = EBaySearchTool(make_client())
    original = PriceConstraint(currency="KRW", max_amount="30000")
    plan = SearchQueryPlan(query="trousers", category_ids=["63863"], price_constraint=original)
    with pytest.raises(ValueError, match="must convert"):
        tool.search(attempt_id="test", plan=plan)
    runtime = PriceFXRuntime(FixedFXClient())
    plan = runtime.apply(plan, runtime.convert(constraint=original, current_date=DAY, target_currency="EUR"))
    with pytest.raises(ValueError, match="does not match"):
        tool.search(attempt_id="test", plan=plan)
