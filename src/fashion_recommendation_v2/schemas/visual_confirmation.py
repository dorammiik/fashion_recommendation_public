"""Role-consolidated implementation; service contracts and behavior are preserved."""
from __future__ import annotations
from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function

# ---- visual_confirmation_v5 ----
"""Image confirmability is separate from metadata-based requirement satisfaction."""
from typing import Any
from typing import Literal
from math import isclose
from pydantic import Field
from pydantic import model_validator
from pydantic import model_serializer
from fashion_recommendation_v2.schemas.base import StrictBaseModel

VISIBILITY_SCORES = {'met': 1., 'mostly_met': .75, 'partial': .5, 'unknown': .4}
VISUAL_REVIEW_TIMEOUT_SECONDS_V5 = 60
VISUAL_REVIEW_MAX_TIMEOUT_RETRIES_V5 = 1
VisibilityStatus = Literal['met', 'mostly_met', 'partial', 'unknown']


@_preserve_class('VisualRequirementCheckV5', 'fashion_recommendation_v2.schemas.visual_confirmation_v5')
class VisualRequirementCheckV5(StrictBaseModel):
    __qualname__ = 'VisualRequirementCheckV5'
    requirement_id: str
    applicable: bool
    status: VisibilityStatus | None = Field(description=(
        'Visibility only, NOT request satisfaction. A clearly visible mismatch can be met. '
        'met=fully assessable; mostly_met=minor limits; partial=limited cues; '
        'unknown=essential cues hidden. Null iff not applicable.'))
    evidence: str = Field(min_length=1)

    @model_validator(mode='after')
    def check_applicability(self):
        if self.applicable != (self.status is not None) or not self.evidence.strip():
            raise ValueError('Visual checks require a status iff applicable and nonblank evidence.')
        return self


@_preserve_class('VisualConfirmationV5', 'fashion_recommendation_v2.schemas.visual_confirmation_v5')
class VisualConfirmationV5(StrictBaseModel):
    __qualname__ = 'VisualConfirmationV5'
    display_subject: Literal['person', 'mannequin', 'garment_only', 'unknown']
    obstruction_causes: list[Literal['folded', 'cropped', 'occluded', 'poor_visibility']]
    hidden_parts: list[Literal['hem', 'lower_body', 'upper_body', 'sleeves', 'waistline', 'leg_openings', 'silhouette', 'requested_detail']] = Field(
        description='Major obscured garment regions, not absent design details/body/backside. Nonempty forbids full focus and met overall form.')
    overall_form_status: VisibilityStatus = Field(
        description='Visibility of actual garment outline and ends, NOT whether the visible form matches the request.')
    overall_form_evidence: str = Field(min_length=1)
    requirement_checks: list[VisualRequirementCheckV5]

    @model_validator(mode='after')
    def validate_structure(self):
        if not self.overall_form_evidence.strip():
            raise ValueError('Overall form requires nonblank evidence.')
        for values in (self.obstruction_causes, self.hidden_parts, [c.requirement_id for c in self.requirement_checks]):
            if len(values) != len(set(values)):
                raise ValueError('Visibility fields and requirement IDs must be unique.')
        if self.hidden_parts and not self.obstruction_causes:
            raise ValueError('Hidden garment parts require an obstruction cause.')
        return self

    def validate_against(self, requirements):
        if getattr(requirements, 'condition_contract_v26', None) is not None:
            from fashion_recommendation_v2.search.condition_semantics import validate_condition_contract
            validate_condition_contract(requirements)
        expected = {r.requirement_id: r for r in requirements.requirements}
        if {c.requirement_id for c in self.requirement_checks} != set(expected):
            raise ValueError('Visual confirmation must cover every resolved requirement exactly once.')
        for check in self.requirement_checks:
            required = visual_applicability(expected[check.requirement_id], getattr(requirements, 'condition_contract_v26', None))
            if required is not None and check.applicable != required:
                raise ValueError(f'Incorrect visual applicability: {check.requirement_id}')
        return self

    @property
    def score(self):
        return min([VISIBILITY_SCORES[self.overall_form_status],
                    *[VISIBILITY_SCORES[c.status] for c in self.requirement_checks if c.applicable]])


@_preserve_function('visual_applicability', 'fashion_recommendation_v2.schemas.visual_confirmation_v5')
def visual_applicability(requirement, condition_contract=None):
    if condition_contract is not None:
        from fashion_recommendation_v2.search.condition_semantics import applicability
        return applicability(requirement, condition_contract)
    if requirement.unrestricted:
        return False
    if requirement.attribute in {'product_type', 'avoid_product_type', 'color', 'pattern', 'fit', 'sleeve_length'}:
        return True
    if requirement.attribute != 'detail':
        return False  # Price, brand, size, material, season, audience etc. are not visibility gates.
    if not hasattr(requirement.value, 'key'):
        return None  # Historical detail strings need semantic applicability review.
    key = requirement.value.key.casefold().replace('-', '_').replace(' ', '_')
    if key in {'length', 'garment_length', 'skirt_length', 'sleeve_length', 'closure', 'front_closure',
               'neckline', 'hem', 'pocket', 'pockets', 'silhouette', 'waistband', 'fit'}:
        return True
    if key in {'size', 'size_type', 'material', 'fabric_composition', 'care', 'garment_care', 'country_of_origin', 'brand'}:
        return False
    return None  # Other details require the semantic reviewer to check applicability.


@_preserve_class('VisualConfirmationAssessmentV5', 'fashion_recommendation_v2.schemas.visual_confirmation_v5')
class VisualConfirmationAssessmentV5(StrictBaseModel):
    __qualname__ = 'VisualConfirmationAssessmentV5'
    observation: VisualConfirmationV5
    score: float = Field(ge=.4, le=1)

    @classmethod
    def from_observation(cls, observation):
        return cls(observation=observation, score=observation.score)

    @model_validator(mode='after')
    def validate_score(self):
        if not isclose(self.score, self.observation.score, abs_tol=1e-12):
            raise ValueError('V must be the minimum of overall form and applicable visual checks.')
        return self


@_preserve_class('VisualConsistencyDecisionV5', 'fashion_recommendation_v2.schemas.visual_confirmation_v5')
class VisualConsistencyDecisionV5(StrictBaseModel):
    __qualname__ = 'VisualConsistencyDecisionV5'
    status: Literal['consistent', 'inconsistent']
    issues: list[str]
    evidence: str = Field(min_length=1)

    @model_validator(mode='after')
    def validate_decision(self):
        if (self.status == 'inconsistent') != bool(self.issues) or any(not s.strip() for s in self.issues) or not self.evidence.strip():
            raise ValueError('Consistency decision requires coherent issues and nonblank evidence.')
        return self


@_preserve_class('VisualConsistencyAttemptV5', 'fashion_recommendation_v2.schemas.visual_confirmation_v5')
class VisualConsistencyAttemptV5(StrictBaseModel):
    __qualname__ = 'VisualConsistencyAttemptV5'
    product_target_v26: dict[str, Any] | None = None
    product_target_sha256_v26: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    observation_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    observation: dict[str, Any]
    decision: VisualConsistencyDecisionV5 | None
    review_source: Literal['llm', 'code'] = 'llm'
    review_questions: list[str] = Field(default_factory=list)
    review_retry_errors: list[str] = Field(default_factory=list, max_length=VISUAL_REVIEW_MAX_TIMEOUT_RETRIES_V5)

    @model_serializer(mode='wrap')
    def serialize_product_target(self, handler):
        data = handler(self)
        if self.product_target_v26 is None:
            data.pop('product_target_v26', None)
            data.pop('product_target_sha256_v26', None)
        return data

    @model_validator(mode='after')
    def validate_retry_errors(self):
        if (self.product_target_v26 is None) != (self.product_target_sha256_v26 is None):
            raise ValueError('An original product review target requires its snapshot hash.')
        if any(not question.strip() for question in self.review_questions) or len(set(self.review_questions)) != len(self.review_questions):
            raise ValueError('Review questions must be unique and nonblank.')
        if self.review_source == 'code':
            if self.decision is not None or self.review_questions or self.review_retry_errors:
                raise ValueError('A code-only check cannot claim an LLM decision, question or retry.')
        elif self.decision is None:
            raise ValueError('An LLM review requires a decision.')
        if any(not e.startswith('TimeoutError: ') or not e.removeprefix('TimeoutError: ').strip()
               for e in self.review_retry_errors):
            raise ValueError('Only a bounded text-review timeout retry may be recorded.')
        return self


@_preserve_class('VisualConsistencyAuditV5', 'fashion_recommendation_v2.schemas.visual_confirmation_v5')
class VisualConsistencyAuditV5(StrictBaseModel):
    __qualname__ = 'VisualConsistencyAuditV5'
    review_policy: Literal['visual_consistency_v5', 'visual_consistency_v5_conditional', 'product_evaluation_v26_conditional']
    attempts: list[VisualConsistencyAttemptV5] = Field(min_length=1, max_length=2)
    code_repair_errors: list[str] = Field(default_factory=list, max_length=1)

    @model_validator(mode='after')
    def validate_completion(self):
        final = self.attempts[-1]
        if (final.review_source == 'llm' and final.decision.status != 'consistent'
                or any(a.review_source != 'llm' or a.decision.status != 'inconsistent' for a in self.attempts[:-1])):
            raise ValueError('Only completed validation may be used by Ranking.')
        if self.review_policy == 'visual_consistency_v5':
            if any(a.review_source != 'llm' or a.review_questions for a in self.attempts):
                raise ValueError('Legacy audits require unconditional LLM reviews.')
        elif any(a.review_source == 'llm' and not a.review_questions for a in self.attempts):
            raise ValueError('Conditional LLM reviews require explicit questions.')
        if len(self.attempts) + len(self.code_repair_errors) > 2 or any(not e.strip() for e in self.code_repair_errors):
            raise ValueError('At most one image-observation correction is allowed.')
        return self
