"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- price ----

import re
from datetime import date
from decimal import Decimal
from typing import Self
from pydantic import ConfigDict
from pydantic import Field
from pydantic import model_validator
from fashion_recommendation_v2.schemas.base import StrictBaseModel

@_preserve_class('PriceConstraint', 'fashion_recommendation_v2.schemas.price')
class PriceConstraint(StrictBaseModel):
    """사용자 예산. LLM은 원래 통화와 금액만 추출하며 환산하지 않는다."""
    model_config = ConfigDict(frozen=True)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    min_amount: str | None = None
    max_amount: str | None = None

    @model_validator(mode="after")
    def validate_amounts(self) -> Self:
        amounts = []
        for value in (self.min_amount, self.max_amount):
            if value is None:
                amounts.append(None)
                continue
            # Decimal strings keep the original amount exact across JSON/LLM boundaries.
            if not re.fullmatch(r"[0-9]{1,15}(?:\.[0-9]{1,8})?", value):
                raise ValueError("Price amounts must be nonnegative decimal strings.")
            amounts.append(Decimal(value))
        lower, upper = amounts
        if lower is None and upper is None:
            raise ValueError("At least one price bound is required.")
        if lower is not None and upper is not None and (lower > upper):
            raise ValueError("min_amount cannot exceed max_amount.")
        return self

@_preserve_class('FXRateSnapshot', 'fashion_recommendation_v2.schemas.price')
class FXRateSnapshot(StrictBaseModel):
    """1 base_currency = rate quote_currency. 조회일과 실제 고시일을 구분한다."""
    model_config = ConfigDict(frozen=True)
    base_currency: str = Field(pattern=r"^[A-Z]{3}$")
    quote_currency: str = Field(pattern=r"^[A-Z]{3}$")
    rate: Decimal = Field(gt=0, allow_inf_nan=False)
    requested_date: date
    rate_date: date
    provider: str

    @model_validator(mode="after")
    def reject_future_rate(self) -> Self:
        if self.rate_date > self.requested_date:
            raise ValueError("rate_date cannot be later than requested_date.")
        return self

@_preserve_class('PriceConversion', 'fashion_recommendation_v2.schemas.price')
class PriceConversion(StrictBaseModel):
    """한 SearchRunner 실행 동안 재사용하는 예산/환율/환산 결과."""
    model_config = ConfigDict(frozen=True)
    original: PriceConstraint
    fx: FXRateSnapshot
    min_amount: Decimal | None = None
    max_amount: Decimal | None = None
