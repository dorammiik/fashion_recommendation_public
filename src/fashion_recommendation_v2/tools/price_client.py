from __future__ import annotations
from fashion_recommendation_v2.module_compat import import_module as _role_module

import json
from datetime import date
from datetime import timedelta
from decimal import Decimal
from decimal import localcontext
from typing import Protocol
from urllib.parse import urlencode
from urllib.request import Request
from urllib.request import urlopen

from fashion_recommendation_v2.schemas.price import FXRateSnapshot


class FXRateUnavailableError(RuntimeError):
    """가격 조건을 유지할 수 있는 환율을 확보하지 못했다."""


class FXClient(Protocol):
    def get_rate(
        self, *, base_currency: str, quote_currency: str, current_date: date,
    ) -> FXRateSnapshot: ...


class FrankfurterFXClient:
    """Frankfurter v2의 ECB 기준 일별 환율. API key는 필요 없다.

    https://frankfurter.dev/#rates-by-provider
    current_date 당일 또는 이전 7일 내 가장 최근 고시 환율을 선택한다.
    """

    MAX_RATE_AGE_DAYS = 7
    ENDPOINT = "https://api.frankfurter.dev/v2/providers/ecb/rates"

    def __init__(self, *, timeout: float | None = 10.0) -> None:
        self.set_timeout(timeout)

    def set_timeout(self, timeout: float | None) -> None:
        if timeout is not None and timeout <= 0:
            raise ValueError("timeout must be positive.")
        self.timeout = timeout

    def get_rate(
        self, *, base_currency: str, quote_currency: str, current_date: date,
    ) -> FXRateSnapshot:
        start = current_date - timedelta(days=self.MAX_RATE_AGE_DAYS)
        # ECB publishes against EUR. Direct KRW/USD API quotes are rounded to
        # five decimal places, losing significant digits for small rates.
        # Cross two native EUR quotes from the SAME date instead.
        quotes = sorted({base_currency, quote_currency} - {"EUR"})
        params = urlencode({
            "base": "EUR",
            "quotes": ",".join(quotes),
            "from": start.isoformat(),
            "to": current_date.isoformat(),
        })
        request = Request(
            f"{self.ENDPOINT}?{params}",
            headers={
                "Accept": "application/json",
                "User-Agent": "fashion-recommendation-v2/0.1",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                rows = json.loads(response.read(), parse_float=Decimal)
            if not isinstance(rows, list):
                raise ValueError("Expected a list of daily exchange rates.")
            daily_rates: dict[date, dict[str, Decimal]] = {}
            for row in rows:
                if row["base"] != "EUR" or row["quote"] not in quotes:
                    raise ValueError("FX response currency pair does not match the request.")
                rate_date = date.fromisoformat(row["date"])
                if not start <= rate_date <= current_date:
                    continue
                rate = Decimal(str(row["rate"]))
                if not rate.is_finite() or rate <= 0:
                    raise ValueError("FX rates must be finite and positive.")
                daily_rates.setdefault(rate_date, {"EUR": Decimal("1")})[row["quote"]] = rate
            snapshots = []
            for rate_date, rates in daily_rates.items():
                if base_currency not in rates or quote_currency not in rates:
                    continue
                with localcontext() as context:
                    context.prec = 50
                    cross_rate = rates[quote_currency] / rates[base_currency]
                snapshots.append(FXRateSnapshot(
                    base_currency=base_currency,
                    quote_currency=quote_currency,
                    rate=cross_rate,
                    requested_date=current_date,
                    rate_date=rate_date,
                    provider="frankfurter:ecb",
                ))
            if not snapshots:
                raise ValueError("No published rate within the previous 7 days.")
            return max(snapshots, key=lambda snapshot: snapshot.rate_date)
        except (OSError, ValueError, TypeError, KeyError, ArithmeticError) as exc:
            raise FXRateUnavailableError(
                f"Cannot resolve {base_currency}/{quote_currency} FX rate "
                f"as of {current_date}: {exc}"
            ) from exc
