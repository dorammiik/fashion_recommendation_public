"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- search_item_normalization_v24 ----

"""schemas.search.item_normalization.search_item_normalization_v24: definitions relocated without semantic changes."""
from fashion_recommendation_v2.schemas.common import EBayRawItem
from pydantic import Field
from typing import Literal
from fashion_recommendation_v2.schemas.base import StrictBaseModel
from fashion_recommendation_v2.schemas.search._model_utils import _common_schema

@_preserve_class('ItemPrice', 'fashion_recommendation_v2.schemas.search.item_normalization.search_item_normalization_v24')
# ============================================================
# ============================================================
# Item Mapper Output
class ItemPrice(StrictBaseModel):
    value: float = Field(ge=0)
    currency: str

@_preserve_class('NormalizationMetadata', 'fashion_recommendation_v2.schemas.search.item_normalization.search_item_normalization_v24')
class NormalizationMetadata(StrictBaseModel):
    deterministic_fields: list[str] = Field(default_factory=list)
    llm_normalized_fields: list[str] = Field(default_factory=list)
    unresolved_fields: list[str] = Field(default_factory=list)

@_preserve_class('NormalizedItem', 'fashion_recommendation_v2.schemas.search.item_normalization.search_item_normalization_v24')
class NormalizedItem(StrictBaseModel):
    raw_metadata: EBayRawItem | None = None
    item_id: str
    title: str
    category_path: str | None = None
    category_id_path: str | None = None
    image_url: str | None = None
    item_web_url: str | None = None
    price: ItemPrice | None = None
    condition: str | None = None
    condition_description: str | None = None
    color: list[str] = Field(default_factory=list)
    size: list[str] = Field(default_factory=list)
    fit: list[str] = Field(default_factory=list)
    material: list[str] = Field(default_factory=list)
    pattern: list[str] = Field(default_factory=list)
    brand: str | None = None
    strength: list[str] = Field(default_factory=list)
    garment_care: list[str] = Field(default_factory=list)
    theme: list[str] = Field(default_factory=list)
    season: list[str] = Field(default_factory=list)
    occasion: list[str] = Field(default_factory=list)
    detail: dict[str, list[str]] = Field(default_factory=dict)
    normalization_metadata: NormalizationMetadata
CommonNormalizedItem = _common_schema('CommonNormalizedItem', NormalizedItem, [key for key in NormalizedItem.model_fields if key != 'raw_metadata'])
NormalizableFieldName = Literal["color", "size", "fit", "material", "pattern", "brand", "strength", "garment_care", "theme", "season", "occasion", "detail"]

@_preserve_class('NormalizedDetail', 'fashion_recommendation_v2.schemas.search.item_normalization.search_item_normalization_v24')
# ============================================================
# ============================================================
# LLM Normalization Result
class NormalizedDetail(StrictBaseModel):
    key: str
    values: list[str] = Field(default_factory=list)

@_preserve_class('ItemNormalizationResult', 'fashion_recommendation_v2.schemas.search.item_normalization.search_item_normalization_v24')
class ItemNormalizationResult(StrictBaseModel):
    """
    Item Mapper에서 LLM이 반환하는 정규화 결과.

    이 Schema에는 deterministic 1:1 field를 포함하지 않는다.

    LLM은 다음과 같은 semantic normalization만 담당한다.

    - color
    - size
    - fit
    - material
    - pattern
    - brand
    - strength
    - garment_care
    - theme
    - season
    - occasion
    - detail

    근거가 없는 값은 생성하지 않고
    list field는 빈 list,
    brand는 None,
    detail은 빈 list로 반환한다.
    """
    color: list[str] = Field(default_factory=list)
    size: list[str] = Field(default_factory=list)
    fit: list[str] = Field(default_factory=list)
    material: list[str] = Field(default_factory=list)
    pattern: list[str] = Field(default_factory=list)
    brand: str | None = None
    strength: list[str] = Field(default_factory=list)
    garment_care: list[str] = Field(default_factory=list)
    theme: list[str] = Field(default_factory=list)
    season: list[str] = Field(default_factory=list)
    occasion: list[str] = Field(default_factory=list)
    # ============================================================
    # ============================================================
    # Normalizable Field Names
    detail: list[NormalizedDetail] = Field(default_factory=list)

@_preserve_class('ItemMapperConfig', 'fashion_recommendation_v2.schemas.search.item_normalization.search_item_normalization_v24')
# ============================================================
# ============================================================
# Mapper Configuration
class ItemMapperConfig(StrictBaseModel):
    """
    Item Mapper 실행 설정.

    normalize_fields:
    LLM normalization 대상으로 허용할 field 목록.

    llm_enabled:
    False이면 deterministic mapping만 수행한다.
    """
    normalize_fields: list[NormalizableFieldName] = Field(default_factory=lambda: ["color", "size", "fit", "material", "pattern", "brand", "strength", "garment_care", "theme", "season", "occasion", "detail"])
    llm_enabled: bool = True
