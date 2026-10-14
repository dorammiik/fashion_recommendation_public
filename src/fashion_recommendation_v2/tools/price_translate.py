from __future__ import annotations
from fashion_recommendation_v2.module_compat import import_module as _role_module

from datetime import date
from decimal import Decimal
from decimal import ROUND_CEILING
from decimal import ROUND_FLOOR
from decimal import localcontext

from fashion_recommendation_v2.schemas.price import FXRateSnapshot
from fashion_recommendation_v2.schemas.price import PriceConstraint
from fashion_recommendation_v2.schemas.price import PriceConversion
from fashion_recommendation_v2.schemas.search.planning.search_planning import SearchQueryPlan
from fashion_recommendation_v2.tools.price_client import FXClient
from fashion_recommendation_v2.tools.price_client import FXRateUnavailableError
from fashion_recommendation_v2.tools.price_client import FrankfurterFXClient


class PriceFXRuntime:
    """환율 조회와 Decimal 환산. LLM이나 검색 전략에 의존하지 않는다."""

    # Supported eBay price currencies; unknown minor units must not be guessed.
    MINOR_UNITS = {
        "USD": 2, "EUR": 2, "GBP": 2, "CAD": 2, "AUD": 2,
        "CHF": 2, "HKD": 2, "SGD": 2, "NZD": 2,
        "KRW": 0, "JPY": 0,
    }

    def __init__(self, fx_client: FXClient | None = None) -> None:
        self.fx_client = fx_client if fx_client is not None else FrankfurterFXClient()

    def convert(
        self, *, constraint: PriceConstraint, current_date: date,
        target_currency: str = "USD",
    ) -> PriceConversion:
        if target_currency not in self.MINOR_UNITS:
            raise ValueError(f"Unsupported target price currency: {target_currency}")
        if constraint.currency == target_currency:
            fx = FXRateSnapshot(
                base_currency=constraint.currency, quote_currency=target_currency,
                rate=Decimal("1"), requested_date=current_date,
                rate_date=current_date, provider="identity",
            )
        else:
            fx = self.fx_client.get_rate(
                base_currency=constraint.currency, quote_currency=target_currency,
                current_date=current_date,
            )
        if (
            fx.base_currency != constraint.currency
            or fx.quote_currency != target_currency
            or fx.requested_date != current_date
            or not 0 <= (current_date - fx.rate_date).days <= 7
        ):
            raise FXRateUnavailableError("FX snapshot does not match the requested currency/date.")

        unit = Decimal(1).scaleb(-self.MINOR_UNITS[target_currency])
        with localcontext() as context:
            context.prec = 50
            lower = (
                (Decimal(constraint.min_amount) * fx.rate).quantize(unit, rounding=ROUND_CEILING)
                if constraint.min_amount is not None else None
            )
            upper = (
                (Decimal(constraint.max_amount) * fx.rate).quantize(unit, rounding=ROUND_FLOOR)
                if constraint.max_amount is not None else None
            )
        if lower is not None and upper is not None and lower > upper:
            raise ValueError("No representable target price remains after currency rounding.")
        return PriceConversion(original=constraint, fx=fx, min_amount=lower, max_amount=upper)

    @staticmethod
    def apply(
        plan: SearchQueryPlan, conversion: PriceConversion | None,
    ) -> SearchQueryPlan:
        """원본 계획은 보존하고 이미 환산된 동일 예산을 실행 계획에 적용한다."""
        completed = plan.model_copy(deep=True)
        if conversion is None:
            if completed.price_constraint is not None:
                raise ValueError("A price constraint requires an FX conversion before execution.")
            return completed
        completed.price_constraint = conversion.original
        completed.price_conversion = conversion
        for field, amount in (
            ("PriceMin", conversion.min_amount), ("PriceMax", conversion.max_amount),
        ):
            completed.aspect_filters.pop(field, None)
            if amount is not None:
                # Existing eBay filter schema accepts floats; calculate/round in Decimal first.
                value = float(amount)
                if Decimal(str(value)) != amount:
                    raise ValueError("Converted price cannot be represented by the eBay filter schema.")
                completed.aspect_filters[field] = value
        return completed


# Shared deterministic price admission/Ranking policy.
import math
from fashion_recommendation_v2.schemas.search.retrieval.search_retrieval import ProductRecord
from fashion_recommendation_v2.schemas.product_evidence import HardConstraintAssessment
def price_gate(item: ProductRecord, constraint: PriceConstraint, conversion: PriceConversion | None):
    price = item.price
    if price is None or not math.isfinite(price.value):
        return 'unknown', '상품 가격이 없거나 유효하지 않음.'
    amount = Decimal(str(price.value))
    lower, upper = constraint.min_amount, constraint.max_amount
    if price.currency != constraint.currency:
        if (conversion is None or conversion.original != constraint
                or conversion.fx.base_currency != constraint.currency
                or conversion.fx.quote_currency != price.currency):
            return 'unknown', '공유 환율로 상품 통화와 요청 통화를 비교할 수 없음.'
        lower, upper = conversion.min_amount, conversion.max_amount
        if ((constraint.min_amount is not None and lower is None)
                or (constraint.max_amount is not None and upper is None)):
            return 'unknown', '환산 예산의 경계값이 누락됨.'
    met = (lower is None or amount >= Decimal(lower)) and (upper is None or amount <= Decimal(upper))
    return ('met' if met else 'unmet'), f'상품 가격 {amount} {price.currency}; 허용 범위 {lower}~{upper} (배송비 제외).'


def filter_requirement(item: ProductRecord, requirement,
                       conversion: PriceConversion | None) -> HardConstraintAssessment:
    if not isinstance(requirement.value, PriceConstraint):
        raise ValueError("Semantic requirements must be assessed by RankingBrain.")
    status, evidence = price_gate(item, requirement.value, conversion)
    return HardConstraintAssessment(requirement_id=requirement.requirement_id, status=status,
                                    evidence_fields=['price'] if item.price is not None else [], evidence=[evidence])
