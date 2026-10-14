"""Role-consolidated implementation; service contracts and behavior are preserved."""
from __future__ import annotations
from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function

# ---- search_requirements_context_v1 ----
"""Versioned product-audience defaults; inferred scope is never explicit user intent."""


import hashlib
import json
import re
from typing import Literal
from pydantic import Field
from pydantic import model_validator
from fashion_recommendation_v2.schemas.base import StrictBaseModel

REVISION = 'contextual-product-audience-v1'
EVIDENCE_REVISION = 'audience-field-sources-v1-2'
from fashion_recommendation_v2.search.audience_policy import DEFAULTS
from fashion_recommendation_v2.search.audience_policy import PRODUCT_WORDS
from fashion_recommendation_v2.search.audience_policy import resolve_audience_target
CONTEXT_REQUIREMENT_ID = 'context_audience_v1'
_UNBOUND_CONTEXT = object()


@_preserve_function('snapshot_hash', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_context_v1')
def snapshot_hash(value):
    if hasattr(value, 'model_dump'):
        value = value.model_dump(mode='json')
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


@_preserve_class('AudienceReferenceV1', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_context_v1')
class AudienceReferenceV1(StrictBaseModel):
    __qualname__ = 'AudienceReferenceV1'
    item_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    gender: list[Literal['women', 'men', 'unisex']]

    @classmethod
    def from_item(cls, item, search_analysis=None):
        from fashion_recommendation_v2.search.evidence_projection import semantic_values
        from fashion_recommendation_v2.search.evidence_projection import validate_analysis_identity
        validate_analysis_identity(item, search_analysis)
        aliases = {'female': 'women', 'woman': 'women', 'male': 'men', 'man': 'men'}
        observed = semantic_values(search_analysis).get('gender', []) if search_analysis is not None else item.detail.get('gender', [])
        values = [aliases.get(v.strip().lower(), v.strip().lower()) for v in observed]
        return cls(item_id=item.item_id, title=item.title,
                   gender=sorted(set(v for v in values if v in {'women', 'men', 'unisex'})))


@_preserve_class('AudienceContextV1', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_context_v1')
class AudienceContextV1(StrictBaseModel):
    __qualname__ = 'AudienceContextV1'
    version: Literal['v1'] = 'v1'
    user_query: str = Field(min_length=1)
    reference: AudienceReferenceV1 | None = None


@_preserve_class('CategoryAnchorAudienceContextV48', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_context_v1')
class CategoryAnchorAudienceContextV48(AudienceContextV1):
    # Code-derived provenance only; never added to the fixed incoming context.
    __qualname__ = 'CategoryAnchorAudienceContextV48'
    anchor_category: str = Field(min_length=1)
    anchor_category_source: Literal['relation_intent.anchor_category'] = 'relation_intent.anchor_category'


@_preserve_class('AudienceInterpretationV1', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_context_v1')
class AudienceInterpretationV1(StrictBaseModel):
    __qualname__ = 'AudienceInterpretationV1'
    basis: Literal['explicit_request', 'anchor', 'product_default', 'none']
    product_type: Literal['skirt', 'dress', 'high_heels', 'tuxedo'] | None
    source_text: str = Field(min_length=1, description=(
        'Exact contiguous quote ONLY from audience_context_v1.user_query, never the expanded '
        'top-level user_query or reference.title. It identifies the context, not an explicit '
        'gender statement. Service defaults do not require women/men words in the quote.'))
    reason: str = Field(min_length=1)

    @model_validator(mode='after')
    def check_product(self):
        if (self.basis == 'product_default') != (self.product_type is not None):
            raise ValueError('Only product_default requires a listed default product type.')
        return self


@_preserve_class('ContextAudienceRequirementV1', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_context_v1')
class ContextAudienceRequirementV1(StrictBaseModel):
    __qualname__ = 'ContextAudienceRequirementV1'
    requirement_id: Literal['context_audience_v1'] = CONTEXT_REQUIREMENT_ID
    attribute: Literal['gender'] = 'gender'
    value: Literal['women', 'men']
    kind: Literal['hard'] = 'hard'
    source: Literal['context'] = 'context'
    source_text: str = Field(min_length=1)
    evaluation_scope: Literal['search'] = 'search'
    unrestricted: Literal[False] = False


@_preserve_class('ContextGenderDiversityPolicyV1', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_context_v1')
class ContextGenderDiversityPolicyV1(StrictBaseModel):
    __qualname__ = 'ContextGenderDiversityPolicyV1'
    model_config = {'frozen': True}
    required: Literal[False] = False
    exemption: Literal['contextual_audience'] = 'contextual_audience'
    interpreted_product_types: list[str]
    source_texts: list[str] = Field(min_length=1)
    reason: str = Field(min_length=1)


@_preserve_class('AudienceDecisionV1', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_context_v1')
class AudienceDecisionV1(StrictBaseModel):
    __qualname__ = 'AudienceDecisionV1'
    revision: Literal['contextual-product-audience-v1'] = REVISION
    context: AudienceContextV1 | CategoryAnchorAudienceContextV48
    context_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    interpretation: AudienceInterpretationV1
    target_gender: Literal['women', 'men'] | None

    @model_validator(mode='after')
    def check_hash(self):
        if self.context_sha256 != snapshot_hash(self.context):
            raise ValueError('Audience context snapshot hash mismatch.')
        return self


@_preserve_function('check_source_quote', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_context_v1')
def check_source_quote(field, quote, source_path, text):
    if not quote.strip() or quote not in text:
        raise ValueError(json.dumps(dict(code='audience_source_mismatch', field=field,
            rejected_value=quote, required_source=source_path, allowed_source_text=text,
            required_change='Use one exact contiguous quote from required_source. Do not switch source documents.',
            policy_note='Authorized women/men defaults do not require a literal gender word in the request.'),
            ensure_ascii=False))


@_preserve_function('audience_evidence_contract', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_context_v1')
def audience_evidence_contract(source):
    """One field-to-document contract for extraction, audit, repair and code checks."""
    return dict(revision=EVIDENCE_REVISION, sources={
        'user_query': source.user_query,
        'audience_context_v1.user_query': source.audience_context_v1.user_query,
        'audience_context_v1.reference': (source.audience_context_v1.reference.model_dump(mode='json')
            if source.audience_context_v1.reference else None),
    }, field_sources={
        'requirements[source=user].source_text': ['user_query'],
        'requirements[source=user,attribute=gender].source_text': ['user_query', 'audience_context_v1.user_query'],
        'gender_diversity_policy.source_texts (model-authored)': ['user_query'],
        'audience_interpretation.source_text': ['audience_context_v1.user_query'],
        'requirements[source=context].source_text (code-owned)': ['audience_context_v1.user_query'],
        'gender_diversity_policy.source_texts (code-owned contextual_audience)': ['audience_context_v1.user_query'],
        'requirements[source=stylist]': ['stylist_resolution (exact immutable copy)'],
        'requirements[source=reference]': ['similarity_reference (existing immutable reference contract)'],
    }, authorized_product_defaults=dict(DEFAULTS), requires_explicit_gender_for_context_default=False)


@_preserve_function('validate_audience_field_sources', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_context_v1')
def validate_audience_field_sources(source, requirements, interpretation=None):
    """Literal provenance is code-owned; the LLM reviews meaning, not containment."""
    context = source.audience_context_v1
    for r in requirements.requirements:
        if r.source == 'user':
            check_source_quote(f'requirements[{r.requirement_id}].source_text', r.source_text,
                'user_query', source.user_query)
            if r.attribute == 'gender':
                check_source_quote(f'requirements[{r.requirement_id}].source_text', r.source_text,
                    'audience_context_v1.user_query', context.user_query)
    policy = requirements.gender_diversity_policy
    policy_source = ('audience_context_v1.user_query' if policy.exemption == 'contextual_audience' else 'user_query')
    documents = audience_evidence_contract(source)['sources']
    for i, quote in enumerate(policy.source_texts):
        check_source_quote(f'gender_diversity_policy.source_texts[{i}]', quote, policy_source, documents[policy_source])
    if interpretation is not None:
        check_source_quote('audience_interpretation.source_text', interpretation.source_text,
            'audience_context_v1.user_query', context.user_query)


@_preserve_function('decide_audience', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_context_v1')
def decide_audience(context, requirements, interpretation):
    """Model resolves the phrase's role; code owns precedence and default values."""
    check_source_quote('audience_interpretation.source_text', interpretation.source_text,
        'audience_context_v1.user_query', context.user_query)
    target = resolve_audience_target(context, requirements, interpretation)
    return AudienceDecisionV1(context=context, context_sha256=snapshot_hash(context),
        interpretation=interpretation, target_gender=target)




@_preserve_function('validate_audience_requirements', 'fashion_recommendation_v2.schemas.search.requirements.search_requirements_context_v1')
def validate_audience_requirements(requirements, context=_UNBOUND_CONTEXT):
    decision = requirements.audience_policy_v1
    contextual = [r for r in requirements.requirements if r.source == 'context']
    policy = requirements.gender_diversity_policy
    if decision is None:
        if contextual or (policy and policy.exemption == 'contextual_audience'):
            raise ValueError('Contextual audience requires a versioned, evidenced decision.')
        if context is not _UNBOUND_CONTEXT and context is not None:
            raise ValueError('The v1 request is missing its audited audience decision.')
        return requirements
    if context is not _UNBOUND_CONTEXT and context != decision.context:
        raise ValueError('Audience decision belongs to another request/anchor.')
    expected = decide_audience(decision.context, requirements, decision.interpretation)
    if expected != decision:
        raise ValueError('Audience target differs from the code-owned default/anchor precedence.')
    if decision.target_gender:
        expected_requirement = ContextAudienceRequirementV1(value=decision.target_gender,
            source_text=decision.interpretation.source_text)
        if contextual != [expected_requirement] or not isinstance(policy, ContextGenderDiversityPolicyV1):
            raise ValueError('Contextual audience must be one hard/search constraint with diversity exempted.')
        if policy.source_texts != [decision.interpretation.source_text]:
            raise ValueError('Contextual diversity evidence differs from the audience decision.')
    elif contextual or isinstance(policy, ContextGenderDiversityPolicyV1):
        raise ValueError('No contextual constraint may survive an explicit override or absent default.')
    return requirements
