"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- search_requirements_legacy ----

"""schemas.search.requirements.search_requirements_legacy: definitions relocated without semantic changes."""
from fashion_recommendation_v2.schemas.search.requirements.search_requirements_context import AudienceContextV1 as AudienceContextV1_legacy
from fashion_recommendation_v2.schemas.search.requirements.search_requirements_context import AudienceDecisionV1
from fashion_recommendation_v2.schemas.search.requirements.search_requirements_context import ContextAudienceRequirementV1 as ContextAudienceRequirementV1_legacy
from fashion_recommendation_v2.schemas.search.requirements.search_requirements_context import ContextGenderDiversityPolicyV1 as ContextGenderDiversityPolicyV1_legacy
from pydantic.json_schema import SkipJsonSchema as SkipJsonSchema_legacy
from pydantic import Field as Field_legacy
from typing import Literal as Literal_legacy
from typing import Annotated as Annotated_legacy
from fashion_recommendation_v2.schemas.search.retrieval.search_retrieval import ProductRecord
from fashion_recommendation_v2.schemas.product_evidence import ConditionDefinitionV26
from fashion_recommendation_v2.schemas.preference_profile import PreferenceProfile
from fashion_recommendation_v2.schemas.price import PriceConstraint as PriceConstraint_legacy
from fashion_recommendation_v2.schemas.relation_intent import RelationIntent as RelationIntent_legacy
from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_legacy
from fashion_recommendation_v2.schemas.stylist import StylistResultV3_v3 as StylistResultV3_legacy
from fashion_recommendation_v2.schemas.stylist import StylistConditionProvenanceV3_v3 as StylistConditionProvenanceV3_legacy
from fashion_recommendation_v2.schemas.stylist import StylistResultV4_v4 as StylistResultV4_legacy
from fashion_recommendation_v2.schemas.stylist import StylistConditionProvenanceV4_v4 as StylistConditionProvenanceV4_legacy
from fashion_recommendation_v2.schemas.stylist import StylistResultV5_v5 as StylistResultV5_legacy
from fashion_recommendation_v2.schemas.stylist import StylistConditionProvenanceV5_v5 as StylistConditionProvenanceV5_legacy
from fashion_recommendation_v2.schemas.stylist import StylistResultV6 as StylistResultV6_legacy
from fashion_recommendation_v2.schemas.stylist import StylistConditionProvenanceV6 as StylistConditionProvenanceV6_legacy
from fashion_recommendation_v2.schemas.stylist import StylistResultV7_stylist_v7 as StylistResultV7_search_requirements_legacy
from fashion_recommendation_v2.schemas.stylist import StylistConditionProvenanceV7_stylist_v7 as StylistConditionProvenanceV7_search_requirements_legacy
from fashion_recommendation_v2.schemas.stylist import StylistResultV8_stylist_v8 as StylistResultV8_search_requirements_legacy
from fashion_recommendation_v2.schemas.stylist import StylistConditionProvenanceV8_stylist_v8 as StylistConditionProvenanceV8_search_requirements_legacy
from fashion_recommendation_v2.schemas.stylist import StylistResultV2_v2 as StylistResultV2_legacy
from fashion_recommendation_v2.schemas.stylist import StylistConditionProvenanceV2_v2 as StylistConditionProvenanceV2_legacy
from fashion_recommendation_v2.schemas.stylist import StylistDetailValue_base as StylistDetailValue_legacy
from fashion_recommendation_v2.schemas.stylist import StylistResult_base as StylistResult_legacy
from datetime import date
from pydantic import model_serializer
from pydantic import model_validator as model_validator_legacy
from fashion_recommendation_v2.schemas.search.requirements.search_requirements_context import validate_audience_requirements

@_preserve_class('SimilarityReference', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_legacy')
# ============================================================
# ============================================================
# Search Agent Input
class SimilarityReference(StrictBaseModel_legacy):
    """Known product facts, separate from the latest user's explicit conditions."""
    item_id: str = Field_legacy(min_length=1)
    user_query: str = Field_legacy(min_length=1)
    attributes: dict[str, list[str]]

    @classmethod
    def from_item(cls, item: ProductRecord, user_query: str, search_analysis=None):
        from fashion_recommendation_v2.search.evidence_projection import semantic_values
        from fashion_recommendation_v2.search.evidence_projection import validate_analysis_identity
        validate_analysis_identity(item, search_analysis)
        if search_analysis is not None:
            attributes = semantic_values(search_analysis)
            attributes.update(title=[item.title])
            if item.category_path:
                attributes['category_path'] = [item.category_path]
            return cls(item_id=item.item_id, user_query=user_query, attributes=attributes)
        # Only normalized product facts, never price, prior search requirements,
        # ranking scores, raw marketplace payloads or recommendation reasons.
        attributes = {}
        for name in ('title', 'category_path', 'color', 'pattern', 'fit', 'material', 'size', 'brand', 'season', 'occasion', 'theme', 'garment_care'):
            value = getattr(item, name)
            if value:
                attributes[name] = list(value) if isinstance(value, list) else [value]
        attributes.update({'detail.' + key: list(values) for key, values in item.detail.items()})
        attributes = {key: [value for value in values if value.strip() and value.strip().lower() not in {'unknown', 'n/a', 'unspecified'}] for key, values in attributes.items()}
        return cls(item_id=item.item_id, user_query=user_query, attributes={key: values for key, values in attributes.items() if values})

@_preserve_class('SearchAgentInput', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_legacy')
class SearchAgentInput_legacy(StrictBaseModel_legacy):
    """Orchestrator supplies the searchable request and resolved interpretations.

    The general orchestrator removes omitted conditions from user_query/goal and
    projects StylistResult to resolved IDs only, preserving source excerpts.
    Search does not receive or decide omission reasons. Legacy smoke callers may
    still exercise their explicit partial-interpretation continue policy.
    """
    request_id: str
    user_query: str
    goal: str
    current_date: date
    stylist_resolution: SkipJsonSchema_legacy[StylistResultV8_search_requirements_legacy | StylistResultV7_search_requirements_legacy | StylistResultV6_legacy | StylistResultV5_legacy | StylistResultV4_legacy | StylistResultV3_legacy | StylistResultV2_legacy] | StylistResult_legacy | None = Field_legacy(default=None, json_schema_extra=lambda s: s.pop('title', None))
    preference_profile: PreferenceProfile | None = None
    similarity_reference: SimilarityReference | None = None
    audience_context_v1: AudienceContextV1_legacy | None = None
    # Accept legacy input artifacts, but never send evaluation metadata to Search LLMs.
    relation_intent: RelationIntent_legacy | None = Field_legacy(default=None, exclude=True)
    relation_anchor: ProductRecord | None = Field_legacy(default=None, exclude=True)
    requested_count: int = Field_legacy(ge=1)

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema, handler):
        schema = handler.resolve_ref_schema(handler(core_schema))
        # Runtime supports the explicit v49 transport extension. Historical LLM
        # schemas keep their original Stylist field presentation and contracts.
        for key in ('stylist_resolution', 'original_stylist_resolution'):
            schema.get('properties', {}).get(key, {}).pop('title', None)
        return schema

    @model_serializer(mode='wrap')
    def serialize_context(self, handler):
        data = handler(self)
        if self.similarity_reference is None:
            data.pop('similarity_reference', None)
        if self.audience_context_v1 is None:
            data.pop('audience_context_v1', None)
        return data

    @model_validator_legacy(mode="after")
    def validate_stylist_source(self):
        if self.stylist_resolution is not None:
            for entry in self.stylist_resolution.interpretations:
                if entry.source_text is not None and entry.source_text not in self.user_query:
                    raise ValueError("Stylist source_text must occur in user_query.")
        return self

@_preserve_class('ResolvedRequirement', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_legacy')
class ResolvedRequirement_legacy(StrictBaseModel_legacy):
    """Original intent, independent of the attributes selected for a query."""
    requirement_id: str = Field_legacy(min_length=1)
    attribute: str = Field_legacy(min_length=1)
    value: str | list[str] | PriceConstraint_legacy | StylistDetailValue_legacy
    kind: Literal_legacy["hard", "soft"]
    source: Literal_legacy["user", "stylist", "reference"]
    source_text: Annotated_legacy[str, Field_legacy(min_length=1)] | SkipJsonSchema_legacy[None]
    stylist_provenance: SkipJsonSchema_legacy[StylistConditionProvenanceV8_search_requirements_legacy | StylistConditionProvenanceV7_search_requirements_legacy | StylistConditionProvenanceV6_legacy | StylistConditionProvenanceV5_legacy | StylistConditionProvenanceV4_legacy | StylistConditionProvenanceV3_legacy | StylistConditionProvenanceV2_legacy | None] = None
    evaluation_scope: Literal_legacy['search', 'item'] | None = None
    unrestricted: bool = False

    @model_serializer(mode='wrap')
    def serialize_provenance(self, handler):
        data = handler(self)
        if self.stylist_provenance is None:
            data.pop('stylist_provenance', None)
        return data

    @model_validator_legacy(mode="after")
    def validate_value(self):
        if self.stylist_provenance is not None:
            if self.source != "stylist" or self.kind != "soft":
                raise ValueError('Stylist provenance requires a soft Stylist condition.')
            if (self.stylist_provenance.origin == 'preference') != (self.source_text is None):
                raise ValueError('Only preference-only Stylist conditions have null source_text.')
        elif self.source_text is None:
            raise ValueError('Legacy/user/reference conditions require source_text.')
        if self.source == "reference" and (self.kind != "soft" or self.unrestricted):
            raise ValueError('Inherited reference attributes must be soft, restricted preferences.')
        if self.attribute == "price":
            if not isinstance(self.value, PriceConstraint_legacy) or self.kind != "hard":
                raise ValueError("price requires a hard condition with a PriceConstraint value.")
        elif isinstance(self.value, PriceConstraint_legacy):
            raise ValueError("PriceConstraint values require attribute='price'.")
        elif isinstance(self.value, StylistDetailValue_legacy):
            if self.attribute != "detail":
                raise ValueError("StylistDetailValue requires attribute='detail'.")
        elif isinstance(self.value, str):
            if not self.value.strip():
                raise ValueError("Requirement value cannot be empty.")
        elif not self.value or any((not value.strip() for value in self.value)):
            raise ValueError("Requirement alternatives cannot be empty.")
        return self

@_preserve_class('RequirementsExtraction', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_legacy')
class RequirementsExtraction(StrictBaseModel_legacy):
    """LLM output produced before any query or marketplace lookup."""
    requirements: list[ResolvedRequirement_legacy]

    @model_validator_legacy(mode="after")
    def validate_requirements(self):
        ids = [entry.requirement_id for entry in self.requirements]
        if len(ids) != len(set(ids)):
            raise ValueError("requirement_id must be unique.")
        if sum((entry.attribute == "price" for entry in self.requirements)) > 1:
            raise ValueError("Combine price bounds into one price requirement.")
        return self

    @property
    def price_constraint(self) -> PriceConstraint_legacy | None:
        return next((entry.value for entry in self.requirements if isinstance(entry.value, PriceConstraint_legacy)), None)

@_preserve_class('GenderDiversityPolicy', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_legacy')
class GenderDiversityPolicy_legacy(StrictBaseModel_legacy):
    """Brain's once-per-request contextual decision, shared by all Search gates."""
    model_config = {'frozen': True}
    required: bool
    exemption: Literal_legacy['explicit_user_gender', 'dress_or_skirt_product_type'] | None
    interpreted_product_types: list[str]
    source_texts: list[str] = Field_legacy(min_length=1)
    reason: str = Field_legacy(min_length=1)

    @model_validator_legacy(mode="after")
    def validate_decision(self):
        if self.required != (self.exemption is None):
            raise ValueError('Required diversity must have no exemption; exempt diversity needs a reason code.')
        if any((not text.strip() for text in self.source_texts)):
            raise ValueError('Gender policy needs nonblank request evidence.')
        return self

@_preserve_class('RequirementsExtractionV3', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_legacy')
class RequirementsExtractionV3(RequirementsExtraction):
    gender_diversity_policy: GenderDiversityPolicy_legacy

@_preserve_class('ProductTypeAlternative', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_legacy')
class ProductTypeAlternative(StrictBaseModel_legacy):
    requirement_id: str
    value: str
    source_text: str = Field_legacy(min_length=1)

@_preserve_class('RequirementsExtractionV7', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_legacy')
class RequirementsExtractionV7(RequirementsExtractionV3):
    # Independent inventory of EVERY user-allowed product type, before planning.
    product_type_alternatives: list[ProductTypeAlternative]

@_preserve_class('RequirementsAuditV7', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_legacy')
class RequirementsAuditV7(StrictBaseModel_legacy):
    complete: bool
    missing_alternatives: list[ProductTypeAlternative]
    issues: list[str]

@_preserve_class('ResolvedRequirementV8', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_legacy')
class ResolvedRequirementV8(ResolvedRequirement_legacy):
    evaluation_scope: Literal_legacy['search', 'item']
    unrestricted: bool

@_preserve_class('RequirementsExtractionV8', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_legacy')
class RequirementsExtractionV8_legacy(RequirementsExtractionV7):
    requirements: list[ResolvedRequirementV8]
from fashion_recommendation_v2.schemas.condition_routing import ConditionRoutingV37

@_preserve_class('ResolvedRequirements', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_legacy')
class ResolvedRequirements_legacy(RequirementsExtraction):
    condition_routing_v37: ConditionRoutingV37 | None = None
    condition_contract_v26: dict[str, ConditionDefinitionV26] | None = None
    requirements: list[ResolvedRequirement_legacy | ContextAudienceRequirementV1_legacy]
    gender_diversity_policy: GenderDiversityPolicy_legacy | ContextGenderDiversityPolicyV1_legacy | None = Field_legacy(default=None, frozen=True)
    audience_policy_v1: AudienceDecisionV1 | None = None
    product_type_alternatives: list[ProductTypeAlternative] | None = None
    requirements_id: str = Field_legacy(min_length=1)

    @model_serializer(mode='wrap')
    def serialize_audience_version(self, handler):
        data = handler(self)
        if self.condition_routing_v37 is None:
            data.pop('condition_routing_v37', None)
        if self.condition_contract_v26 is None:
            data.pop('condition_contract_v26', None)
        if self.audience_policy_v1 is None:
            data.pop('audience_policy_v1', None)
        return data

    @model_validator_legacy(mode="after")
    def validate_audience_scope(self):
        if self.condition_routing_v37 is not None:
            routing = self.condition_routing_v37
            products = {r.requirement_id for r in self.requirements}
            relations = {r.requirement_id for r in routing.relation_conditions}
            if products & relations or {r.requirement_id for r in routing.assignments} != products | relations:
                raise ValueError('Routing must cover each product/relation condition exactly once.')
        return validate_audience_requirements(self)
SearchAgentInput_legacy.model_rebuild()


# ---- search_requirements_v14 ----

"""schemas.search.requirements.search_requirements_v14: definitions relocated without semantic changes."""
GenderDiversityPolicy = GenderDiversityPolicy_legacy
RequirementsExtractionV8_v14 = RequirementsExtractionV8_legacy
from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_v14
from fashion_recommendation_v2.schemas.search._model_utils import copy_fields as copy_fields_v14
from pydantic import create_model as create_model_v14
AudiencePolicyV14_v14 = create_model_v14('AudiencePolicyV14', __base__=StrictBaseModel_v14, **copy_fields_v14(GenderDiversityPolicy, exclude={'interpreted_product_types'}))
RequirementsExtractionV14_v14 = create_model_v14('RequirementsExtractionV14', __base__=StrictBaseModel_v14, **{**copy_fields_v14(RequirementsExtractionV8_v14, exclude={'product_type_alternatives', 'gender_diversity_policy'}), 'gender_diversity_policy': (AudiencePolicyV14_v14, ...)})

@_preserve_function('bind_product_types', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v14')
def bind_product_types(output):
    data = output.model_dump(mode='json')
    inventory = [dict(requirement_id=r['requirement_id'], value=v, source_text=r['source_text']) for r in data['requirements'] if r['attribute'] == 'product_type' for v in (r['value'] if isinstance(r['value'], list) else [r['value']])]
    data['product_type_alternatives'] = inventory
    data['gender_diversity_policy']['interpreted_product_types'] = list(dict.fromkeys((a['value'] for a in inventory)))
    return RequirementsExtractionV8_v14.model_validate(data)


# ---- search_requirements_v15 ----

"""schemas.search.requirements.search_requirements_v15: definitions relocated without semantic changes."""
AudiencePolicyV14 = AudiencePolicyV14_v14
RequirementsExtractionV14 = RequirementsExtractionV14_v14
RequirementsExtractionV8 = RequirementsExtractionV8_legacy
from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_v15
from fashion_recommendation_v2.schemas.search._model_utils import copy_fields as copy_fields_v15
from pydantic import create_model as create_model_v15
AudiencePolicyV15 = create_model_v15('AudiencePolicyV15', __base__=StrictBaseModel_v15, **copy_fields_v15(AudiencePolicyV14, exclude={'required'}))
RequirementsExtractionV15_v15 = create_model_v15('RequirementsExtractionV15', __base__=StrictBaseModel_v15, **{**copy_fields_v15(RequirementsExtractionV14, exclude={'gender_diversity_policy'}), 'gender_diversity_policy': (AudiencePolicyV15, ...)})

@_preserve_function('bind_requirement_fields', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v15')
def bind_requirement_fields(output):
    data = output.model_dump(mode='json')
    types = [r for r in data['requirements'] if r['attribute'] == 'product_type']
    for r in types:
        if r['kind'] != 'hard' or r['evaluation_scope'] != 'search':
            raise ValueError(f"product_type is reserved for positively allowed hard/search products. Represent dislikes using avoid_product_type, soft/item; retain the negative meaning. requirement_id={r['requirement_id']}")
    inventory = [dict(requirement_id=r['requirement_id'], value=v, source_text=r['source_text']) for r in types for v in (r['value'] if isinstance(r['value'], list) else [r['value']])]
    data['product_type_alternatives'] = inventory
    policy = data['gender_diversity_policy']
    policy['required'] = policy['exemption'] is None
    policy['interpreted_product_types'] = list(dict.fromkeys((a['value'] for a in inventory)))
    return RequirementsExtractionV8.model_validate(data)


# ---- search_requirements_v24 ----

"""schemas.search.requirements.search_requirements_v24: definitions relocated without semantic changes."""
RequirementsExtractionV15_v24 = RequirementsExtractionV15_v15

@_preserve_function('extraction_schema', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v24')
def extraction_schema_v24(source):
    return audience_extraction_schema_v24() if source.audience_context_v1 else RequirementsExtractionV15_v24
from pydantic import create_model as create_model_v24
from fashion_recommendation_v2.schemas.search.requirements.search_requirements_context import CONTEXT_REQUIREMENT_ID
from fashion_recommendation_v2.schemas.search.requirements.search_requirements_context import ContextAudienceRequirementV1 as ContextAudienceRequirementV1_v24
from fashion_recommendation_v2.schemas.search.requirements.search_requirements_context import ContextGenderDiversityPolicyV1
from fashion_recommendation_v2.schemas.search.requirements.search_requirements_context import AudienceInterpretationV1

@_preserve_function('apply_audience_decision', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v24')
def apply_audience_decision_v24(output, decision, *, requirements_id):
    ResolvedRequirements = ResolvedRequirements_legacy
    entries = [r.model_dump(mode='json') for r in output.requirements]
    if any((r['requirement_id'] == CONTEXT_REQUIREMENT_ID for r in entries)):
        raise ValueError('The contextual audience requirement ID is code-owned.')
    policy = output.gender_diversity_policy.model_copy(deep=True)
    if decision.target_gender:
        entries.append(ContextAudienceRequirementV1_v24(value=decision.target_gender, source_text=decision.interpretation.source_text))
        policy = ContextGenderDiversityPolicyV1(interpreted_product_types=policy.interpreted_product_types, source_texts=[decision.interpretation.source_text], reason=decision.interpretation.reason)
    return ResolvedRequirements(requirements_id=requirements_id, requirements=entries, product_type_alternatives=output.product_type_alternatives, gender_diversity_policy=policy, audience_policy_v1=decision)

@_preserve_function('audience_extraction_schema', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v24')
def audience_extraction_schema_v24():
    from pydantic import create_model
    RequirementsExtractionV15 = RequirementsExtractionV15_v15
    return create_model('RequirementsExtractionAudienceV1', __base__=RequirementsExtractionV15, audience_interpretation=(AudienceInterpretationV1, ...))


# ---- search_requirements_v25 ----

"""v25 provenance and review envelope; existing model output fields are preserved."""
from copy import deepcopy as deepcopy_v25
import json
from typing import Any
from typing import Literal as Literal_v25
from pydantic.json_schema import SkipJsonSchema
from pydantic import Field as Field_v25
from pydantic import model_validator as model_validator_v25
from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_v25
from fashion_recommendation_v2.schemas.stylist import StylistResultV3_v3 as StylistResultV3_v25
from fashion_recommendation_v2.schemas.stylist import StylistConditionProvenanceV3_v3 as StylistConditionProvenanceV3_v25
from fashion_recommendation_v2.schemas.stylist import StylistResultV4_v4 as StylistResultV4_v25
from fashion_recommendation_v2.schemas.stylist import StylistConditionProvenanceV4_v4 as StylistConditionProvenanceV4_v25
from fashion_recommendation_v2.schemas.stylist import StylistResultV5_v5 as StylistResultV5_v25
from fashion_recommendation_v2.schemas.stylist import StylistConditionProvenanceV5_v5 as StylistConditionProvenanceV5_v25
from fashion_recommendation_v2.schemas.stylist import StylistResultV6 as StylistResultV6_v25
from fashion_recommendation_v2.schemas.stylist import StylistConditionProvenanceV6 as StylistConditionProvenanceV6_v25
from fashion_recommendation_v2.schemas.stylist import StylistResultV7_stylist_v7 as StylistResultV7_search_requirements_v25
from fashion_recommendation_v2.schemas.stylist import StylistConditionProvenanceV7_stylist_v7 as StylistConditionProvenanceV7_search_requirements_v25
from fashion_recommendation_v2.schemas.stylist import StylistResultV8_stylist_v8 as StylistResultV8_search_requirements_v25
from fashion_recommendation_v2.schemas.stylist import StylistConditionProvenanceV8_stylist_v8 as StylistConditionProvenanceV8_search_requirements_v25
from fashion_recommendation_v2.schemas.stylist import StylistResultV2_v2 as StylistResultV2_v25
from fashion_recommendation_v2.schemas.stylist import StylistResult_base as StylistResult_v25
from fashion_recommendation_v2.schemas.query_composition import SearchQueryComposition
from fashion_recommendation_v2.schemas.relation_intent import RelationIntent as RelationIntent_v25
SearchAgentInput = SearchAgentInput_legacy
# Generation/repair share these unchanged output schemas. Audit receives the same
# subject schema; its own verdict is a different, stage-specific output schema.
from fashion_recommendation_v2.schemas.search.requirements.search_requirements_context import AudienceContextV1
RequirementsExtractionV15 = RequirementsExtractionV15_v15
extraction_schema_v25 = extraction_schema_v24
audience_extraction_schema = audience_extraction_schema_v24
apply_audience_decision = apply_audience_decision_v24

@_preserve_class('SearchAgentInputV25', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v25')
class SearchAgentInputV25_v25(SearchAgentInput):
    search_query_composition: SearchQueryComposition | None = None
    relation_intent: RelationIntent_v25 | None = None
    original_user_query: str = Field_v25(min_length=1, description='Actual current user message before projection/anchor expansion.')
    original_stylist_resolution: SkipJsonSchema[StylistResultV8_search_requirements_v25 | StylistResultV7_search_requirements_v25 | StylistResultV6_v25 | StylistResultV5_v25 | StylistResultV4_v25 | StylistResultV3_v25 | StylistResultV2_v25] | StylistResult_v25 | None = Field_v25(default=None, description='Unmodified Stylist result before projection; provenance only.', json_schema_extra=lambda s: s.pop('title', None))

    @model_validator_v25(mode='after')
    def consistent_originals(self):
        from fashion_recommendation_v2.query_composition import validate_composed_input
        validate_composed_input(self)
        for context in (self.audience_context_v1, self.similarity_reference):
            if context and context.user_query != self.original_user_query:
                raise ValueError('Original request snapshots disagree; never replace original_user_query with expanded user_query.')
        if self.stylist_resolution:
            if self.original_stylist_resolution is None:
                raise ValueError('Stylist projection requires original_stylist_resolution.')
            original = self.original_stylist_resolution
            if getattr(self.stylist_resolution, 'personalization_context', None) != getattr(original, 'personalization_context', None):
                raise ValueError('Stylist projection must preserve frozen profile provenance.')
            if self.stylist_resolution.preference_category != original.preference_category or self.stylist_resolution.resolved_state_ids != original.resolved_state_ids or any((i not in original.interpretations for i in self.stylist_resolution.interpretations)):
                raise ValueError('Stylist projection must preserve original resolved IDs and interpretations.')
        return self

@_preserve_function('prepare_input', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v25')
def prepare_input_v25(source):
    """Copy at the boundary; never modify legacy paths or caller objects."""
    data = deepcopy_v25(source.model_dump(mode='json') if hasattr(source, 'model_dump') else source)
    if 'original_user_query' not in data:
        originals = [data[name]['user_query'] for name in ('audience_context_v1', 'similarity_reference') if data.get(name)]
        data['original_user_query'] = originals[0] if originals else data['user_query']
    if 'original_stylist_resolution' not in data:
        data['original_stylist_resolution'] = deepcopy_v25(data.get('stylist_resolution'))
    if not data.get('audience_context_v1'):
        data['audience_context_v1'] = AudienceContextV1(user_query=data['original_user_query']).model_dump(mode='json')
    return SearchAgentInputV25_v25.model_validate_json(json.dumps(data, ensure_ascii=False))

@_preserve_class('CodeValidationV25', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v25')
class CodeValidationV25(StrictBaseModel_v25):
    status: Literal_v25['pending', 'passed', 'failed'] = 'pending'
    checks: list[str] = Field_v25(default_factory=list)
    errors: list[str] = Field_v25(default_factory=list)
    derived: dict[str, Any] = Field_v25(default_factory=dict)

@_preserve_class('RequirementsReviewInputV25', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v25')
class RequirementsReviewInputV25(StrictBaseModel_v25):
    """Never inject code-derived fields into model_response or rename nested fields."""
    model_response: dict[str, Any] | None
    model_response_text: str | None = None
    response_schema: dict[str, Any]
    code_validation: CodeValidationV25 = Field_v25(default_factory=CodeValidationV25)


# ---- search_requirements_v26 ----

"""Two immutable inventories: condition meaning first, ID-only application second."""
from typing import Annotated
from typing import Literal as Literal_v26
from typing import Union as Union_v26
from pydantic import Field as Field_v26
from pydantic import create_model as create_model_v26
from pydantic import model_validator as model_validator_v26
from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_v26
from fashion_recommendation_v2.schemas.price import PriceConstraint
from fashion_recommendation_v2.schemas.stylist import StylistDetailValue_base as StylistDetailValue_v26
from fashion_recommendation_v2.schemas.stylist import StylistAttribute
SearchAgentInputV25_v26 = SearchAgentInputV25_v25
prepare_input_v26 = prepare_input_v25
from fashion_recommendation_v2.schemas.search._model_utils import preserve_response_schema as preserve_response_schema_v26
Nonblank_v26 = Annotated[str, Field_v26(min_length=1, pattern=r'\S')]
ConditionValue_v26 = Nonblank_v26 | list[Nonblank_v26] | PriceConstraint | StylistDetailValue_v26
CanonicalAttributeV26 = Literal_v26['product_type', 'gender', 'sleeve_length', 'pattern', 'color', 'size', 'brand', 'price', 'avoid_product_type', 'detail']

@_preserve_class('StructuredConditionV26', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v26')
class StructuredConditionV26(StrictBaseModel_v26):
    requirement_id: str = Field_v26(pattern=r'^[a-zA-Z][a-zA-Z0-9_]{0,79}$')
    attribute: CanonicalAttributeV26
    value: ConditionValue_v26
    source: Literal_v26['user', 'reference']
    source_text: Nonblank_v26
    role: Literal_v26['target', 'anchor']
    polarity: Literal_v26['positive', 'negative', 'unrestricted']

    @model_validator_v26(mode='after')
    def value_shape(self):
        if (self.attribute == 'detail') != isinstance(self.value, StylistDetailValue_v26):
            raise ValueError('detail requires the unchanged key/values object; other attributes cannot use it.')
        if (self.attribute == 'price') != isinstance(self.value, PriceConstraint):
            raise ValueError('price requires a PriceConstraint in the original currency.')
        if isinstance(self.value, list) and (not self.value or (self.source != 'stylist' and len(self.value) != len(set(self.value)))):
            raise ValueError('OR alternatives must be nonempty and unique.')
        if isinstance(self.value, (str, list)) and any((not v.strip() for v in ([self.value] if isinstance(self.value, str) else self.value))):
            raise ValueError('Condition values must contain nonblank text.')
        return self
from fashion_recommendation_v2.schemas.stylist import StylistResultV3_v3 as StylistResultV3_v26
from fashion_recommendation_v2.schemas.stylist import StylistConditionProvenanceV3_v3 as StylistConditionProvenanceV3_v26
from fashion_recommendation_v2.schemas.stylist import StylistResultV4_v4 as StylistResultV4_v26
from fashion_recommendation_v2.schemas.stylist import StylistConditionProvenanceV4_v4 as StylistConditionProvenanceV4_v26
from fashion_recommendation_v2.schemas.stylist import StylistResultV5_v5 as StylistResultV5_v26
from fashion_recommendation_v2.schemas.stylist import StylistConditionProvenanceV5_v5 as StylistConditionProvenanceV5_v26
from fashion_recommendation_v2.schemas.stylist import StylistResultV6 as StylistResultV6_v26
from fashion_recommendation_v2.schemas.stylist import StylistConditionProvenanceV6 as StylistConditionProvenanceV6_v26
from fashion_recommendation_v2.schemas.stylist import StylistResultV7_stylist_v7 as StylistResultV7_search_requirements_v26
from fashion_recommendation_v2.schemas.stylist import StylistConditionProvenanceV7_stylist_v7 as StylistConditionProvenanceV7_search_requirements_v26
from fashion_recommendation_v2.schemas.stylist import StylistResultV8_stylist_v8 as StylistResultV8_search_requirements_v26
from fashion_recommendation_v2.schemas.stylist import StylistConditionProvenanceV8_stylist_v8 as StylistConditionProvenanceV8_search_requirements_v26
from fashion_recommendation_v2.schemas.stylist import StylistConditionProvenanceV2_v2 as StylistConditionProvenanceV2_v26

@_preserve_class('StylistConditionV26', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v26')
class StylistConditionV26(StructuredConditionV26):
    source: Literal_v26['stylist']
    attribute: StylistAttribute
    source_text: Nonblank_v26 | None
    stylist_provenance: StylistConditionProvenanceV8_search_requirements_v26 | StylistConditionProvenanceV7_search_requirements_v26 | StylistConditionProvenanceV6_v26 | StylistConditionProvenanceV5_v26 | StylistConditionProvenanceV4_v26 | StylistConditionProvenanceV3_v26 | StylistConditionProvenanceV2_v26 | None = None

    @model_validator_v26(mode='after')
    def source_shape(self):
        if self.stylist_provenance is None:
            if self.source_text is None:
                raise ValueError('Legacy Stylist condition requires source_text.')
        elif (self.stylist_provenance.origin == 'preference') != (self.source_text is None):
            raise ValueError('Only preference-only Stylist condition permits null source_text.')
        return self

@_preserve_class('ExplicitAudienceV26', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v26')
class ExplicitAudienceV26(StrictBaseModel_v26):
    basis: Literal_v26['explicit_request']
    product_type: None = Field_v26(description='Only product_default may have a product_type.')
    source_text: Nonblank_v26
    reason: Nonblank_v26

@_preserve_class('AnchorAudienceV26', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v26')
class AnchorAudienceV26(ExplicitAudienceV26):
    basis: Literal_v26['anchor']

@_preserve_class('NoAudienceV26', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v26')
class NoAudienceV26(ExplicitAudienceV26):
    basis: Literal_v26['none']

@_preserve_class('DefaultAudienceV26', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v26')
class DefaultAudienceV26(ExplicitAudienceV26):
    basis: Literal_v26['product_default']
    product_type: Literal_v26['skirt', 'dress', 'high_heels', 'tuxedo']

@_preserve_class('RequirementsStructureV26', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v26')
class RequirementsStructureV26(StrictBaseModel_v26):
    # No kind, evaluation_scope, model-authored diversity policy, or Stylist copy.
    conditions: list[StructuredConditionV26]
    audience_interpretation: Union_v26[ExplicitAudienceV26, AnchorAudienceV26, DefaultAudienceV26, NoAudienceV26]

@_preserve_class('UserApplicationV26', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v26')
class UserApplicationV26_v26(StrictBaseModel_v26):
    requirement_id: Nonblank_v26
    kind: Literal_v26['hard', 'soft']
    evaluation_scope: Literal_v26['search', 'item']
    reason: Nonblank_v26

@_preserve_class('PreservedApplicationV26', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v26')
class PreservedApplicationV26_v26(StrictBaseModel_v26):
    requirement_id: Nonblank_v26
    # Stylist/reference kind is code-owned soft. Only scope needs interpretation.
    evaluation_scope: Literal_v26['search', 'item']
    reason: Nonblank_v26

@_preserve_class('RequirementsClassificationV26', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v26')
class RequirementsClassificationV26(StrictBaseModel_v26):
    user_applications: list[UserApplicationV26_v26]
    preserved_applications: list[PreservedApplicationV26_v26]

@_preserve_function('extraction_schema', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v26')
def extraction_schema_v26(source):
    return preserve_response_schema_v26(RequirementsStructureV26)

@_preserve_function('classification_schema', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v26')
def classification_schema_v26(conditions):
    fields = {}
    for field, model, source in [('user_applications', UserApplicationV26_v26, 'user'), ('preserved_applications', PreservedApplicationV26_v26, 'preserved')]:
        ids = tuple((c.requirement_id for c in conditions if c.role == 'target' and (c.source == 'user') == (source == 'user')))
        entry = create_model_v26(model.__name__ + 'Bound', __base__=model, requirement_id=(Literal_v26[ids], ...)) if ids else model
        fields[field] = (list[entry], Field_v26(..., min_length=len(ids), max_length=len(ids)))
    schema = create_model_v26('RequirementsClassificationV26', __base__=RequirementsClassificationV26, **fields)
    return preserve_response_schema_v26(schema)


# ---- search_requirements_v30 ----

"""v30 proposals preserve facts; deterministic projections own executable policy."""
from typing import Literal as Literal_v30
from pydantic import Field as Field_v30
from pydantic import create_model as create_model_v30
from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_v30
from fashion_recommendation_v2.schemas.search._model_utils import preserve_response_schema as preserve_response_schema_v30
Nonblank = Nonblank_v26
ConditionValue = ConditionValue_v26
UserApplicationV26 = UserApplicationV26_v26
PreservedApplicationV26 = PreservedApplicationV26_v26
prepare_input_v30 = prepare_input_v26
# Registered native dimensions are accepted without wrapping OR lists in detail.
AttributeV30 = Literal_v30['product_type', 'gender', 'sleeve_length', 'pattern', 'color', 'size', 'brand', 'price', 'avoid_product_type', 'detail', 'fit', 'material', 'season', 'occasion', 'theme', 'strength', 'garment_care', 'category']

@_preserve_class('StructuredConditionV30', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v30')
class StructuredConditionV30_v30(StrictBaseModel_v30):
    requirement_id: str = Field_v30(pattern=r'^[a-zA-Z][a-zA-Z0-9_]{0,79}$')
    attribute: AttributeV30
    value: ConditionValue = Field_v30(description='Preserve OR lists. All allowed target product types belong to one OR list, not separate mandatory garment rows.')
    source: Literal_v30['user', 'reference'] = Field_v30(description='Follow SOURCE_RULES documents. Expanded reference prose is reference, never new user intent. Stylist originals are attached by code; do not copy them here.')
    source_text: Nonblank = Field_v30(description='Exact quote from the field-specific SOURCE_RULES document. Reference evidence must support this attribute and its values, not an unrelated reference fact.')
    role: Literal_v30['target', 'anchor']
    polarity: Literal_v30['positive', 'negative', 'unrestricted'] = Field_v30(description='An explicitly accepted product alternative is positive. Unrestricted means no constraint, not permission to choose a named alternative.')

@_preserve_class('AudienceProposalV30', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v30')
class AudienceProposalV30(StrictBaseModel_v30):
    # Cross-field consistency is checked on the code-derived decision, not here.
    basis: Literal_v30['explicit_request', 'anchor', 'product_default', 'none']
    product_type: Literal_v30['skirt', 'dress', 'high_heels', 'tuxedo'] | None
    source_text: Nonblank
    reason: Nonblank

@_preserve_class('RequirementsStructureV30', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v30')
class RequirementsStructureV30_v30(StrictBaseModel_v30):
    conditions: list[StructuredConditionV30_v30]
    audience_interpretation: AudienceProposalV30

@_preserve_class('RequirementsClassificationV30', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v30')
class RequirementsClassificationV30_v30(StrictBaseModel_v30):
    user_applications: list[UserApplicationV26]
    preserved_applications: list[PreservedApplicationV26]

@_preserve_function('extraction_schema', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v30')
def extraction_schema_v30(source):
    return preserve_response_schema_v30(RequirementsStructureV30_v30)

@_preserve_function('classification_schema', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v30')
def classification_schema_v30(conditions):
    fields = {}
    for field, model, user in [('user_applications', UserApplicationV26, True), ('preserved_applications', PreservedApplicationV26, False)]:
        ids = tuple((c.requirement_id for c in conditions if c.role == 'target' and (c.source == 'user') == user))
        entry = create_model_v30(model.__name__ + 'V30Bound', __base__=model, requirement_id=(Literal_v30[ids], ...)) if ids else model
        fields[field] = (list[entry], Field_v30(..., min_length=len(ids), max_length=len(ids)))
    return preserve_response_schema_v30(create_model_v30('RequirementsClassificationV30', __base__=RequirementsClassificationV30_v30, **fields))


# ---- search_requirements_v31 ----

"""v31 keeps the proposal types; role interpretation is shared neutral policy."""
from pydantic import create_model as create_model_v31
from fashion_recommendation_v2.schemas.search._model_utils import preserve_response_schema as preserve_response_schema_v31
from fashion_recommendation_v2.schemas.search._model_utils import copy_fields
RequirementsStructureV30_v31 = RequirementsStructureV30_v30
RequirementsClassificationV30 = RequirementsClassificationV30_v30
prepare_input_v31 = prepare_input_v30
classification_v30 = classification_schema_v30

@_preserve_class('RequirementsStructureV31', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v31')
class RequirementsStructureV31(RequirementsStructureV30_v31):
    """Immutable structure proposal, before the code-owned role projection."""

@_preserve_class('RequirementsClassificationV31', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v31')
class RequirementsClassificationV31(RequirementsClassificationV30):
    """ID-only labels for the same projected condition inventory."""

@_preserve_function('extraction_schema', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v31')
def extraction_schema_v31(source):
    return preserve_response_schema_v31(RequirementsStructureV31)

@_preserve_function('classification_schema', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v31')
def classification_schema_v31(conditions):
    bound = classification_v30(conditions)
    return preserve_response_schema_v31(create_model_v31('RequirementsClassificationV31', __base__=RequirementsClassificationV31, **copy_fields(bound)))


# ---- search_requirements_v37 ----

"""v37 uses two calls; relationship clauses never enter product judgments."""
from copy import deepcopy
from typing import Literal as Literal_v37
from pydantic import Field as Field_v37
from pydantic import create_model as create_model_v37
from fashion_recommendation_v2.schemas.base import StrictBaseModel
from fashion_recommendation_v2.schemas.condition_routing import RelationCondition
from fashion_recommendation_v2.schemas.condition_routing import ConditionAssignment as ConditionAssignment_v37
from fashion_recommendation_v2.schemas.relation_intent import RelationIntent
from fashion_recommendation_v2.schemas.search._model_utils import preserve_response_schema as preserve_response_schema_v37
SearchAgentInputV25 = SearchAgentInputV25_v25
previous_input_v37 = prepare_input_v25
RequirementsStructureV30 = RequirementsStructureV30_v30
product_classification = classification_schema_v30

@_preserve_class('SearchAgentInputV37', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v37')
class SearchAgentInputV37_v37(SearchAgentInputV25):
    # Confirmed upstream identity, never a new anchor selection by Search.
    relation_intent: RelationIntent | None = None

@_preserve_function('prepare_input', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v37')
def prepare_input_v37(source):
    intent = source.get('relation_intent') if isinstance(source, dict) else source.relation_intent
    anchor = source.get('relation_anchor') if isinstance(source, dict) else source.relation_anchor
    prepared = previous_input_v37(source)
    data = prepared.model_dump()
    data['relation_intent'] = deepcopy(intent.model_dump(mode='json') if hasattr(intent, 'model_dump') else intent)
    result = SearchAgentInputV37_v37.model_validate(data)
    result.relation_anchor = anchor
    return result

@_preserve_class('RequirementsStructureV37', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v37')
class RequirementsStructureV37_v37(RequirementsStructureV30):
    relation_conditions: list[RelationCondition]
    relative_requirement_ids: list[str] = Field_v37(description='Product IDs requiring comparison against the confirmed anchor, e.g. longer than anchor; never absolute long.')

@_preserve_function('extraction_schema', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v37')
def extraction_schema_v37(source):
    count = int(source.relation_intent is not None)
    return preserve_response_schema_v37(create_model_v37('RequirementsStructureV37', __base__=RequirementsStructureV37_v37, relation_conditions=(list[RelationCondition], Field_v37(..., min_length=count, max_length=count))))

@_preserve_function('classification_schema', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v37')
def classification_schema_v37(conditions, *, relation_conditions=()):
    ids = tuple([c.requirement_id for c in conditions if c.role == 'target'] + [r.requirement_id for r in relation_conditions])
    entry = create_model_v37('ConditionAssignmentV37', __base__=ConditionAssignment_v37, requirement_id=(Literal_v37[ids], ...)) if ids else ConditionAssignment_v37
    return preserve_response_schema_v37(create_model_v37('RequirementsClassificationV37', __base__=product_classification(conditions), assignments=(list[entry], Field_v37(..., min_length=len(ids), max_length=len(ids)))))


# ---- search_requirements_v46 ----

"""v46 provenance contract; preserve the two-stage response wire and operation names."""
from typing import ClassVar
from typing import Literal as Literal_v46
from pydantic import Field as Field_v46
from pydantic import create_model as create_model_v46
from fashion_recommendation_v2.schemas.search._model_utils import preserve_response_schema as preserve_response_schema_v46
StructuredConditionV30 = StructuredConditionV30_v30
SearchAgentInputV37 = SearchAgentInputV37_v37
RequirementsStructureV37 = RequirementsStructureV37_v37
previous_schema_v46 = extraction_schema_v37
classification_schema_v46 = classification_schema_v37
previous_input_v46 = prepare_input_v37

@_preserve_class('SearchAgentInputV46', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v46')
class SearchAgentInputV46_v46(SearchAgentInputV37):
    # Internal contract selection, never a new input/provenance field.
    requirements_source_version: ClassVar[str] = 'v46'

@_preserve_function('prepare_input', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v46')
def prepare_input_v46(source):
    prepared = previous_input_v46(source)
    result = SearchAgentInputV46_v46.model_validate(prepared.model_dump())
    result.relation_anchor = prepared.relation_anchor
    return result

@_preserve_function('extraction_schema', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v46')
def extraction_schema_v46(source):
    schema = previous_schema_v46(source)
    if not source.relation_intent or source.relation_intent.relation_type != 'compatibility':
        return schema
    condition = create_model_v46('CompatibilityTargetConditionV46', __base__=StructuredConditionV30, role=(Literal_v46['target'], Field_v46(..., description='Only searched target product conditions.')), source=(Literal_v46['user'], Field_v46(..., description='Actual user conditions only; code attaches Stylist originals.')))
    return preserve_response_schema_v46(create_model_v46('RequirementsStructureV37', __base__=schema, conditions=(list[condition], ...)))


# ---- search_requirements_v47 ----

"""v47 reuses two operations, adding semantic comparisons to classification."""
from typing import ClassVar
from typing import Literal as Literal_v47
from typing import Union
from pydantic import Field as Field_v47
from pydantic import create_model as create_model_v47
from pydantic import model_validator as model_validator_v47
from fashion_recommendation_v2.schemas.condition_routing import ConditionAssignment
from fashion_recommendation_v2.schemas.condition_routing import fixed_condition_owners
from fashion_recommendation_v2.schemas.stylist_condition_policy import StylistUserComparison
from fashion_recommendation_v2.schemas.search._model_utils import preserve_response_schema as preserve_response_schema_v47
SearchAgentInputV46 = SearchAgentInputV46_v46
extraction_schema_v47 = extraction_schema_v46
previous_input_v47 = prepare_input_v46
previous_classification = classification_schema_v37

@_preserve_class('SearchAgentInputV47', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v47')
class SearchAgentInputV47_v47(SearchAgentInputV46):
    requirements_source_version: ClassVar[str] = 'v47'

@_preserve_function('prepare_input', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v47')
def prepare_input_v47(source):
    prepared = previous_input_v47(source)
    result = SearchAgentInputV47_v47.model_validate(prepared.model_dump())
    result.relation_anchor = prepared.relation_anchor
    return result

@_preserve_function('classification_schema', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v47')
def classification_schema_v47(conditions, *, relation_conditions=()):
    owners = fixed_condition_owners(conditions, relation_conditions)
    variants = []
    for owner in ('relation', 'ranking'):
        ids = tuple((rid for rid, expected in owners.items() if expected == owner))
        if ids:
            variants.append(create_model_v47('ConditionAssignmentV47_' + owner, __base__=ConditionAssignment, requirement_id=(Literal_v47[ids], ...), owner=(Literal_v47[owner], ...)))
    entry = Union[tuple(variants)] if len(variants) > 1 else variants[0] if variants else ConditionAssignment

    @model_validator_v47(mode='after')
    def exact_assignments(self):
        actual = {row.requirement_id: row.owner for row in self.assignments}
        if len(actual) != len(self.assignments) or actual != owners:
            raise ValueError('Assignments must cover each frozen condition ID once with its fixed owner.')
        return self
    return preserve_response_schema_v47(create_model_v47('RequirementsClassificationV37', __base__=previous_classification(conditions, relation_conditions=relation_conditions), __validators__={'fixed_assignments': exact_assignments}, assignments=(list[entry], Field_v47(..., min_length=len(owners), max_length=len(owners), description='Copy each fixed ID/owner pair once. Reference products and relation clauses use relation; user/Stylist products use ranking, regardless of target role or search/item scope.')), stylist_user_comparisons=(list[StylistUserComparison], Field_v47(..., description='Exactly one comparison per same-dimension Stylist / classified hard-user pair. Empty if none.'))))


# ---- search_requirements_v48 ----

"""v48 input policy: category anchors participate in code-owned audience defaults."""
from typing import ClassVar
SearchAgentInputV47 = SearchAgentInputV47_v47
extraction_schema_v48 = extraction_schema_v47
classification_schema_v48 = classification_schema_v47
previous_input_v48 = prepare_input_v47

@_preserve_class('SearchAgentInputV48', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v48')
class SearchAgentInputV48_v48(SearchAgentInputV47):
    requirements_source_version: ClassVar[str] = 'v48'

    def category_anchor_context(self, context):
        from fashion_recommendation_v2.schemas.search.requirements.search_requirements_context import CategoryAnchorAudienceContextV48
        return CategoryAnchorAudienceContextV48(**context.model_dump(exclude={'anchor_category', 'anchor_category_source'}), anchor_category=self.relation_intent.anchor_category)

@_preserve_function('prepare_input', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v48')
def prepare_input_v48(source):
    prepared = previous_input_v48(source)
    result = SearchAgentInputV48_v48.model_validate(prepared.model_dump())
    result.relation_anchor = prepared.relation_anchor
    return result


# ---- search_requirements_v49 ----

"""v49 binds detail attributes to keyed objects; other value contracts stay intact."""
from typing import ClassVar
from typing import Literal
from typing import get_args
from pydantic import Field as Field_v49
from pydantic import RootModel
from pydantic import create_model as create_model_v49
from pydantic import model_validator
from fashion_recommendation_v2.schemas.stylist import StylistDetailValue_base as StylistDetailValue
from fashion_recommendation_v2.schemas.search._model_utils import preserve_response_schema
SearchAgentInputV48 = SearchAgentInputV48_v48
previous_input_v49 = prepare_input_v48
classification_schema_v49 = classification_schema_v48
previous_schema_v49 = extraction_schema_v48
from fashion_recommendation_v2.schemas.stylist import StylistResult_base as StylistResult
from fashion_recommendation_v2.schemas.stylist import StylistResultV3_v3 as StylistResultV3
from fashion_recommendation_v2.schemas.stylist import StylistConditionProvenanceV3_v3 as StylistConditionProvenanceV3
from fashion_recommendation_v2.schemas.stylist import StylistResultV4_v4 as StylistResultV4
from fashion_recommendation_v2.schemas.stylist import StylistConditionProvenanceV4_v4 as StylistConditionProvenanceV4
from fashion_recommendation_v2.schemas.stylist import StylistResultV5_v5 as StylistResultV5
from fashion_recommendation_v2.schemas.stylist import StylistConditionProvenanceV5_v5 as StylistConditionProvenanceV5
from fashion_recommendation_v2.schemas.stylist import StylistResultV6
from fashion_recommendation_v2.schemas.stylist import StylistConditionProvenanceV6
from fashion_recommendation_v2.schemas.stylist import StylistResultV7_stylist_v7 as StylistResultV7_search_requirements_v49
from fashion_recommendation_v2.schemas.stylist import StylistConditionProvenanceV7_stylist_v7 as StylistConditionProvenanceV7_search_requirements_v49
from fashion_recommendation_v2.schemas.stylist import StylistResultV8_stylist_v8 as StylistResultV8_search_requirements_v49
from fashion_recommendation_v2.schemas.stylist import StylistConditionProvenanceV8_stylist_v8 as StylistConditionProvenanceV8_search_requirements_v49
from fashion_recommendation_v2.schemas.stylist import StylistResultV2_v2 as StylistResultV2
from fashion_recommendation_v2.schemas.stylist import StylistConditionProvenanceV2_v2 as StylistConditionProvenanceV2
ResolvedRequirement = ResolvedRequirement_legacy
ResolvedRequirements = ResolvedRequirements_legacy
from fashion_recommendation_v2.schemas.search.requirements.search_requirements_context import ContextAudienceRequirementV1

@_preserve_class('ResolvedRequirementV49', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v49')
class ResolvedRequirementV49(ResolvedRequirement):
    """Published v49 transport extension; old generation schemas stay frozen."""
    source_text: str | None = Field_v49(min_length=1)
    stylist_provenance: StylistConditionProvenanceV8_search_requirements_v49 | StylistConditionProvenanceV7_search_requirements_v49 | StylistConditionProvenanceV6 | StylistConditionProvenanceV5 | StylistConditionProvenanceV4 | StylistConditionProvenanceV3 | StylistConditionProvenanceV2 | None = None

@_preserve_class('ResolvedRequirementsV49', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v49')
class ResolvedRequirementsV49(ResolvedRequirements):
    requirements: list[ResolvedRequirementV49 | ContextAudienceRequirementV1]

@_preserve_class('SearchAgentInputV49', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v49')
class SearchAgentInputV49_v49(SearchAgentInputV48):
    requirements_source_version: ClassVar[str] = 'v49'
    stylist_resolution: StylistResultV8_search_requirements_v49 | StylistResultV7_search_requirements_v49 | StylistResultV6 | StylistResultV5 | StylistResultV4 | StylistResultV3 | StylistResultV2 | StylistResult | None = None
    original_stylist_resolution: StylistResultV8_search_requirements_v49 | StylistResultV7_search_requirements_v49 | StylistResultV6 | StylistResultV5 | StylistResultV4 | StylistResultV3 | StylistResultV2 | StylistResult | None = Field_v49(default=None, description='Unmodified Stylist result before projection; provenance only.')

@_preserve_function('prepare_input', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v49')
def prepare_input_v49(source):
    prepared = previous_input_v49(source)
    result = SearchAgentInputV49_v49.model_validate(prepared.model_dump())
    result.relation_anchor = prepared.relation_anchor
    return result

@_preserve_function('check_detail_shapes', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v49')
def check_detail_shapes(data):
    errors = []
    if isinstance(data, dict):
        for row in data.get('conditions', []):
            if not isinstance(row, dict) or row.get('attribute') != 'detail':
                continue
            value = row.get('value')
            if not isinstance(value, dict) or 'key' not in value or 'values' not in value:
                errors.append(f"detail_shape: condition_id={row.get('requirement_id')}; field=conditions.value; actual_type={type(value).__name__}; actual={value!r}; expected={{key: nonblank detail name, values: OR string array}}. Return an explicit key and values object; do not infer or discard the condition.")
    if errors:
        raise ValueError(' | '.join(errors))
    return data

@_preserve_function('extraction_schema', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v49')
def extraction_schema_v49(source):
    base = previous_schema_v49(source)
    condition = get_args(base.model_fields['conditions'].annotation)[0]
    attributes = tuple((a for a in get_args(condition.model_fields['attribute'].annotation) if a != 'detail'))
    detail = create_model_v49('DetailConditionV49', __base__=condition, attribute=(Literal['detail'], ...), value=(StylistDetailValue, Field_v49(..., description='Required keyed detail object. key names the detail; values preserves OR alternatives.')))
    general = create_model_v49('GeneralConditionV49', __base__=condition, attribute=(Literal[attributes], ...))
    # anyOf branches, not an if/then schema: the detail+scalar combination is impossible.
    result = create_model_v49('RequirementsStructureV37', __base__=base, conditions=(list[detail | general], ...), __validators__={'detail_shapes': model_validator(mode='before')(check_detail_shapes)})
    return preserve_response_schema(result)

@_preserve_class('SearchLLMInputV49', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v49')
class SearchLLMInputV49(RootModel[dict]):
    """Model-facing projection; complete validated source remains separate."""


# ---- search_requirements_v54 ----

"""v54 adds an optional, advisory explanation for unused reference features."""
from typing import ClassVar
from pydantic import Field
from pydantic import create_model
SearchAgentInputV49 = SearchAgentInputV49_v49
previous_input = prepare_input_v49
previous_schema = extraction_schema_v49
classification_schema = classification_schema_v49

@_preserve_class('SearchAgentInputV54', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v54')
class SearchAgentInputV54(SearchAgentInputV49):
    requirements_source_version: ClassVar[str] = 'v54'

@_preserve_function('prepare_input', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v54')
def prepare_input(source):
    prepared = previous_input(source)
    result = SearchAgentInputV54.model_validate(prepared.model_dump())
    result.relation_anchor = prepared.relation_anchor
    return result

@_preserve_function('extraction_schema', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v54')
def extraction_schema(source):
    return create_model('RequirementsStructureV37', __base__=previous_schema(source), reference_nonuse_reason=(str | None, Field(default=None, description='Brief reason for selecting no reference target conditions in similarity, e.g. user conflict, uncertain facts, or meaning already covered by user conditions. Optional advisory explanation; absence or insufficient detail never blocks execution.')))


# ---- search_requirements_v57 ----

"""v57 records decomposition reasons separately from untouched condition fields."""
from typing import ClassVar
from typing import Literal as Literal_search_requirements_v57
from pydantic import Field as Field_search_requirements_v57
from pydantic import create_model as create_model_search_requirements_v57
from pydantic import model_validator as model_validator_search_requirements_v57
from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_search_requirements_v57
SearchAgentInputV54_search_requirements_v57 = SearchAgentInputV54
previous_input_search_requirements_v57 = prepare_input
previous_schema_search_requirements_v57 = extraction_schema
classification_schema_search_requirements_v57 = classification_schema
from fashion_recommendation_v2.schemas.search._model_utils import preserve_response_schema as preserve_response_schema_search_requirements_v57

@_preserve_class('DecompositionDecisionV57', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v57')
class DecompositionDecisionV57_search_requirements_v57(StrictBaseModel_search_requirements_v57):
    requirement_id: str = Field_search_requirements_v57(min_length=1)
    reason: str | None = Field_search_requirements_v57(default=None, description='Why this semantic unit was separated or retained; preserve garment-part context.')

@_preserve_class('RequirementSourceSpanV57', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v57')
class RequirementSourceSpanV57_search_requirements_v57(StrictBaseModel_search_requirements_v57):
    start: int
    end: int
    source_text: str

@_preserve_class('RequirementSourceUnitV57', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v57')
class RequirementSourceUnitV57_search_requirements_v57(StrictBaseModel_search_requirements_v57):
    unit_id: str
    state_id: str | None
    role: Literal_search_requirements_v57['direct_user', 'stylist_resolved', 'omitted_unresolved', 'context_only']
    spans: list[RequirementSourceSpanV57_search_requirements_v57]

@_preserve_class('RequirementExtractionScopeV57', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v57')
class RequirementExtractionScopeV57_search_requirements_v57(StrictBaseModel_search_requirements_v57):
    """Advisory source ownership; no response rejection based on this boundary."""
    coordinate_source: Literal_search_requirements_v57['orchestrator_user_query'] = 'orchestrator_user_query'
    source_text: str
    direct_user_text: str
    units: list[RequirementSourceUnitV57_search_requirements_v57]

@_preserve_class('RequirementQuote', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v57')
class RequirementQuote_search_requirements_v57(StrictBaseModel_search_requirements_v57):
    source_text: str

@_preserve_class('RequirementQuoteUnit', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v57')
class RequirementQuoteUnit_search_requirements_v57(RequirementSourceUnitV57_search_requirements_v57):
    spans: list[RequirementQuote_search_requirements_v57]

@_preserve_class('RequirementQuoteScope', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v57')
class RequirementQuoteScope_search_requirements_v57(StrictBaseModel_search_requirements_v57):
    coordinate_source: Literal_search_requirements_v57['orchestrator_quotes'] = 'orchestrator_quotes'
    source_text: str
    direct_user_text: str
    units: list[RequirementQuoteUnit_search_requirements_v57]

@_preserve_class('SearchAgentInputV57', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v57')
class SearchAgentInputV57_search_requirements_v57(SearchAgentInputV54_search_requirements_v57):
    requirements_source_version: ClassVar[str] = 'v57'
    requirement_extraction_scope: RequirementExtractionScopeV57_search_requirements_v57 | RequirementQuoteScope_search_requirements_v57 | None = None

@_preserve_function('prepare_input', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v57')
def prepare_input_search_requirements_v57(source):
    scope = getattr(source, 'requirement_extraction_scope', None)
    legacy = SearchAgentInputV54_search_requirements_v57.model_validate(source.model_dump(exclude={'requirement_extraction_scope'}))
    legacy.relation_anchor = getattr(source, 'relation_anchor', None)
    old = previous_input_search_requirements_v57(legacy)
    result = SearchAgentInputV57_search_requirements_v57.model_validate(dict(old.model_dump(), requirement_extraction_scope=scope))
    result.relation_anchor = old.relation_anchor
    return result

@_preserve_function('extraction_schema', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v57')
def extraction_schema_search_requirements_v57(source):

    def coverage(self):
        ids = [r.requirement_id for r in self.decomposition_decisions or []]
        if len(ids) != len(set(ids)) or not set(ids) <= {r.requirement_id for r in self.conditions}:
            raise ValueError('Decomposition reason IDs must be unique and refer to existing product conditions.')
        return self
    return preserve_response_schema_search_requirements_v57(create_model_search_requirements_v57('RequirementsStructureV37', __base__=previous_schema_search_requirements_v57(source), decomposition_decisions=(list[DecompositionDecisionV57_search_requirements_v57] | None, None), __validators__={'decomposition_coverage': model_validator_search_requirements_v57(mode='after')(coverage)}))


# ---- search_requirements_v58 ----

"""v58 compact Stylist transport and bound comparisons; v57 extraction semantics."""
from typing import ClassVar
from typing import Literal as Literal_search_requirements_v58
from typing import Union as Union_search_requirements_v58
import json as json_search_requirements_v58
from pydantic import Field as Field_search_requirements_v58
from pydantic import create_model as create_model_search_requirements_v58
from pydantic import model_validator as model_validator_search_requirements_v58
SearchAgentInputV57_search_requirements_v58 = SearchAgentInputV57_search_requirements_v57
previous_input_search_requirements_v58 = prepare_input_search_requirements_v57
extraction_schema_search_requirements_v58 = extraction_schema_search_requirements_v57
previous_classification_search_requirements_v58 = classification_schema_search_requirements_v57
from fashion_recommendation_v2.schemas.search._model_utils import preserve_response_schema as preserve_response_schema_search_requirements_v58
from fashion_recommendation_v2.schemas.stylist_condition_policy import StylistUserComparison as StylistUserComparison_search_requirements_v58
from fashion_recommendation_v2.search.stylist_comparison_targets import comparison_targets_stylist_comparison_targets_v58 as comparison_targets_search_requirements_v58
from fashion_recommendation_v2.search.stylist_comparison_targets import required_pairs_stylist_comparison_targets_v58 as required_pairs_search_requirements_v58
from fashion_recommendation_v2.search.stylist_policy import validate_comparisons as validate_comparisons_search_requirements_v58
from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_search_requirements_v58
from fashion_recommendation_v2.schemas.stylist import StylistInterpretation_base as StylistInterpretation_search_requirements_v58
from fashion_recommendation_v2.schemas.stylist import NonBlankText_base as NonBlankText_search_requirements_v58
from fashion_recommendation_v2.schemas.stylist import StylistInterpretationV2_v2 as StylistInterpretationV2_search_requirements_v58
from fashion_recommendation_v2.schemas.stylist import StylistInterpretationV3_v3 as StylistInterpretationV3_search_requirements_v58

@_preserve_class('SearchPreferencePriorityV58', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v58')
class SearchPreferencePriorityV58_search_requirements_v58(StrictBaseModel_search_requirements_v58):
    """Only the used interpretation's grades and evidence ownership for planning."""
    interpretation_id: NonBlankText_search_requirements_v58
    importance: Literal_search_requirements_v58['high', 'medium', 'low']
    confidence: Literal_search_requirements_v58['high', 'medium', 'low']
    supporting_evidence_refs: list[NonBlankText_search_requirements_v58]
    counter_evidence_refs: list[NonBlankText_search_requirements_v58]

@_preserve_class('SearchStylistResolutionV58', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v58')
class SearchStylistResolutionV58_search_requirements_v58(StrictBaseModel_search_requirements_v58):
    """Search conditions and provenance references, without the profile payload."""
    contract_version: Literal_search_requirements_v58['stylist-v2', 'stylist-v3', 'stylist-v4', 'stylist-v5', 'stylist-v6', 'stylist-v7', 'stylist-v8'] | None = None
    interpretations: list[StylistInterpretationV3_search_requirements_v58 | StylistInterpretationV2_search_requirements_v58 | StylistInterpretation_search_requirements_v58]
    resolved_state_ids: list[NonBlankText_search_requirements_v58]
    frozen_profile: dict | None = None
    preference_priorities: list[SearchPreferencePriorityV58_search_requirements_v58] = Field_search_requirements_v58(default_factory=list)

    @model_validator_search_requirements_v58(mode='after')
    def coherent(self):
        ids = self.resolved_state_ids
        if len(ids) != len(set(ids)) or {i.state_id for i in self.interpretations if i.state_id is not None} != set(ids):
            raise ValueError('Search Stylist interpretations must cover resolved states only.')
        row_type = StylistInterpretationV3_search_requirements_v58 if self.contract_version not in {None, 'stylist-v2'} else StylistInterpretationV2_search_requirements_v58 if self.contract_version else StylistInterpretation_search_requirements_v58
        keys = [(getattr(i, 'origin', None), i.state_id, getattr(i, 'preference_interpretation_id', None) if getattr(i, 'origin', None) == 'preference' else None, i.attribute, getattr(i.value, 'key', None)) for i in self.interpretations]
        if len(keys) != len(set(keys)):
            raise ValueError('Combine same-source attribute alternatives into one OR value.')
        for entry in self.interpretations:
            row_type.model_validate(entry.model_dump())
            if entry.preference_evidence_refs and self.contract_version and (not self.frozen_profile):
                raise ValueError('Preference evidence requires its frozen profile reference.')
        priority_ids = [p.interpretation_id for p in self.preference_priorities]
        used_ids = {i.preference_interpretation_id for i in self.interpretations if getattr(i, 'preference_basis', None) == 'profile_interpretation'}
        if len(priority_ids) != len(set(priority_ids)) or not set(priority_ids) <= used_ids:
            raise ValueError('Priority records must uniquely reference used profile interpretations.')
        if priority_ids and (not self.frozen_profile):
            raise ValueError('Preference priority requires its frozen profile reference.')
        return self

@_preserve_function('search_stylist_resolution_v58', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v58')
def search_stylist_resolution_v58_search_requirements_v58(result):
    """Project a validated result; its complete original stays with the orchestrator."""
    if result is None:
        return None
    from copy import deepcopy
    from fashion_recommendation_v2.stylist_context import project_stylist_result
    projection = project_stylist_result(result)
    entries = projection.interpretations
    context = getattr(result, 'personalization_context', None)
    frozen = deepcopy(context.bundle['frozen']) if context and context.bundle and any((i.preference_evidence_refs for i in entries)) else None
    used_ids = {i.preference_interpretation_id for i in entries if getattr(i, 'preference_basis', None) == 'profile_interpretation'}
    claims = context.bundle['profile']['interpretations'] if context and context.bundle else []
    priorities = [{k: deepcopy(claim[k]) for k in SearchPreferencePriorityV58_search_requirements_v58.model_fields} for claim in claims if claim['interpretation_id'] in used_ids]
    return SearchStylistResolutionV58_search_requirements_v58(preference_priorities=priorities, contract_version=getattr(result, 'contract_version', None), interpretations=[i.model_dump() for i in entries], resolved_state_ids=list(projection.resolved_state_ids), frozen_profile=frozen)

@_preserve_class('SearchAgentInputV58', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v58')
class SearchAgentInputV58_search_requirements_v58(SearchAgentInputV57_search_requirements_v58):
    # v57 source semantics remain unchanged; only the transport is compacted.
    compact_stylist_input: ClassVar[bool] = True
    original_stylist_resolution: ClassVar[None] = None
    stylist_resolution: SearchStylistResolutionV58_search_requirements_v58 | None = None

    @model_validator_search_requirements_v58(mode='after')
    def consistent_originals(self):
        from fashion_recommendation_v2.query_composition import validate_composed_input
        validate_composed_input(self)
        for context in (self.audience_context_v1, self.similarity_reference):
            if context and context.user_query != self.original_user_query:
                raise ValueError('Original request snapshots disagree.')
        return self

@_preserve_function('prepare_input', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v58')
def prepare_input_search_requirements_v58(source):
    if isinstance(source, SearchAgentInputV58_search_requirements_v58):
        result = SearchAgentInputV58_search_requirements_v58.model_validate(source.model_dump())
        result.relation_anchor = source.relation_anchor
        return result
    data = source.model_dump() if hasattr(source, 'model_dump') else dict(source)
    compact = data.get('stylist_resolution')
    if 'original_stylist_resolution' not in data and (compact is None or 'frozen_profile' in compact):
        # Standalone historical inputs are validated before the original is removed.
        return SearchAgentInputV58_search_requirements_v58.model_validate_json(json_search_requirements_v58.dumps(data, default=str))
    old = previous_input_search_requirements_v58(SearchAgentInputV57_search_requirements_v58.model_validate_json(json_search_requirements_v58.dumps(data, default=str)) if isinstance(source, dict) else source)
    data = old.model_dump(exclude={'original_stylist_resolution', 'stylist_resolution'})
    data['stylist_resolution'] = search_stylist_resolution_v58_search_requirements_v58(old.stylist_resolution)
    result = SearchAgentInputV58_search_requirements_v58.model_validate(data)
    result.relation_anchor = old.relation_anchor
    return result

@_preserve_function('classification_schema', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_v58')
def classification_schema_search_requirements_v58(conditions, *, relation_conditions=()):
    pairs = comparison_targets_search_requirements_v58(conditions)
    variants = [create_model_search_requirements_v58(f'StylistUserComparisonV58_{i}', __base__=StylistUserComparison_search_requirements_v58, stylist_requirement_id=(Literal_search_requirements_v58[s], ...), user_requirement_id=(Literal_search_requirements_v58[u], ...)) for i, (s, u) in enumerate(pairs)]
    entry = Union_search_requirements_v58[tuple(variants)] if len(variants) > 1 else variants[0] if variants else StylistUserComparison_search_requirements_v58

    @model_validator_search_requirements_v58(mode='after')
    def exact_comparisons(self):
        validate_comparisons_search_requirements_v58(self.stylist_user_comparisons, required_pairs_search_requirements_v58(conditions, self.user_applications))
        return self
    return preserve_response_schema_search_requirements_v58(create_model_search_requirements_v58('RequirementsClassificationV37', __base__=previous_classification_search_requirements_v58(conditions, relation_conditions=relation_conditions), __validators__={'bound_comparisons': exact_comparisons}, stylist_user_comparisons=(list[entry], Field_search_requirements_v58(..., max_length=len(pairs), description='Use only CODE_COMPARISON_TARGETS. Include each listed pair exactly once iff its user ID is classified hard; omit soft-user pairs. Empty when no required pairs.'))))
