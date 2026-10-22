"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- search_relation_observation_v0 ----

"""Advisory, Search-owned visual facts for relationship evaluation; no scores."""
import hashlib
import json
from typing import Literal
from pydantic import Field
from pydantic import model_validator
from fashion_recommendation_v2.schemas.base import StrictBaseModel
DIMENSIONS = ('color', 'pattern', 'silhouette', 'length', 'details', 'style')
Dimension = Literal['color', 'pattern', 'silhouette', 'length', 'details', 'style']
REVISION = 'search-relation-observation-v0-1'

@_preserve_function('canonical_hash', 'fashion_recommendation_v2.schemas.search.relation_observation.search_relation_observation_v0')
def canonical_hash(value):
    if hasattr(value, 'model_dump'):
        value = value.model_dump(mode='json')
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

@_preserve_class('RelationVisualFact', 'fashion_recommendation_v2.schemas.search.relation_observation.search_relation_observation_v0')
class RelationVisualFact(StrictBaseModel):
    dimension: Dimension
    status: Literal['observed', 'unknown']
    value: str | None
    evidence: str = Field(min_length=1)
    limitations: list[str]

    @model_validator(mode='after')
    def supported(self):
        if self.status == 'observed' and (not self.value or self.value.strip().lower() == 'unknown'):
            raise ValueError('Observed facts need a concrete visible value.')
        if self.status == 'unknown' and (self.value is not None or not self.limitations):
            raise ValueError('Unknown facts require null value and explicit limitations.')
        return self

@_preserve_class('RelationVisualOutput', 'fashion_recommendation_v2.schemas.search.relation_observation.search_relation_observation_v0')
class RelationVisualOutput(StrictBaseModel):
    facts: list[RelationVisualFact]

    def validate_dimensions(self, dimensions):
        ids = [f.dimension for f in self.facts]
        if len(ids) != len(set(ids)) or set(ids) != set(dimensions):
            raise ValueError('Return each requested visual dimension exactly once.')
        return self

@_preserve_class('RelationVisualInput', 'fashion_recommendation_v2.schemas.search.relation_observation.search_relation_observation_v0')
class RelationVisualInput(StrictBaseModel):
    item_id: str
    dimensions: list[Dimension]
    validation_feedback: list[str] = Field(default_factory=list)

@_preserve_class('RelationVisualObservation', 'fashion_recommendation_v2.schemas.search.relation_observation.search_relation_observation_v0')
class RelationVisualObservation(StrictBaseModel):
    revision: Literal['search-relation-observation-v0-1'] = REVISION
    source: Literal['search_image_analysis', 'image_unavailable']
    item_id: str
    image_url: str | None
    item_sha256: str
    source_analysis_sha256: str
    image_sha256: str | None
    prompt_sha256: str
    model: str | None
    requested_dimensions: list[Dimension]
    facts: list[RelationVisualFact]
    attempts: list[dict] = Field(default_factory=list)

    def validate_against(self, item, analysis):
        data = analysis.model_dump(mode='json')
        data.pop('relation_observation_v0', None)
        if self.item_id != item.item_id or self.image_url != item.image_url or self.item_sha256 != canonical_hash(item) or (self.source_analysis_sha256 != canonical_hash(data)) or (self.prompt_sha256 != RELATION_V0_PROMPT_SHA256):
            raise ValueError('Relation observation snapshot/provenance mismatch.')
        if len(self.requested_dimensions) != len(set(self.requested_dimensions)):
            raise ValueError('Duplicate requested visual dimensions.')
        if self.requested_dimensions != missing_visual_dimensions(analysis):
            raise ValueError('Supplemental dimensions differ from missing Search visual features.')
        RelationVisualOutput(facts=self.facts).validate_dimensions(self.requested_dimensions)
        if self.source == 'image_unavailable':
            if self.image_sha256 is not None or any((f.status != 'unknown' for f in self.facts)):
                raise ValueError('Unavailable images cannot produce observed facts.')
        elif not self.image_sha256 or not self.model:
            raise ValueError('Image observations require image hash and model provenance.')
        return self

@_preserve_function('missing_visual_dimensions', 'fashion_recommendation_v2.schemas.search.relation_observation.search_relation_observation_v0')
def missing_visual_dimensions(analysis):
    covered = set()
    for feature in analysis.attributes:
        if feature.value != 'unknown' and feature.image_evidence:
            dimension = {'color': 'color', 'pattern': 'pattern', 'fit': 'silhouette'}.get(feature.attribute)
            if dimension:
                covered.add(dimension)
    return [d for d in DIMENSIONS if d not in covered]
# Frozen v0 prompt identity; validated against the actual prompt in contract tests.
RELATION_V0_PROMPT_SHA256 = 'c662ae6799a6d47add686d33518af2b1692102ec9104044f85848667e8d77dcc'
