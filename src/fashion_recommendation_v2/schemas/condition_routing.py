"""Request scoring ownership, separate from product eligibility contracts."""
from fashion_recommendation_v2.module_compat import import_module as _role_module
from typing import Literal
from pydantic import Field
from pydantic import model_validator
from pydantic import model_serializer
from fashion_recommendation_v2.schemas.base import StrictBaseModel
from fashion_recommendation_v2.schemas.relation_intent import RelationIntent
from fashion_recommendation_v2.schemas.stylist_condition_policy import StylistPolicyV47


class RelationCondition(StrictBaseModel):
    requirement_id: str = Field(pattern=r'^[a-zA-Z][a-zA-Z0-9_]{0,79}$')
    intent: RelationIntent
    target: Literal['search_target']
    source_text: str = Field(min_length=1)


class ConditionAssignment(StrictBaseModel):
    requirement_id: str
    owner: Literal['relation', 'ranking']


# Shared source-to-owner contract; scope/kind/product attribute never select owner.
def product_condition_owner(source):
    return 'relation' if source == 'reference' else 'ranking'


def fixed_condition_owners(conditions, relation_conditions=()):
    pairs = [(c.requirement_id, product_condition_owner(c.source))
             for c in conditions if c.role == 'target']
    pairs += [(c.requirement_id, 'relation') for c in relation_conditions]
    owners = dict(pairs)
    if len(owners) != len(pairs):
        raise ValueError('Duplicate product/relation condition IDs.')
    return owners


class ConditionRoutingV37(StrictBaseModel):
    stylist_policy_v47: StylistPolicyV47 | None = None
    version: Literal['v37'] = 'v37'
    relation_conditions: list[RelationCondition]
    assignments: list[ConditionAssignment]
    relative_requirement_ids: list[str] = Field(default_factory=list)
    anchor_comparison: dict = Field(default_factory=dict)

    @model_serializer(mode='wrap')
    def serialize_policy(self, handler):
        data = handler(self)
        if self.stylist_policy_v47 is None:
            data.pop('stylist_policy_v47', None)
        return data

    @model_validator(mode='after')
    def unique_ids(self):
        ids = [r.requirement_id for r in self.assignments]
        relations = [r.requirement_id for r in self.relation_conditions]
        if len(ids) != len(set(ids)) or len(relations) != len(set(relations)):
            raise ValueError('Duplicate condition routing IDs.')
        owners = {r.requirement_id: r.owner for r in self.assignments}
        if any(owners.get(rid) != 'relation' for rid in relations):
            raise ValueError('Every relation clause must have Relation ownership.')
        if len(set(self.relative_requirement_ids)) != len(self.relative_requirement_ids) or not set(self.relative_requirement_ids) <= set(ids) - set(relations):
            raise ValueError('Relative comparisons must reference unique product conditions.')
        return self
