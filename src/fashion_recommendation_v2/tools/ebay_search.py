"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- ebay_search ----

from typing import Any
from typing import Literal
from typing import Protocol
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from threading import BoundedSemaphore
import re
from pydantic import Field
from fashion_recommendation_v2.schemas.base import StrictBaseModel
from fashion_recommendation_v2.schemas.common import EBayRawItem
from fashion_recommendation_v2.schemas.common import RawAspect
from fashion_recommendation_v2.schemas.common import RawMoney
from fashion_recommendation_v2.schemas.search.retrieval.search_retrieval import SearchRequestSnapshot
from fashion_recommendation_v2.schemas.search.retrieval.search_retrieval import SearchResults
from fashion_recommendation_v2.schemas.search.retrieval.search_retrieval import ItemRetrievalFailure
from fashion_recommendation_v2.schemas.search.planning.search_planning import SearchQueryPlan
from fashion_recommendation_v2.schemas.search.planning.search_planning import SearchCategoryOption

@_preserve_class('FilterLookupResult', 'fashion_recommendation_v2.tools.ebay_search')
# ============================================================
# ============================================================
# Filter Lookup Schema
class FilterLookupResult(StrictBaseModel):
    filter_name: Literal["Condition", "Size"]
    options: list[str] = Field(default_factory=list)
    query: str
    category_ids: list[str] = Field(default_factory=list)
    inspected_item_count: int = Field(ge=0)
    # Cursor uses requested limits, not the number of returned products.
    limit_used: int = Field(ge=1)
    attempted_limits: list[int] = Field(default_factory=list)
    exhausted: bool = False

@_preserve_class('EBayBrowseClient', 'fashion_recommendation_v2.tools.ebay_search')
# ============================================================
# ============================================================
# eBay Browse Client Interface
class EBayBrowseClient(Protocol):
    """
    실제 eBay HTTP Client가 따라야 하는 인터페이스.

    이후 live client 구현에서:
    - item_summary/search
    - item/{item_id}

    를 실제 eBay Browse API에 연결한다.
    """

    def search_item_summaries(self, *, query: str, category_ids: list[str], aspect_filters: dict[str, list[str] | float], limit: int) -> dict[str, Any]:
        ...

    def get_item(self, *, item_id: str) -> dict[str, Any]:
        ...

@_preserve_class('EBaySearchTool', 'fashion_recommendation_v2.tools.ebay_search')
# ============================================================
# ============================================================
# eBay Search Tool
class EBaySearchTool:
    """
    Search Agent가 사용하는 eBay Search Tool.

    담당:

    1. Filter option lookup
    2. qSearch
    3. item_id 확보
    4. 각 item_id로 getItem 호출
    5. enriched EBayRawItem 생성
    6. SearchResults 반환
    """

    def __init__(self, client: EBayBrowseClient, *, detail_workers: int=1) -> None:
        if type(detail_workers) is not int or not 1 <= detail_workers <= 5:
            raise ValueError('detail_workers must be an integer between 1 and 5.')
        self._detail_slots = BoundedSemaphore(detail_workers)
        self.detail_workers = detail_workers
        self.client = client

    @property
    def price_currency(self) -> str:
        # Legacy/fake browse clients use the existing USD default.
        return getattr(self.client, "price_currency", "USD")

    def lookup_categories(self, *, query: str, include_context: bool=False) -> list[SearchCategoryOption]:
        """필터 없는 검색 결과에서 실제 말단 카테고리 후보를 확보한다."""
        for limit in (10, 50):
            response = self.client.search_item_summaries(query=query, category_ids=[], aspect_filters={}, limit=limit)
            candidates: dict[str, SearchCategoryOption] = {}
            representatives = {}
            details = {}
            for summary in response.get("itemSummaries", []):
                names = {category["categoryId"]: category.get("categoryName", "") for category in summary.get("categories", []) if isinstance(category.get("categoryId"), str)}
                leaf_ids = [value.strip() for value in summary.get("leafCategoryIds", []) if isinstance(value, str) and value.strip()]
                title = summary.get("title", "")
                # Older/sparse responses may only expose the path in getItem.
                if not leaf_ids and summary.get("itemId"):
                    detail = self.client.get_item(item_id=summary["itemId"])
                    details[summary["itemId"]] = detail
                    path = detail.get("categoryIdPath", "")
                    if isinstance(path, str) and path.strip():
                        leaf_id = path.split("|")[-1].strip()
                        if leaf_id:
                            leaf_ids = [leaf_id]
                            names[leaf_id] = detail.get("categoryPath", "")
                            title = detail.get("title") or title
                for category_id in leaf_ids:
                    if category_id not in candidates:
                        candidates[category_id] = SearchCategoryOption(category_id=category_id, category_name=names.get(category_id) or "")
                    representatives.setdefault(category_id, summary.get("itemId"))
                    candidate = candidates[category_id]
                    if not candidate.category_name and names.get(category_id):
                        candidate.category_name = names[category_id]
                    if isinstance(title, str) and title and (title not in candidate.example_titles):
                        candidate.example_titles.append(title)
            if candidates:
                if include_context:
                    for category_id, candidate in candidates.items():
                        item_id = representatives.get(category_id)
                        if not item_id:
                            continue
                        try:
                            if item_id not in details:
                                with self._detail_slots:
                                    details[item_id] = self.client.get_item(item_id=item_id)
                            detail = details[item_id]
                            ids = detail.get("categoryIdPath", "")
                            path = detail.get("categoryPath", "")
                            # A representative can be cross-listed. Never attach
                            # another leaf's hierarchy to this candidate ID.
                            if ids and ids.split("|")[-1].strip() == category_id and path:
                                candidate.category_path = path
                                candidate.category_id_path = ids
                                candidate.gender_scope = category_gender_scope(path)
                                candidate.scope_evidence = path
                        except Exception:
                            # Explicitly unknown is preferable to a title-based guess.
                            candidate.gender_scope = 'unknown'
                return list(candidates.values())
        return []

    def lookup_filter_options(self, *, query: str, filter_name: Literal["Condition", "Size"], category_ids: list[str] | None=None, min_options: int=3, max_limit: int=50, previous_result: FilterLookupResult | None=None) -> FilterLookupResult:
        """
        최초 조회: 옵션 min_options개 확보 또는 max_limit까지 탐색한다.
        재조회: 이전 요청 limit 다음부터 새 옵션 발견 또는 max_limit까지 탐색한다.

        옵션과 조회 이력은 누적한다. 검색어/카테고리/필터가 바뀌면
        previous_result를 재사용할 수 없다.
        """
        # ========================================================
        # ========================================================
        # Filter Lookup
        if min_options < 1:
            raise ValueError("min_options must be >= 1.")
        if not 1 <= max_limit <= 50:
            raise ValueError("max_limit must be between 1 and 50.")
        category_ids = list(category_ids or [])
        if previous_result is not None:
            if previous_result.query != query or previous_result.category_ids != category_ids or previous_result.filter_name != filter_name:
                raise ValueError("Lookup cursor must match query, category_ids and filter_name.")
            if previous_result.limit_used >= max_limit:
                return previous_result.model_copy(update={"exhausted": True}, deep=True)
        limits = [limit for limit in (3, 5, 10, 20, 50) if limit <= max_limit]
        if max_limit not in limits:
            limits.append(max_limit)
        if previous_result is not None:
            limits = [limit for limit in limits if limit > previous_result.limit_used]
        discovered = list(previous_result.options) if previous_result else []
        original_options = set(discovered)
        attempted_limits = list(previous_result.attempted_limits) if previous_result else []
        for limit in limits:
            response = self.client.search_item_summaries(query=query, category_ids=category_ids, aspect_filters={}, limit=limit)
            attempted_limits.append(limit)
            summaries = response.get("itemSummaries", [])
            options = self._collect_conditions(summaries) if filter_name == "Condition" else self._collect_sizes(summaries)
            for option in options:
                if option not in discovered:
                    discovered.append(option)
            result = FilterLookupResult(filter_name=filter_name, query=query, category_ids=category_ids, options=list(discovered), inspected_item_count=len(summaries), limit_used=limit, attempted_limits=list(attempted_limits), exhausted=limit >= max_limit)
            found_options = bool(set(discovered) - original_options) if previous_result is not None else len(discovered) >= min_options
            if found_options or result.exhausted:
                return result
        raise RuntimeError("No lookup limits available.")

    def search(self, *, attempt_id: str, plan: SearchQueryPlan, limit: int=50) -> SearchResults:
        """
        SearchQueryPlan을 사용해 eBay 검색을 실행한다.

        qSearch
        ↓
        item_id 확보
        ↓
        getItem
        ↓
        enriched EBayRawItem
        ↓
        SearchResults
        """
        if limit < 1:
            raise ValueError("limit must be >= 1.")
        # Invalid plans are not transient eBay failures: fail before the retry path.
        plan.validate_for_execution()
        if plan.price_constraint is not None:
            if plan.price_conversion is None:
                raise ValueError("PriceFXRuntime must convert the price before eBay search.")
            if plan.price_conversion.fx.quote_currency != self.price_currency:
                raise ValueError("Converted price currency does not match the eBay client.")
        snapshot = SearchRequestSnapshot(query=plan.query, category_ids=plan.category_ids, aspect_filters=plan.aspect_filters)
        try:
            response = self.client.search_item_summaries(query=plan.query, category_ids=plan.category_ids, aspect_filters=plan.aspect_filters, limit=limit)
            summaries = response.get("itemSummaries", [])
            if not isinstance(summaries, list):
                raise ValueError('eBay itemSummaries must be a list.')
        except Exception as exc:
            return SearchResults(attempt_id=attempt_id, request=snapshot, items=[], returned_item_count=0, success=False, failure_stage='search', error_message=str(exc))
        items: list[EBayRawItem] = []
        failures = []

        def fetch_detail(native_order, summary):
            item_id = None
            stage = 'summary'
            try:
                item_id = summary.get("itemId")
                if not isinstance(item_id, str) or not item_id:
                    item_id = None
                    raise ValueError('Search summary has no valid itemId.')
                stage = 'get_item'
                with self._detail_slots:
                    detail = self.client.get_item(item_id=item_id)
                stage = 'build_item'
                raw_item = self._build_raw_item(native_order=native_order, summary=summary, detail=detail)
                return (raw_item, None)
            except Exception as exc:
                return (None, ItemRetrievalFailure(item_id=item_id, native_order=native_order, stage=stage, error_type=type(exc).__name__, message=str(exc) or type(exc).__name__))
        if self.detail_workers == 1 or len(summaries) <= 1:
            outcomes = [fetch_detail(order, summary) for order, summary in enumerate(summaries, start=1)]
        # ========================================================
        # ========================================================
        # Search
        else:
            # Independent contexts retain Recorder parent IDs and per-run cost state.
            # Rolling pool: a completed request frees a slot for the next item.
            with ThreadPoolExecutor(max_workers=self.detail_workers, thread_name_prefix='ebay-detail') as executor:
                futures = [executor.submit(copy_context().run, fetch_detail, order, summary) for order, summary in enumerate(summaries, start=1)]
                # Collect in marketplace order, not network completion order.
                outcomes = [future.result() for future in futures]
        for item, failure in outcomes:
            if item is not None:
                items.append(item)
            if failure is not None:
                failures.append(failure)
        all_details_failed = bool(failures) and (not items)
        return SearchResults(attempt_id=attempt_id, request=snapshot, items=items, returned_item_count=len(items), success=not all_details_failed, item_failures=failures, failure_stage='item_details' if all_details_failed else None, error_message=f'All {len(failures)} item details failed; no usable items retrieved.' if all_details_failed else None)

    @staticmethod
    def _collect_conditions(summaries: list[dict[str, Any]]) -> list[str]:
        values: list[str] = []
        for summary in summaries:
            condition = summary.get("condition")
            if isinstance(condition, str) and condition and (condition not in values):
                values.append(condition)
        return values

    def _collect_sizes(self, summaries: list[dict[str, Any]]) -> list[str]:
        values: list[str] = []
        for summary in summaries:
            item_id = summary.get("itemId")
            if not item_id:
                continue
            detail = self.client.get_item(item_id=item_id)
            size = detail.get("size")
            if isinstance(size, str) and size and (size not in values):
                values.append(size)
        return values

    # ========================================================
    # ========================================================
    # ========================================================
    # ========================================================
    # Filter Helpers
    # Raw Item Mapping
    @staticmethod
    def _build_raw_item(*, native_order: int, summary: dict[str, Any], detail: dict[str, Any]) -> EBayRawItem:
        item_id = detail.get("itemId") or summary.get("itemId")
        title = detail.get("title") or summary.get("title")
        if not item_id:
            raise ValueError("eBay item has no itemId.")
        if not title:
            raise ValueError(f'eBay item {item_id} has no title.')
        image_url = None
        detail_image = detail.get("image")
        if isinstance(detail_image, dict):
            image_url = detail_image.get("imageUrl")
        if image_url is None:
            summary_image = summary.get("image")
            if isinstance(summary_image, dict):
                image_url = summary_image.get("imageUrl")
        price_data = detail.get("price") or summary.get("price")
        price = None
        if isinstance(price_data, dict):
            value = price_data.get("value")
            currency = price_data.get("currency")
            if value is not None and currency is not None:
                price = RawMoney(value=str(value), currency=str(currency))
        localized_aspects: list[RawAspect] = []
        for aspect in detail.get("localizedAspects", []):
            if not isinstance(aspect, dict):
                continue
            name = aspect.get("name")
            value = aspect.get("value")
            if not name or value is None:
                continue
            localized_aspects.append(RawAspect(type=aspect.get("type"), name=str(name), value=str(value)))
        return EBayRawItem(native_order=native_order, item_id=str(item_id), title=str(title), category_path=detail.get("categoryPath"), category_id_path=detail.get("categoryIdPath"), image_url=image_url, item_web_url=detail.get("itemWebUrl") or summary.get("itemWebUrl"), price=price, condition=detail.get("condition") or summary.get("condition"), condition_description=detail.get("conditionDescription"), color=detail.get("color"), size=detail.get("size"), size_type=detail.get("sizeType"), material=detail.get("material"), pattern=detail.get("pattern"), brand=detail.get("brand"), short_description=detail.get("shortDescription"), localized_aspects=localized_aspects)

@_preserve_function('category_gender_scope', 'fashion_recommendation_v2.tools.ebay_search')
def category_gender_scope(path):
    """Audience from actual taxonomy ancestors, never opaque IDs or item titles."""
    parts = [part.strip().casefold().replace('’', "'") for part in re.split(r'[|>]', path or "")]
    women = any((re.match(r"^women(?:'s|s)?(?:\s|$)", part) for part in parts))
    men = any((re.match(r"^men(?:'s|s)?(?:\s|$)", part) for part in parts))
    if men and women:
        return 'all'
    return 'women' if women else 'men' if men else 'unknown'
