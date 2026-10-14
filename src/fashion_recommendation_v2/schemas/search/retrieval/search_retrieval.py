"""Role-consolidated implementation; service contracts and behavior are preserved."""
from __future__ import annotations
from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function

from fashion_recommendation_v2.schemas.common import RawMoney, RawAspect, EBayRawItem as EBayRawItem_base

# ---- search_retrieval ----
"""schemas.search.retrieval.search_retrieval: definitions relocated without semantic changes."""

from pydantic import Field
from typing import Literal as Literal_base
from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_base

# ============================================================
# Shared Types
# ============================================================

AspectFilterValue = list[str] | float


# ============================================================
# eBay Search Tool Output
# ============================================================








@_preserve_class('SearchRequestSnapshot', 'fashion_recommendation_v2.schemas.search.retrieval.search_retrieval')
class SearchRequestSnapshot(StrictBaseModel_base):
    __qualname__ = 'SearchRequestSnapshot'
    query: str

    category_ids: list[str] = Field(
        default_factory=list
    )

    aspect_filters: dict[
        str,
        AspectFilterValue,
    ] = Field(
        default_factory=dict
    )


@_preserve_class('ItemRetrievalFailure', 'fashion_recommendation_v2.schemas.search.retrieval.search_retrieval')
class ItemRetrievalFailure(StrictBaseModel_base):
    __qualname__ = 'ItemRetrievalFailure'
    item_id: str | None = None
    native_order: int = Field(ge=1)
    stage: Literal_base['summary', 'get_item', 'build_item']
    error_type: str
    message: str


@_preserve_class('SearchResults', 'fashion_recommendation_v2.schemas.search.retrieval.search_retrieval')
class SearchResults(StrictBaseModel_base):
    __qualname__ = 'SearchResults'
    item_failures: list[ItemRetrievalFailure] = Field(default_factory=list)
    failure_stage: Literal_base['search', 'item_details'] | None = None
    attempt_id: str

    request: SearchRequestSnapshot

    items: list[EBayRawItem_base] = Field(
        default_factory=list
    )

    returned_item_count: int = Field(ge=0)

    success: bool

    error_message: str | None = None


# ---- search_retrieval_v26 ----
"""Marketplace identity/commerce snapshot; semantic facts live in search_analysis."""
from typing import Literal
from fashion_recommendation_v2.schemas.base import StrictBaseModel
EBayRawItem = EBayRawItem_base
from fashion_recommendation_v2.schemas.search.item_normalization.search_item_normalization import ItemPrice
from fashion_recommendation_v2.schemas.search.item_normalization.search_item_normalization import NormalizedItem


@_preserve_class('RetrievedProductV26', 'fashion_recommendation_v2.schemas.search.retrieval.search_retrieval_v26')
class RetrievedProductV26(StrictBaseModel):
    __qualname__ = 'RetrievedProductV26'
    record_version: Literal['search_product_v26']
    item_id: str
    title: str
    category_path: str | None = None
    category_id_path: str | None = None
    image_url: str | None = None
    item_web_url: str | None = None
    price: ItemPrice | None = None
    condition: str | None = None
    condition_description: str | None = None
    raw_metadata: EBayRawItem

    @classmethod
    def from_raw(cls, raw):
        fields = {key: getattr(raw, key) for key in ('item_id', 'title', 'category_path',
            'category_id_path', 'item_web_url', 'condition', 'condition_description')}
        return cls(record_version='search_product_v26', **fields, image_url=raw.image_url.strip() or None if raw.image_url else None,
            price=ItemPrice(value=float(raw.price.value), currency=raw.price.currency) if raw.price else None,
            raw_metadata=raw.model_copy(deep=True))


# Old persisted candidates are readable, but v26 creates only RetrievedProductV26.
ProductRecord = RetrievedProductV26 | NormalizedItem

from fashion_recommendation_v2.schemas.search._model_utils import _common_schema
CommonRetrievedProductV26 = _common_schema('CommonRetrievedProductV26', RetrievedProductV26,
    [key for key in RetrievedProductV26.model_fields if key != 'raw_metadata'])
