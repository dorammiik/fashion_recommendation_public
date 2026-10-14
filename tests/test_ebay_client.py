from __future__ import annotations
from fashion_recommendation_v2.module_compat import import_module as _role_module

import io
import json
from typing import Any
from urllib.error import HTTPError
from urllib.parse import parse_qs
from urllib.parse import urlparse
from unittest.mock import patch

import pytest

from fashion_recommendation_v2.tools.ebay_client import EBayAPIError
from fashion_recommendation_v2.tools.ebay_client import EBayLiveBrowseClient


class FakeHTTPResponse:
    def __init__(
        self,
        payload: dict[str, Any],
    ) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeHTTPResponse":
        return self

    def __exit__(
        self,
        exc_type: Any,
        exc_value: Any,
        traceback: Any,
    ) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(
            self.payload
        ).encode("utf-8")


def make_client() -> EBayLiveBrowseClient:
    return EBayLiveBrowseClient(
        client_id="test_client_id",
        client_secret="test_client_secret",
        marketplace_id="EBAY_US",
        price_currency="USD",
        environment="production",
    )


def test_get_access_token():
    client = make_client()

    fake_response = FakeHTTPResponse(
        {
            "access_token": "token_123",
            "expires_in": 7200,
        }
    )

    with patch(
        "fashion_recommendation_v2.tools.ebay_client.urlopen",
        return_value=fake_response,
    ) as mocked_urlopen:
        token = client._get_access_token()

    assert token == "token_123"
    assert mocked_urlopen.call_count == 1

    request = mocked_urlopen.call_args.args[0]

    assert request.full_url == (
        "https://api.ebay.com/"
        "identity/v1/oauth2/token"
    )

    assert request.get_method() == "POST"


def test_access_token_is_cached():
    client = make_client()

    fake_response = FakeHTTPResponse(
        {
            "access_token": "token_123",
            "expires_in": 7200,
        }
    )

    with patch(
        "fashion_recommendation_v2.tools.ebay_client.urlopen",
        return_value=fake_response,
    ) as mocked_urlopen:
        first = client._get_access_token()
        second = client._get_access_token()

    assert first == "token_123"
    assert second == "token_123"

    assert mocked_urlopen.call_count == 1


def test_search_item_summaries_builds_basic_query():
    client = make_client()

    client._access_token = "cached_token"
    client._access_token_expires_at = float("inf")

    fake_response = FakeHTTPResponse(
        {
            "itemSummaries": [],
        }
    )

    with patch(
        "fashion_recommendation_v2.tools.ebay_client.urlopen",
        return_value=fake_response,
    ) as mocked_urlopen:
        result = client.search_item_summaries(
            query="floral dress",
            category_ids=["63861"],
            aspect_filters={},
            limit=50,
        )

    assert result == {
        "itemSummaries": [],
    }

    request = mocked_urlopen.call_args.args[0]

    parsed = urlparse(
        request.full_url
    )

    params = parse_qs(
        parsed.query
    )

    assert params["q"] == [
        "floral dress"
    ]

    assert params["category_ids"] == [
        "63861"
    ]

    assert params["limit"] == [
        "50"
    ]

    assert (
        request.headers[
            "X-ebay-c-marketplace-id"
        ]
        == "EBAY_US"
    )


def test_search_builds_price_filter():
    client = make_client()

    client._access_token = "cached_token"
    client._access_token_expires_at = float("inf")

    fake_response = FakeHTTPResponse(
        {
            "itemSummaries": [],
        }
    )

    with patch(
        "fashion_recommendation_v2.tools.ebay_client.urlopen",
        return_value=fake_response,
    ) as mocked_urlopen:
        client.search_item_summaries(
            query="floral dress",
            category_ids=[],
            aspect_filters={
                "PriceMax": 80.0,
            },
            limit=50,
        )

    request = mocked_urlopen.call_args.args[0]

    params = parse_qs(
        urlparse(
            request.full_url
        ).query
    )

    filter_value = params["filter"][0]

    assert "price:[..80.0]" in filter_value
    assert "priceCurrency:USD" in filter_value


def test_search_builds_condition_filter():
    client = make_client()

    client._access_token = "cached_token"
    client._access_token_expires_at = float("inf")

    fake_response = FakeHTTPResponse(
        {
            "itemSummaries": [],
        }
    )

    with patch(
        "fashion_recommendation_v2.tools.ebay_client.urlopen",
        return_value=fake_response,
    ) as mocked_urlopen:
        client.search_item_summaries(
            query="polo shirt",
            category_ids=[],
            aspect_filters={
                "Condition": [
                    "New with tags",
                    "New without tags",
                ],
            },
            limit=50,
        )

    request = mocked_urlopen.call_args.args[0]

    params = parse_qs(
        urlparse(
            request.full_url
        ).query
    )

    filter_value = params["filter"][0]

    assert "conditions:{NEW}" in filter_value


def test_search_builds_size_aspect_filter():
    client = make_client()

    client._access_token = "cached_token"
    client._access_token_expires_at = float("inf")

    fake_response = FakeHTTPResponse(
        {
            "itemSummaries": [],
        }
    )

    with patch(
        "fashion_recommendation_v2.tools.ebay_client.urlopen",
        return_value=fake_response,
    ) as mocked_urlopen:
        client.search_item_summaries(
            query="polo shirt",
            category_ids=["57989"],
            aspect_filters={
                "Size": [
                    "M",
                    "L",
                ],
            },
            limit=50,
        )

    request = mocked_urlopen.call_args.args[0]

    params = parse_qs(
        urlparse(
            request.full_url
        ).query
    )

    aspect_filter = (
        params["aspect_filter"][0]
    )

    assert (
        "categoryId:57989"
        in aspect_filter
    )

    assert (
        "Size:{M|L}"
        in aspect_filter
    )


def test_aspect_filter_requires_category():
    client = make_client()

    client._access_token = "cached_token"
    client._access_token_expires_at = float("inf")

    with pytest.raises(
        ValueError,
        match="category_ids is required",
    ):
        client.search_item_summaries(
            query="polo shirt",
            category_ids=[],
            aspect_filters={
                "Size": ["M"],
            },
            limit=50,
        )


def test_get_item_encodes_item_id():
    client = make_client()

    client._access_token = "cached_token"
    client._access_token_expires_at = float("inf")

    fake_response = FakeHTTPResponse(
        {
            "itemId": "v1|820105175390|0",
        }
    )

    with patch(
        "fashion_recommendation_v2.tools.ebay_client.urlopen",
        return_value=fake_response,
    ) as mocked_urlopen:
        result = client.get_item(
            item_id="v1|820105175390|0"
        )

    assert result["itemId"] == (
        "v1|820105175390|0"
    )

    request = mocked_urlopen.call_args.args[0]

    assert request.full_url.endswith(
        "v1%7C820105175390%7C0"
    )


def test_normalize_conditions():
    result = (
        EBayLiveBrowseClient
        ._normalize_conditions(
            [
                "New with tags",
                "New without tags",
                "Pre-owned - Excellent",
                "Used",
            ]
        )
    )

    assert result == [
        "NEW",
        "USED",
    ]


def test_http_error_becomes_ebay_api_error():
    client = make_client()

    error = HTTPError(
        url="https://api.ebay.com/test",
        code=500,
        msg="Internal Server Error",
        hdrs=None,
        fp=io.BytesIO(
            b'{"error":"server error"}'
        ),
    )

    with patch(
        "fashion_recommendation_v2.tools.ebay_client.urlopen",
        side_effect=error,
    ):
        with pytest.raises(
            EBayAPIError,
            match="eBay HTTP 500",
        ):
            client._execute_request(
                request=object(),
            )


def test_invalid_json_becomes_ebay_api_error():
    client = make_client()

    class InvalidJSONResponse:
        def __enter__(self) -> "InvalidJSONResponse":
            return self

        def __exit__(
            self,
            exc_type: Any,
            exc_value: Any,
            traceback: Any,
        ) -> None:
            return None

        def read(self) -> bytes:
            return b"not-json"

    with patch(
        "fashion_recommendation_v2.tools.ebay_client.urlopen",
        return_value=InvalidJSONResponse(),
    ):
        with pytest.raises(
            EBayAPIError,
            match="invalid JSON",
        ):
            client._execute_request(
                request=object(),
            )