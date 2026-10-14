"""Code-composed Search query and provenance; not a new model response contract."""
from fashion_recommendation_v2.module_compat import import_module as _role_module
from typing import Any
from typing import Literal
from pydantic import Field
from pydantic import model_validator
from fashion_recommendation_v2.schemas.base import StrictBaseModel
from fashion_recommendation_v2.schemas.relation_intent import RelationIntent


class SearchQuerySegment(StrictBaseModel):
    role: Literal['user', 'anchor', 'stylist']
    text: str = Field(min_length=1)
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    source_refs: list[str] = Field(min_length=1)


class SearchQueryComposition(StrictBaseModel):
    orchestrator_version: Literal['v1'] = 'v1'
    effective_query: str = Field(min_length=1)
    retained_user_query: str = Field(min_length=1)
    relation_intent: RelationIntent
    segments: list[SearchQuerySegment] = Field(min_length=1)
    anchor_evidence: dict[str, Any]
    resolved_state_ids: list[str]

    @model_validator(mode='after')
    def consistent_segments(self):
        position = 0
        for segment in self.segments:
            if (segment.start != position or segment.end != segment.start + len(segment.text)
                    or self.effective_query[segment.start:segment.end] != segment.text):
                raise ValueError('Composition spans must reproduce the exact effective_query.')
            position = segment.end + 1  # A single newline separates complete source segments.
        if '\n'.join(s.text for s in self.segments) != self.effective_query:
            raise ValueError('Composition cannot contain unattributed text.')
        if self.segments[0].role != 'user' or self.segments[0].text != self.retained_user_query:
            raise ValueError('Composition must retain the unmodified projected request first.')
        if sum(s.role == 'user' for s in self.segments) != 1:
            raise ValueError('Only the retained request is user-authored.')
        return self
