"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- item_normalization_legacy ----

from typing import Any
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import wait
from concurrent.futures import FIRST_COMPLETED
from contextvars import copy_context
from fashion_recommendation_v2.llm.base import StructuredLLM
from fashion_recommendation_v2.prompts.search.item_normalization import build_item_normalization_prompt
from fashion_recommendation_v2.schemas.search.item_normalization.search_item_normalization import ItemMapperConfig
from fashion_recommendation_v2.schemas.search.item_normalization.search_item_normalization import ItemNormalizationResult
from fashion_recommendation_v2.schemas.search.item_normalization.search_item_normalization import NormalizableFieldName
from fashion_recommendation_v2.schemas.common import EBayRawItem
from fashion_recommendation_v2.schemas.search.item_normalization.search_item_normalization import ItemPrice
from fashion_recommendation_v2.schemas.search.item_normalization.search_item_normalization import NormalizationMetadata
from fashion_recommendation_v2.schemas.search.item_normalization.search_item_normalization import NormalizedItem

@_preserve_class('ItemMapper', 'fashion_recommendation_v2.search.item_normalization_legacy')
class ItemMapper:
    """
    EBayRawItem을 NormalizedItem으로 변환한다.

    Flow:

    EBayRawItem
    ↓
    Deterministic Mapping
    ↓
    Unresolved Field Detection
    ↓
    LLM Normalization
    ↓
    NormalizationMetadata
    ↓
    NormalizedItem

    원칙:
    - 1:1 대응 가능한 값은 코드로 매핑한다.
    - semantic normalization이 필요한 필드만 LLM에 전달한다.
    - LLM은 deterministic field를 수정할 수 없다.
    - LLM은 unresolved_fields에 포함된 필드만 실제 결과에 반영된다.
    """
    DETERMINISTIC_FIELD_NAMES = ("item_id", "title", "category_path", "category_id_path", "image_url", "item_web_url", "price", "condition", "condition_description")
    NORMALIZABLE_FIELD_NAMES: tuple[NormalizableFieldName, ...] = ("color", "size", "fit", "material", "pattern", "brand", "strength", "garment_care", "theme", "season", "occasion", "detail")

    def __init__(self, *, llm: StructuredLLM, config: ItemMapperConfig | None=None, max_workers: int=4) -> None:
        if type(max_workers) is not int or max_workers < 1:
            raise ValueError("max_workers must be a positive integer")
        self.max_workers = max_workers
        self.llm = llm
        self.config = config if config is not None else ItemMapperConfig()

    def map_item(self, raw_item: EBayRawItem, *, analysis=None) -> NormalizedItem:
        """
        EBayRawItem 하나를 NormalizedItem 하나로 변환한다.
        """
        # ============================================================
        # ============================================================
        # Deterministic Mapping
        deterministic_values = self._build_deterministic_values(raw_item)
        deterministic_fields = self._collect_deterministic_fields(deterministic_values)
        initial_normalized_values = self._build_initial_normalized_values(raw_item)
        analysis_fields = []
        if analysis is not None:
            if analysis.item_id != raw_item.item_id or analysis.image_url != (raw_item.image_url.strip() or None if raw_item.image_url else None):
                raise ValueError('ItemMapper analysis belongs to a different item/image.')
            deterministic_values["image_url"] = analysis.image_url
            if initial_normalized_values["brand"] is not None:
                deterministic_fields.append("brand")
            initial_normalized_values, analysis_fields = self._integrate_analysis(initial_normalized_values, analysis)
        unresolved_fields = self._detect_unresolved_fields(initial_normalized_values)
        if analysis is not None and "detail" in self.config.normalize_fields and ("detail" not in unresolved_fields):
            unresolved_fields.append("detail")
        blocked_fields = []
        if analysis is not None:
            blocked_fields = list(dict.fromkeys((c.attribute if c.attribute in self.NORMALIZABLE_FIELD_NAMES else "detail" for c in analysis.conflicts)))
            for field in blocked_fields:
                initial_normalized_values[field] = None if field == "brand" else {} if field == "detail" else []
            unresolved_fields = [f for f in unresolved_fields if f not in blocked_fields]
        normalization_result = self._run_llm_normalization(raw_item=raw_item, unresolved_fields=unresolved_fields, **{"analysis": analysis} if analysis is not None else {})
        final_normalized_values = self._apply_normalization_result(initial_values=initial_normalized_values, result=normalization_result, unresolved_fields=unresolved_fields)
        if analysis is not None:
            for field, value in final_normalized_values.items():
                terms = [v for values in value.values() for v in values] if isinstance(value, dict) else value if isinstance(value, list) else [value]
                if any((isinstance(v, str) and (not v.strip() or v.strip().casefold() == 'unknown') for v in terms)):
                    raise ValueError(f'ItemMapper unsupported empty/unknown value: {field}')
            # Evaluated values take precedence over supplementary metadata guesses.
            final_normalized_values["detail"].update(initial_normalized_values["detail"])
        llm_normalized_fields = self._collect_llm_normalized_fields(result=normalization_result, unresolved_fields=unresolved_fields)
        remaining_unresolved_fields = self._collect_remaining_unresolved_fields(values=final_normalized_values, requested_fields=unresolved_fields)
        remaining_unresolved_fields = list(dict.fromkeys(remaining_unresolved_fields + blocked_fields))
        metadata = NormalizationMetadata(deterministic_fields=deterministic_fields, llm_normalized_fields=list(dict.fromkeys(analysis_fields + llm_normalized_fields)), unresolved_fields=remaining_unresolved_fields)
        return NormalizedItem(**deterministic_values, **final_normalized_values, normalization_metadata=metadata, **{"raw_metadata": raw_item.model_copy(deep=True)} if analysis is not None else {})

    @staticmethod
    def _integrate_analysis(values, analysis):
        """Use validated evaluation attributes as authoritative semantic values.

        Unknown observations never become product values. Non-common attributes
        are retained under detail; source/evaluation evidence stays in the trace.
        """
        values = {**values, "detail": dict(values["detail"])}
        supplied = []
        for feature in analysis.known_attributes:
            value = feature.value
            if value == 'unknown':
                continue
            if not (feature.evidence_fields or feature.image_evidence):
                raise ValueError('ItemMapper requires evidence for evaluated attributes.')
            if feature.attribute == "detail":
                values["detail"][value.key] = list(value.values)
                supplied.append("detail")
            elif feature.attribute in values and feature.attribute != "brand":
                terms = value if isinstance(value, list) else [value]
                values[feature.attribute] = list(dict.fromkeys(terms))
                supplied.append(feature.attribute)
            else:
                key = 'product_type' if feature.attribute == 'category' else feature.attribute
                values["detail"][key] = list(value) if isinstance(value, list) else [value]
                supplied.append("detail")
        # detail still needs normalization of other raw aspects. Merge it later.
        return (values, list(dict.fromkeys(supplied)))

    def map_items(self, raw_items: list[EBayRawItem]) -> list[NormalizedItem]:
        """Normalize up to max_workers items concurrently, returning input order.

        Injected LLM adapters must support concurrent generate calls, or use
        max_workers=1. Each task inherits the caller's cost-report context.
        On failure, stop submitting work and drain in-flight calls before raising
        so their usage is captured before the enclosing report is finalized.
        """
        if self.max_workers == 1 or len(raw_items) <= 1:
            return [self.map_item(item) for item in raw_items]
        results = [None] * len(raw_items)
        pending = {}
        next_index = 0
        with ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix='item-normalization') as pool:

            # ============================================================
            # ============================================================
            # Public
            def submit(index):
                future = pool.submit(copy_context().run, self.map_item, raw_items[index])
                pending[future] = index
            try:
                while next_index < min(self.max_workers, len(raw_items)):
                    submit(next_index)
                    next_index += 1
                while pending:
                    done, _ = wait(pending, return_when=FIRST_COMPLETED)
                    # Check all finished calls before allowing more paid work.
                    for future in done:
                        results[pending.pop(future)] = future.result()
                    while next_index < len(raw_items) and len(pending) < self.max_workers:
                        submit(next_index)
                        next_index += 1
            except BaseException:
                for future in pending:
                    future.cancel()
                raise
        return results

    def _build_deterministic_values(self, raw_item: EBayRawItem) -> dict[str, Any]:
        """
        LLM 판단이 필요 없는 1:1 field를 코드로 매핑한다.
        """
        price = None
        if raw_item.price is not None:
            try:
                price_value = float(raw_item.price.value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f'EBayRawItem.price.value must be convertible to float. item_id={raw_item.item_id}, value={raw_item.price.value!r}') from exc
            price = ItemPrice(value=price_value, currency=raw_item.price.currency)
        return {"item_id": raw_item.item_id, "title": raw_item.title, "category_path": raw_item.category_path, "category_id_path": raw_item.category_id_path, "image_url": raw_item.image_url, "item_web_url": raw_item.item_web_url, "price": price, "condition": raw_item.condition, "condition_description": raw_item.condition_description}

    @staticmethod
    def _collect_deterministic_fields(values: dict[str, Any]) -> list[str]:
        """
        실제 값이 존재하는 deterministic field만 metadata에 기록한다.

        item_id / title은 schema상 항상 존재한다.
        optional field는 None이면 기록하지 않는다.
        """
        return [field_name for field_name, value in values.items() if value is not None]

    @staticmethod
    def _build_initial_normalized_values(raw_item: EBayRawItem) -> dict[str, Any]:
        """
        LLM normalization 전에 확정 가능한 normalized field를 준비한다.

        brand는 dedicated raw brand가 명확할 경우
        1:1 deterministic 성격으로 우선 보존한다.

        그 외 color / size / material / pattern 등은 raw dedicated
        field가 있어도 semantic normalization 대상이므로 여기서
        직접 최종값으로 확정하지 않는다.
        """
        return {"color": [], "size": [], "fit": [], "material": [], "pattern": [], "brand": raw_item.brand.strip() if isinstance(raw_item.brand, str) and raw_item.brand.strip() else None, "strength": [], "garment_care": [], "theme": [], "season": [], "occasion": [], "detail": {}}

    def _detect_unresolved_fields(self, initial_values: dict[str, Any]) -> list[NormalizableFieldName]:
        """
        config에서 허용된 normalize field 중
        아직 값이 확정되지 않은 field를 LLM 대상으로 선정한다.

        brand는 raw brand가 이미 존재하면 LLM을 호출하지 않는다.
        """
        unresolved: list[NormalizableFieldName] = []
        allowed_fields = set(self.config.normalize_fields)
        for field_name in self.NORMALIZABLE_FIELD_NAMES:
            if field_name not in allowed_fields:
                continue
            value = initial_values[field_name]
            if self._is_empty_value(value):
                unresolved.append(field_name)
        return unresolved

    def _run_llm_normalization(self, *, raw_item: EBayRawItem, unresolved_fields: list[NormalizableFieldName], analysis=None) -> ItemNormalizationResult:
        """
        필요한 field가 있을 때만 LLM을 호출한다.

        llm_enabled=False이거나 unresolved field가 없으면
        빈 ItemNormalizationResult를 반환한다.
        """
        if not self.config.llm_enabled or not unresolved_fields:
            # ============================================================
            # ============================================================
            # LLM
            return ItemNormalizationResult()
        prompt = build_item_normalization_prompt(raw_item=raw_item.model_dump(mode="json"), unresolved_fields=list(unresolved_fields))
        if analysis is not None:
            from fashion_recommendation_v2.prompts.search.item_normalization import evaluated_mapping_prompt
            prompt = evaluated_mapping_prompt(prompt, analysis.model_dump(mode="json"))
        result = self.llm.generate(system_prompt=prompt, user_input=raw_item, output_schema=ItemNormalizationResult, **{'timeout_seconds': 30, 'failure_stage': 'item_mapping'} if analysis is not None else {})
        return ItemNormalizationResult.model_validate(result.model_dump())

    @staticmethod
    def _apply_normalization_result(*, initial_values: dict[str, Any], result: ItemNormalizationResult, unresolved_fields: list[NormalizableFieldName]) -> dict[str, Any]:
        """
        요청한 unresolved field만 반영한다.

        ItemNormalizationResult.detail은
        Structured Output 호환성을 위해 list 형태이고,
        최종 NormalizedItem.detail에서는 dict 형태로 변환한다.
        """
        final_values = dict(initial_values)
        result_values = result.model_dump()
        for field_name in unresolved_fields:
            if field_name == "detail":
                final_values["detail"] = {detail["key"]: detail["values"] for detail in result_values["detail"] if detail["key"] and detail["values"]}
                continue
            final_values[field_name] = result_values[field_name]
        return final_values

    def _collect_llm_normalized_fields(self, *, result: ItemNormalizationResult, unresolved_fields: list[NormalizableFieldName]) -> list[str]:
        """
        실제 LLM이 요청받았고,
        유효한 값을 반환한 field만 기록한다.
        """
        if not self.config.llm_enabled:
            return []
        result_values = result.model_dump()
        normalized_fields: list[str] = []
        # ============================================================
        # ============================================================
        # Unresolved Detection
        for field_name in unresolved_fields:
            value = result_values[field_name]
            if not self._is_empty_value(value):
                normalized_fields.append(field_name)
        # ============================================================
        # ============================================================
        # Metadata
        return normalized_fields

    def _collect_remaining_unresolved_fields(self, *, values: dict[str, Any], requested_fields: list[NormalizableFieldName]) -> list[str]:
        """
        LLM normalization 이후에도 비어 있는 요청 field를 기록한다.
        """
        return [field_name for field_name in requested_fields if self._is_empty_value(values[field_name])]

    # ============================================================
    # ============================================================
    # ============================================================
    # ============================================================
    # ============================================================
    # ============================================================
    # Apply LLM Result
    # Helpers
    # Initial Normalized Values
    @staticmethod
    def _is_empty_value(value: Any) -> bool:
        """
        Normalization 관점의 unresolved 여부 판단.
        """
        if value is None:
            return True
        if isinstance(value, str):
            return not value.strip()
        if isinstance(value, (list, dict)):
            return len(value) == 0
        return False
