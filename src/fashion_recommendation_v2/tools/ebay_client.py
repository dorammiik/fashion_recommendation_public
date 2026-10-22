"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- ebay_client ----

import base64
import json
import os
import time
from threading import Lock
from typing import Any
from typing import Literal
from urllib.error import HTTPError
from urllib.error import URLError
from urllib.parse import quote
from urllib.parse import urlencode
from urllib.request import Request
from urllib.request import urlopen

@_preserve_class('EBayAPIError', 'fashion_recommendation_v2.tools.ebay_client')
class EBayAPIError(RuntimeError):
    pass

@_preserve_class("EBayLiveBrowseClient", 'fashion_recommendation_v2.tools.ebay_client')
class EBayLiveBrowseClient:
    """
    실제 eBay Browse API Client.

    담당:
    - Client Credentials OAuth token 발급
    - GET /buy/browse/v1/item_summary/search
    - GET /buy/browse/v1/item/{item_id}

    EBaySearchTool의 EBayBrowseClient Protocol을 구현한다.
    """
    OAUTH_SCOPE = "https://api.ebay.com/oauth/api_scope"

    def __init__(self, *, client_id: str, client_secret: str, marketplace_id: str="EBAY_US", price_currency: str="USD", environment: Literal["production", "sandbox"]="production", timeout_seconds: float | None=20.0) -> None:
        if not client_id:
            raise ValueError("client_id must not be empty.")
        if not client_secret:
            raise ValueError("client_secret must not be empty.")
        self.client_id = client_id
        self.client_secret = client_secret
        self.marketplace_id = marketplace_id
        self.price_currency = price_currency
        self.environment = environment
        self.timeout_seconds = timeout_seconds
        if environment == "production":
            self.api_base_url = "https://api.ebay.com"
        else:
            self.api_base_url = "https://api.sandbox.ebay.com"
        self._token_lock = Lock()
        self._access_token: str | None = None
        self._access_token_expires_at: float = 0.0

    # ========================================================
    # ========================================================
    # Factory
    def set_timeout(self, seconds: float | None) -> None:
        """Set this client's HTTP limit, including None for unbounded requests."""
        self.timeout_seconds = seconds

    @classmethod
    def from_env(cls) -> "EBayLiveBrowseClient":
        client_id = os.getenv("EBAY_CLIENT_ID", "")
        client_secret = os.getenv("EBAY_CLIENT_SECRET", "")
        marketplace_id = os.getenv("EBAY_MARKETPLACE_ID", "EBAY_US")
        price_currency = os.getenv("EBAY_PRICE_CURRENCY", "USD")
        environment = os.getenv("EBAY_ENVIRONMENT", "production")
        if environment not in {"production", "sandbox"}:
            raise ValueError("EBAY_ENVIRONMENT must be 'production' or 'sandbox'.")
        return cls(client_id=client_id, client_secret=client_secret, marketplace_id=marketplace_id, price_currency=price_currency, environment=environment)

    # ========================================================
    # ========================================================
    # OAuth
    def _get_access_token(self) -> str:
        # Detail workers share one client; refresh an expired token only once.
        with self._token_lock:
            return self._get_access_token_locked()

    def _get_access_token_locked(self) -> str:
        now = time.monotonic()
        if self._access_token is not None and now < self._access_token_expires_at - 60:
            return self._access_token
        credentials = f'{self.client_id}:{self.client_secret}'.encode("utf-8")
        encoded_credentials = base64.b64encode(credentials).decode("ascii")
        body = urlencode({"grant_type": "client_credentials", "scope": self.OAUTH_SCOPE}).encode("utf-8")
        request = Request(url=f'{self.api_base_url}/identity/v1/oauth2/token', data=body, method="POST", headers={"Authorization": f'Basic {encoded_credentials}', "Content-Type": 'application/x-www-form-urlencoded'})
        # ========================================================
        # ========================================================
        # HTTP
        payload = self._execute_request(request)
        access_token = payload.get("access_token")
        expires_in = payload.get("expires_in")
        if not isinstance(access_token, str):
            raise EBayAPIError('OAuth response does not contain access_token.')
        if not isinstance(expires_in, (int, float)):
            raise EBayAPIError('OAuth response does not contain valid expires_in.')
        self._access_token = access_token
        self._access_token_expires_at = now + float(expires_in)
        return access_token

    def search_item_summaries(self, *, query: str, category_ids: list[str], aspect_filters: dict[str, list[str] | float], limit: int) -> dict[str, Any]:
        if not query.strip():
            raise ValueError("query must not be empty.")
        # 만료 60초 전부터 새 Token 사용
        if limit < 1:
            raise ValueError("limit must be >= 1.")
        params: dict[str, str | int] = {"q": query, "limit": limit}
        if category_ids:
            params["category_ids"] = ",".join(category_ids)
        # ========================================================
        # ========================================================
        # eBay Aspect Filters
        field_filters = self._build_field_filters(aspect_filters)
        # ========================================================
        # ========================================================
        # eBay Field Filters
        if field_filters:
            params["filter"] = ",".join(field_filters)
        ebay_aspect_filter = self._build_aspect_filter(category_ids=category_ids, aspect_filters=aspect_filters)
        if ebay_aspect_filter is not None:
            params["aspect_filter"] = ebay_aspect_filter
        query_string = urlencode(params)
        url = f'{self.api_base_url}/buy/browse/v1/item_summary/search?{query_string}'
        request = Request(url=url, method="GET", headers=self._auth_headers())
        return self._execute_request(request)

    # ========================================================
    # ========================================================
    # Search
    def get_item(self, *, item_id: str) -> dict[str, Any]:
        # ========================================================
        # ========================================================
        # Get Item
        if not item_id:
            raise ValueError("item_id must not be empty.")
        encoded_item_id = quote(item_id, safe="")
        url = f'{self.api_base_url}/buy/browse/v1/item/{encoded_item_id}'
        request = Request(url=url, method="GET", headers=self._auth_headers())
        return self._execute_request(request)

    def _build_field_filters(self, aspect_filters: dict[str, list[str] | float]) -> list[str]:
        filters: list[str] = []
        price_min = aspect_filters.get("PriceMin")
        price_max = aspect_filters.get("PriceMax")
        if isinstance(price_min, (int, float)) or isinstance(price_max, (int, float)):
            if isinstance(price_min, (int, float)) and isinstance(price_max, (int, float)):
                price_filter = f'price:[{price_min}..{price_max}]'
            elif isinstance(price_min, (int, float)):
                price_filter = f'price:[{price_min}]'
            else:
                price_filter = f'price:[..{price_max}]'
            filters.append(price_filter)
            filters.append(f'priceCurrency:{self.price_currency}')
        condition_values = aspect_filters.get("Condition")
        if isinstance(condition_values, list):
            condition_groups = self._normalize_conditions(condition_values)
            if condition_groups:
                joined = "|".join(condition_groups)
                filters.append(f'conditions:{{{joined}}}')
        return filters

    def _build_aspect_filter(self, *, category_ids: list[str], aspect_filters: dict[str, list[str] | float]) -> str | None:
        ignored_keys = {"Condition", "PriceMin", "PriceMax"}
        aspect_parts: list[tuple[str, list[str]]] = []
        for key, value in aspect_filters.items():
            if key in ignored_keys:
                continue
            if isinstance(value, list) and value:
                aspect_parts.append((key, value))
        if not aspect_parts:
            return None
        # eBay aspect_filter는 categoryId가 필수.
        if not category_ids:
            raise ValueError('category_ids is required when using eBay aspect filters.')
        category_id = category_ids[0]
        components = [f'categoryId:{category_id}']
        for aspect_name, values in aspect_parts:
            joined_values = "|".join(values)
            components.append(f'{aspect_name}:{{{joined_values}}}')
        return ",".join(components)

    # ========================================================
    # ========================================================
    # Condition Mapping
    @staticmethod
    def _normalize_conditions(conditions: list[str]) -> list[str]:
        """
        eBay Browse API의 broad condition filter:

        NEW
        USED
        UNSPECIFIED

        로 변환한다.
        """
        normalized: list[str] = []
        for condition in conditions:
            value = condition.strip().lower()
            if not value:
                continue
            if value == "new" or value.startswith("new ") or "new with" in value or ("new without" in value):
                result = "NEW"
            elif value == "used" or "pre-owned" in value or "preowned" in value:
                result = "USED"
            elif value == "unspecified":
                result = "UNSPECIFIED"
            else:
                continue
            if result not in normalized:
                normalized.append(result)
        return normalized

    # ========================================================
    # ========================================================
    # Headers
    def _auth_headers(self) -> dict[str, str]:
        access_token = self._get_access_token()
        return {"Authorization": f'Bearer {access_token}', "Accept": "application/json", "X-EBAY-C-MARKETPLACE-ID": self.marketplace_id}

    def _execute_request(self, request: Request) -> dict[str, Any]:
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            try:
                body = exc.read().decode("utf-8")
            except Exception:
                body = ""
            raise EBayAPIError(f'eBay HTTP {exc.code}: {body or exc.reason}') from exc
        except URLError as exc:
            raise EBayAPIError(f'eBay network error: {exc.reason}') from exc
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise EBayAPIError("eBay returned invalid JSON.") from exc
        if not isinstance(payload, dict):
            raise EBayAPIError('eBay response must be a JSON object.')
        return payload
