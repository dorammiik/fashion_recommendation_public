"""Role-consolidated implementation; service contracts and behavior are preserved."""
from __future__ import annotations
from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function

# ---- summary ----
"""Cold-start recommendation and blocked explanation contracts.

For recommendations, LLM generates RecommendationCopy. Runtime copies IDs/ranks, creates the
response ID, and joins URLs from CandidateSet. Call validate_against before
publishing: standalone validation cannot resolve references to the input.
BlockedSummaryInput / BlockedSummaryCopy / BlockedResponse form a separate
search-free path; reason semantics are prompt/review obligations.
"""

from fashion_recommendation_v2.validation_reuse import validated_once as validated_once_base

from typing import Annotated
from typing import Literal as Literal_base
from typing import Self as Self_base

from pydantic import AliasChoices
from pydantic import Field as Field_base
from pydantic import model_validator as model_validator_base

from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_base
from fashion_recommendation_v2.schemas.search.item_normalization.search_item_normalization import ItemPrice
from fashion_recommendation_v2.schemas.relation import RelationRatio
from fashion_recommendation_v2.schemas.ranking import FinalRanking
from fashion_recommendation_v2.schemas.ranking import RankingAgentInput_base as RankingAgentInput
from fashion_recommendation_v2.schemas.preference_profile import PreferenceProfile
from fashion_recommendation_v2.schemas.search.candidate_pool.search_candidate_pool import CandidateSet


NonBlankText_base = Annotated[str, Field_base(min_length=1, pattern=r"\S")]


@_preserve_class('BlockedReason', 'fashion_recommendation_v2.schemas.summary')
class BlockedReason(StrictBaseModel_base):
    __qualname__ = 'BlockedReason'
    state_id: NonBlankText_base
    reason: NonBlankText_base


@_preserve_class('BlockedSummaryInput', 'fashion_recommendation_v2.schemas.summary')
class BlockedSummaryInput(StrictBaseModel_base):
    __qualname__ = 'BlockedSummaryInput'
    user_request: NonBlankText_base
    blocked_at: Literal_base["request_assessment", "stylist"]
    unresolved_states: list[BlockedReason] = Field_base(min_length=1)

    @model_validator_base(mode="after")
    def validate_ids(self) -> Self_base:
        ids = [entry.state_id for entry in self.unresolved_states]
        if len(ids) != len(set(ids)):
            raise ValueError("Blocked state IDs must be unique.")
        return self


@_preserve_class('BlockedSummaryCopy', 'fashion_recommendation_v2.schemas.summary')
class BlockedSummaryCopy(StrictBaseModel_base):
    __qualname__ = 'BlockedSummaryCopy'
    intro: NonBlankText_base = Field_base(validation_alias=AliasChoices('intro', 'message'))
    reasons: list[BlockedReason] = Field_base(min_length=1)

    def validate_against(self, input_data: BlockedSummaryInput) -> Self_base:
        source = BlockedSummaryInput.model_validate(input_data.model_dump())
        if [entry.state_id for entry in self.reasons] != [
            entry.state_id for entry in source.unresolved_states
        ]:
            raise ValueError("Blocked copy must preserve every state ID in input order.")
        return self


@_preserve_class('BlockedResponse', 'fashion_recommendation_v2.schemas.summary')
class BlockedResponse(BlockedSummaryCopy):
    __qualname__ = 'BlockedResponse'
    response_id: NonBlankText_base
    status: Literal_base["blocked"] = "blocked"


@_preserve_class('OmittedCondition', 'fashion_recommendation_v2.schemas.summary')
class OmittedCondition(StrictBaseModel_base):
    """Orchestrator-owned exclusion evidence, never sent to Search or Ranking."""
    __qualname__ = 'OmittedCondition'
    state_id: NonBlankText_base
    source_text: NonBlankText_base
    reason: NonBlankText_base


@_preserve_class('SummaryAgentInput', 'fashion_recommendation_v2.schemas.summary')
class SummaryAgentInput_base(StrictBaseModel_base):
    __qualname__ = 'SummaryAgentInput'
    ralationRatio: RelationRatio | None = None
    preference_profile: PreferenceProfile | None = None
    preference_category: str | None = None
    interaction_collection_enabled: bool = False
    profile_updates_enabled: bool = False
    user_request: NonBlankText_base
    candidate_set: CandidateSet
    final_ranking: FinalRanking
    omitted_conditions: list[OmittedCondition] = Field_base(default_factory=list)

    @model_validator_base(mode="after")
    @validated_once_base
    def validate_sources(self) -> Self_base:
        if self.profile_updates_enabled and not self.interaction_collection_enabled:
            raise ValueError('Profile updates require interaction collection')
        ids = [entry.state_id for entry in self.omitted_conditions]
        if len(ids) != len(set(ids)):
            raise ValueError('Omitted condition state IDs must be unique.')
        for entry in self.omitted_conditions:
            if entry.source_text not in self.user_request:
                raise ValueError('Omitted source_text must occur in the original user request.')
        candidates = self.candidate_set.candidates
        ids = [candidate.item.item_id for candidate in candidates]
        if self.candidate_set.candidate_count != len(ids) or len(ids) != len(set(ids)):
            raise ValueError("Candidate count and unique item IDs must match.")
        self.final_ranking.validate_against(RankingAgentInput(
            user_request=self.user_request,
            candidate_set=self.candidate_set,
            requested_count=self.final_ranking.requested_count, preference_profile=self.preference_profile,
            preference_category=self.preference_category, ralationRatio=self.ralationRatio,
            relation_intent=self.final_ranking.relation_context_v8,
        ))
        return self


@_preserve_class('RecommendationItemCopy', 'fashion_recommendation_v2.schemas.summary')
class RecommendationItemCopy_base(StrictBaseModel_base):
    __qualname__ = 'RecommendationItemCopy'
    preference_evidence_refs: list[str] = Field_base(default_factory=list)
    """Text and its input reference; URLs are never generated by the LLM."""

    rank: int = Field_base(ge=1)
    item_id: NonBlankText_base
    recommendation_reason: NonBlankText_base
    key_features: list[NonBlankText_base] = Field_base(default_factory=list, max_length=2)


@_preserve_class('RecommendationCopy', 'fashion_recommendation_v2.schemas.summary')
class RecommendationCopy_base(StrictBaseModel_base):
    """LLM output, also usable for deterministic empty-result copy.

Korean copy must preserve evidence limitations/conflicts, never invent product
facts or personal preferences, and describe shortfalls in intro. Those semantic
requirements belong to the prompt/review, not structural schema validation.
"""
    __qualname__ = 'RecommendationCopy'

    intro: NonBlankText_base
    recommendations: list[RecommendationItemCopy_base]
    source_notice: NonBlankText_base
    outro: NonBlankText_base

    @model_validator_base(mode="after")
    def validate_structure(self) -> Self_base:
        if "ebay" not in self.intro.casefold():
            raise ValueError("intro must explicitly name eBay.")
        if "ebay" not in self.source_notice.casefold():
            raise ValueError("source_notice must explicitly name eBay.")
        validate_recommendation_order_base(self.recommendations)
        return self

    def validate_against(self, input_data: SummaryAgentInput_base) -> Self_base:
        source = SummaryAgentInput_base.model_validate(input_data.model_dump())
        for entry in source.omitted_conditions:
            if entry.source_text not in self.intro:
                raise ValueError('intro must name every omitted condition using its source_text.')
        validate_recommendation_references_base(self.recommendations, source)
        return self


@_preserve_class('RecommendationItem', 'fashion_recommendation_v2.schemas.summary')
class RecommendationItem_base(RecommendationItemCopy_base):
    __qualname__ = 'RecommendationItem'
    title: str
    price: ItemPrice | None = None
    # Required keys, nullable values: absent source URLs must remain absent.
    item_web_url: str | None
    image_url: str | None


@_preserve_class('RecommendationResponse', 'fashion_recommendation_v2.schemas.summary')
class RecommendationResponse_base(RecommendationCopy_base):
    __qualname__ = 'RecommendationResponse'
    feedback_notice: str | None = None
    response_id: NonBlankText_base
    recommendations: list[RecommendationItem_base]

    def validate_against(self, input_data: SummaryAgentInput_base) -> Self_base:
        super().validate_against(input_data)
        validate_presentation_base(self, input_data)
        return self


@_preserve_function('feedback_notice', 'fashion_recommendation_v2.schemas.summary')
def feedback_notice_base(source: SummaryAgentInput_base) -> str | None:
    if not source.interaction_collection_enabled or not source.final_ranking.ranked_items:
        return None
    if source.profile_updates_enabled:
        return '좋아요를 보내면 행동 기록이 저장돼요. 취향 프로필은 백그라운드에서 갱신되므로 다음 추천에 아직 반영되지 않을 수 있어요.'
    return '좋아요를 보내면 행동 기록이 저장돼요. 현재 취향 프로필 자동 갱신은 연결되지 않았어요.'


@_preserve_function('validate_recommendation_references', 'fashion_recommendation_v2.schemas.summary')
def validate_recommendation_references_base(recommendations, source):
    expected = [(item.rank, item.item_id) for item in sorted(
        source.final_ranking.ranked_items, key=lambda item: item.rank
    )]
    actual = [(item.rank, item.item_id) for item in recommendations]
    if actual != expected:
        raise ValueError("Recommendations must preserve every FinalRanking item and rank.")
    ranked = {item.item_id: item for item in source.final_ranking.ranked_items}
    for item in recommendations:
        if len(item.preference_evidence_refs) != len(set(item.preference_evidence_refs)) or not set(item.preference_evidence_refs) <= set(ranked[item.item_id].preference_evidence_refs):
            raise ValueError('Summary preference claims must cite actually used ranking evidence')


@_preserve_function('validate_presentation', 'fashion_recommendation_v2.schemas.summary')
def validate_presentation_base(response, input_data, *, notice_factory=feedback_notice_base):
    if response.feedback_notice != notice_factory(input_data):
        raise ValueError('Feedback notice must match connected collection/update capabilities')
    items = {candidate.item.item_id: candidate.item
             for candidate in input_data.candidate_set.candidates}
    for recommendation in response.recommendations:
        item = items[recommendation.item_id]
        if (recommendation.title != item.title
                or recommendation.item_web_url != item.item_web_url
                or recommendation.image_url != item.image_url
                or recommendation.price != item.price):
            raise ValueError("Title, price and product/image URLs must exactly match CandidateSet.")


@_preserve_function('validate_recommendation_order', 'fashion_recommendation_v2.schemas.summary')
def validate_recommendation_order_base(recommendations):
    ids = [item.item_id for item in recommendations]
    if len(ids) != len(set(ids)):
        raise ValueError("Recommendation item IDs must be unique.")
    if [item.rank for item in recommendations] != list(range(1, len(ids) + 1)):
        raise ValueError("Recommendations must be in contiguous rank order starting at 1.")


# ---- summary_v1 ----
"""Summary v1: request/count intro, consolidated remarks, follow-up outro.

Input, item, blocked, reference and presentation contracts remain shared with v0.
Semantic accuracy is evaluated separately from these structural checks.
"""
from fashion_recommendation_v2.validation_reuse import validated_once as validated_once_v1
from typing import Self as Self_v1

from pydantic import model_validator as model_validator_v1

from fashion_recommendation_v2.schemas.base import StrictBaseModel as StrictBaseModel_v1
NonBlankText_v1 = NonBlankText_base
RecommendationItemCopy_v1 = RecommendationItemCopy_base
RecommendationItem_v1 = RecommendationItem_base
SummaryAgentInput_v1 = SummaryAgentInput_base
validate_recommendation_references = validate_recommendation_references_base
validate_presentation_v1 = validate_presentation_base
validate_recommendation_order_v1 = validate_recommendation_order_base


@_preserve_class('RecommendationCopy', 'fashion_recommendation_v2.schemas.summary_v1')
class RecommendationCopy_v1(StrictBaseModel_v1):
    __qualname__ = 'RecommendationCopy'
    intro: NonBlankText_v1
    remarks: NonBlankText_v1
    recommendations: list[RecommendationItemCopy_v1]
    outro: NonBlankText_v1

    @model_validator_v1(mode='after')
    def validate_structure(self) -> Self_v1:
        if 'ebay' not in self.remarks.casefold():
            raise ValueError('remarks must explicitly name eBay.')
        validate_recommendation_order_v1(self.recommendations)
        return self

    @validated_once_v1
    def validate_against(self, input_data: SummaryAgentInput_v1) -> Self_v1:
        source = SummaryAgentInput_v1.model_validate(input_data.model_dump())
        for entry in source.omitted_conditions:
            if entry.source_text not in self.remarks:
                raise ValueError('remarks must name every omitted condition using its source_text.')
        validate_recommendation_references(self.recommendations, source)
        return self


@_preserve_class('RecommendationResponse', 'fashion_recommendation_v2.schemas.summary_v1')
class RecommendationResponse_v1(RecommendationCopy_v1):
    __qualname__ = 'RecommendationResponse'
    feedback_notice: str | None = None
    response_id: NonBlankText_v1
    recommendations: list[RecommendationItem_v1]

    @validated_once_v1
    def validate_against(self, input_data: SummaryAgentInput_v1) -> Self_v1:
        super().validate_against(input_data)
        validate_presentation_v1(self, input_data)
        return self


# ---- summary_v3 ----
"""v3 preserves v1 fields and adds an exact outro for evidenced candidate shortage."""
from fashion_recommendation_v2.validation_reuse import validated_once as validated_once_v3
from typing import Self as Self_v3

SummaryAgentInput_v3 = SummaryAgentInput_base
RecommendationItem_v3 = RecommendationItem_base
NonBlankText_v3 = NonBlankText_base
validate_presentation_v3 = validate_presentation_base
CopyV1 = RecommendationCopy_v1

CANDIDATE_SHORTFALL_REASON = '추천 가능한 후보 수가 요청 개수보다 적어요.'
CANDIDATE_SHORTFALL_OUTRO = '추천 후보 중 마음에 든 후보가 있었나요? 마음에 든 후보가 있었다면 해당 후보와 비슷한 아이템을 좀 더 찾아볼 수 있어요'


@_preserve_function('is_candidate_shortfall', 'fashion_recommendation_v2.schemas.summary_v3')
def is_candidate_shortfall(ranking) -> bool:
    """Conservative scope: the explicit pure-candidate-shortage input reason.

    Unknown/mixed reasons and evaluation failures retain the v2 behavior.
    This recognizes upstream evidence; it does not change the ranking decision.
    """
    return (ranking.status == 'partial'
            and 0 < ranking.returned_count < ranking.requested_count
            and ranking.shortfall_reasons == [CANDIDATE_SHORTFALL_REASON])


@_preserve_class('RecommendationCopy', 'fashion_recommendation_v2.schemas.summary_v3')
class RecommendationCopy_v3(CopyV1):
    __qualname__ = 'RecommendationCopy'
    @validated_once_v3
    def validate_against(self, input_data: SummaryAgentInput_v3) -> Self_v3:
        super().validate_against(input_data)
        if is_candidate_shortfall(input_data.final_ranking) and self.outro != CANDIDATE_SHORTFALL_OUTRO:
            raise ValueError('Candidate shortage outro must exactly equal: ' + CANDIDATE_SHORTFALL_OUTRO)
        return self


@_preserve_class('RecommendationResponse', 'fashion_recommendation_v2.schemas.summary_v3')
class RecommendationResponse_v3(RecommendationCopy_v3):
    __qualname__ = 'RecommendationResponse'
    feedback_notice: str | None = None
    response_id: NonBlankText_v3
    recommendations: list[RecommendationItem_v3]

    @validated_once_v3
    def validate_against(self, input_data: SummaryAgentInput_v3) -> Self_v3:
        super().validate_against(input_data)
        validate_presentation_v3(self, input_data)
        return self


# ---- summary_v2 ----
"""v2 changes outro style only; the exact v1 output/validation contract is reused.

Explicit version exports keep schema/prompt entrypoints aligned without copying
field definitions or adding sentence-match validation for a semantic criterion.
"""
RecommendationCopy_v2 = RecommendationCopy_v1
RecommendationResponse_v2 = RecommendationResponse_v1

__all___v2 = ['RecommendationCopy', 'RecommendationResponse']


# ---- summary_v4 ----
"""v4 keeps the recommendation contract; empty results do not require a source notice."""
from fashion_recommendation_v2.validation_reuse import validated_once as validated_once_v4
from typing import Self as Self_v4

from pydantic import model_validator as model_validator_v4

SummaryAgentInput_v4 = SummaryAgentInput_base
RecommendationItem_v4 = RecommendationItem_base
NonBlankText_v4 = NonBlankText_base
validate_recommendation_order = validate_recommendation_order_base
validate_presentation_v4 = validate_presentation_base
CopyV3 = RecommendationCopy_v3


@_preserve_class('RecommendationCopy', 'fashion_recommendation_v2.schemas.summary_v4')
class RecommendationCopy_v4(CopyV3):
    __qualname__ = 'RecommendationCopy'
    @model_validator_v4(mode='after')
    def validate_structure(self) -> Self_v4:
        # Override v1's unconditional source requirement. Actual count/IDs are
        # still checked against the input, so dropping items cannot bypass it.
        if self.recommendations and 'ebay' not in self.remarks.casefold():
            raise ValueError('remarks must explicitly name eBay when recommendations are present.')
        validate_recommendation_order(self.recommendations)
        return self


@_preserve_class('RecommendationResponse', 'fashion_recommendation_v2.schemas.summary_v4')
class RecommendationResponse_v4(RecommendationCopy_v4):
    __qualname__ = 'RecommendationResponse'
    feedback_notice: str | None = None
    response_id: NonBlankText_v4
    recommendations: list[RecommendationItem_v4]

    @validated_once_v4
    def validate_against(self, input_data: SummaryAgentInput_v4) -> Self_v4:
        super().validate_against(input_data)
        validate_presentation_v4(self, input_data)
        return self


# ---- summary_v5 ----
"""v5 changes only code-assembled feedback notices; generation remains v4."""
from fashion_recommendation_v2.validation_reuse import validated_once as validated_once_v5
from typing import Self as Self_v5

SummaryAgentInput_v5 = SummaryAgentInput_base
legacy_feedback_notice = feedback_notice_base
validate_presentation_v5 = validate_presentation_base
RecommendationCopy_v5 = RecommendationCopy_v4
ResponseV4 = RecommendationResponse_v4

FEEDBACK_NOTICE_OFF = '좋아요를 누르거나 추천 아이템을 클릭한 기록은 저장되고 있어요. 다만 현재는 취향 프로필 자동 갱신이 꺼져 있어, 이 기록을 추천에 반영하기 어려워요. 자동 갱신을 켜면 행동 기록을 바탕으로 취향에 더 잘 맞는 아이템을 추천해드릴게요!'
FEEDBACK_NOTICE_ON = '좋아요를 누르거나 추천 아이템을 클릭한 기록이 저장되고 있어요. 이 기록을 바탕으로 취향 프로필이 자동으로 업데이트되고, 다음 추천부터 반영돼요.'


@_preserve_function('feedback_notice', 'fashion_recommendation_v2.schemas.summary_v5')
def feedback_notice_v5(source: SummaryAgentInput_v5) -> str | None:
    # Preserve the existing collection-enabled/nonempty display gate exactly.
    if legacy_feedback_notice(source) is None:
        return None
    return FEEDBACK_NOTICE_ON if source.profile_updates_enabled else FEEDBACK_NOTICE_OFF


@_preserve_class('RecommendationResponse', 'fashion_recommendation_v2.schemas.summary_v5')
class RecommendationResponse_v5(ResponseV4):
    __qualname__ = 'RecommendationResponse'
    @validated_once_v5
    def validate_against(self, input_data: SummaryAgentInput_v5) -> Self_v5:
        RecommendationCopy_v5.validate_against(self, input_data)
        validate_presentation_v5(self, input_data, notice_factory=feedback_notice_v5)
        return self


# ---- summary_v6 ----
"""v6 adds two grounded follow-up requests; presentation keeps v5 notices."""
from fashion_recommendation_v2.validation_reuse import validated_once
import re
from typing import Self

from pydantic import Field as Field_v6
from pydantic import model_validator as model_validator_v6

NonBlankText = NonBlankText_base
RecommendationItem = RecommendationItem_base
SummaryAgentInput = SummaryAgentInput_base
validate_presentation = validate_presentation_base
CopyV5 = RecommendationCopy_v5
feedback_notice_v6 = feedback_notice_v5


@_preserve_class('RecommendationCopy', 'fashion_recommendation_v2.schemas.summary_v6')
class RecommendationCopy_v6(CopyV5):
    __qualname__ = 'RecommendationCopy'
    next_recommendation: list[NonBlankText] = Field_v6(
        max_length=2,
        description='추천이 있으면 similarity 요청, compatibility 요청 순서로 짧은 사용자 요청 2개. '
                    '각 문구는 실제 N번 추천 하나를 참조한다. 추천이 없으면 빈 목록.',
    )

    @model_validator_v6(mode='after')
    def validate_next_recommendation(self) -> Self:
        expected = 2 if self.recommendations else 0
        if len(self.next_recommendation) != expected:
            raise ValueError(f'next_recommendation must contain {expected} requests.')
        normalized = [' '.join(text.split()) for text in self.next_recommendation]
        if any(not text for text in normalized) or len(set(normalized)) != expected:
            raise ValueError('next_recommendation requests must be nonblank and distinct.')
        ranks = {item.rank for item in self.recommendations}
        for text in self.next_recommendation:
            references = re.findall(r'([0-9]+)\s*번\s*추천', text)
            numbered = re.findall(r'([0-9]+)\s*번', text)
            if len(references) != 1 or numbered != references or int(references[0]) not in ranks:
                raise ValueError('Each next_recommendation must reference one existing rank as N번 추천.')
        return self

    @validated_once
    def validate_against(self, input_data: SummaryAgentInput) -> Self:
        super().validate_against(input_data)
        self.validate_next_recommendation()
        return self


@_preserve_class('RecommendationResponse', 'fashion_recommendation_v2.schemas.summary_v6')
class RecommendationResponse_v6(RecommendationCopy_v6):
    __qualname__ = 'RecommendationResponse'
    feedback_notice: str | None = None
    response_id: NonBlankText
    recommendations: list[RecommendationItem]

    @validated_once
    def validate_against(self, input_data: SummaryAgentInput) -> Self:
        super().validate_against(input_data)
        validate_presentation(self, input_data, notice_factory=feedback_notice_v6)
        return self


# ---- summary_v7 ----
"""v7 selects Luna; recommendation and presentation contracts remain v6."""
RecommendationCopy_v7 = RecommendationCopy_v6
RecommendationResponse_v7 = RecommendationResponse_v6
feedback_notice_v7 = feedback_notice_v6

__all__ = ['RecommendationCopy', 'RecommendationResponse', 'feedback_notice']


# ---- summary_v9 ----
"""v9 input personalization context; unchanged v8 output wire contract."""
from typing import Literal as Literal_v9
from pydantic import model_validator
from pydantic import PrivateAttr
from fashion_recommendation_v2.schemas.base import StrictBaseModel
PreviousCopy = RecommendationCopy_v7
RecommendationResponse_v9 = RecommendationResponse_v7
feedback_notice_v9 = feedback_notice_v7
from fashion_recommendation_v2.schemas.ranking import SelectionKind

@_preserve_class('PersonalizationContext', 'fashion_recommendation_v2.schemas.summary_v9')
class PersonalizationContext(StrictBaseModel):
    __qualname__ = 'PersonalizationContext'
    p_active: bool
    selection_kind: SelectionKind
    inactive_reason: Literal_v9['cold', 'profile_not_found', 'profile_empty', 'no_applicable_preference',
        'insufficient_product_evidence', 'conflicting_product_evidence'] | None

    @model_validator(mode='after')
    def coherent(self):
        if self.p_active != (self.selection_kind == 'personalized'):
            raise ValueError('Selection kind and P activation disagree')
        if self.p_active != (self.inactive_reason is None):
            raise ValueError('Inactive reason and P activation disagree')
        if (self.selection_kind == 'nonpersonalized') != (self.inactive_reason == 'cold'):
            raise ValueError('Cold selection and reason disagree')
        return self


@_preserve_class('RecommendationCopy', 'fashion_recommendation_v2.schemas.summary_v9')
class RecommendationCopy_v9(PreviousCopy):
    """Same output fields; retain transport response separately for v9 audit/retry."""
    __qualname__ = 'RecommendationCopy'
    _model_response: dict | None = PrivateAttr(default=None)
    _model_response_text: str | None = PrivateAttr(default=None)


# ---- summary_v10 ----
"""Request-specific LLM keys; canonical output remains the v9 real-ID contract."""
from typing import Literal
from pydantic import Field
from pydantic import create_model
RecommendationItemCopy = RecommendationItemCopy_base
RecommendationCopy = RecommendationCopy_v9
RecommendationResponse = RecommendationResponse_v9
feedback_notice = feedback_notice_v9


@_preserve_function('response_schema', 'fashion_recommendation_v2.schemas.summary_v10')
def response_schema(reference_keys):
    keys = tuple(reference_keys)
    refs = (list[Literal[keys]], ...) if keys else (list[str], Field(..., max_length=0))
    row = create_model('SummaryItemRefsV10', __base__=RecommendationItemCopy,
                       preference_evidence_refs=refs)
    # Preserve the adapter operation name and any existing model/budget overrides.
    return create_model(RecommendationCopy.__name__, __base__=RecommendationCopy,
                        recommendations=(list[row], ...))
