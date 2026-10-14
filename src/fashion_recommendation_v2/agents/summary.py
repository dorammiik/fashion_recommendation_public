"""Validate ranking references, generate copy, and join original presentation URLs."""
from __future__ import annotations
from fashion_recommendation_v2.module_compat import import_module as _role_module
from fashion_recommendation_v2.validation_reuse import reuse_for
from fashion_recommendation_v2.validation_reuse import measure_processing

from copy import deepcopy
from typing import Any
from typing import Literal
from typing import TYPE_CHECKING
from uuid import uuid4

from pydantic import Field

from fashion_recommendation_v2.llm.base import StructuredLLM
from fashion_recommendation_v2.prompts.summary import summary__SUMMARY_PROMPT as SUMMARY_PROMPT
from fashion_recommendation_v2.prompts.summary import BLOCKED_SUMMARY_PROMPT
from fashion_recommendation_v2.schemas.base import StrictBaseModel
from fashion_recommendation_v2.schemas.search.requirements.search_requirements import ResolvedRequirements_legacy as ResolvedRequirements
from fashion_recommendation_v2.schemas.summary import RecommendationCopy_base as RecommendationCopy
from fashion_recommendation_v2.schemas.summary import RecommendationResponse_base as RecommendationResponse
from fashion_recommendation_v2.schemas.summary import SummaryAgentInput_base as SummaryAgentInput
from fashion_recommendation_v2.schemas.summary import BlockedSummaryInput
from fashion_recommendation_v2.schemas.summary import BlockedSummaryCopy
from fashion_recommendation_v2.schemas.summary import BlockedResponse
from fashion_recommendation_v2.schemas.summary import OmittedCondition
from fashion_recommendation_v2.schemas.summary import feedback_notice_base as feedback_notice


if TYPE_CHECKING:
    from fashion_recommendation_v2.schemas.summary import RecommendationCopy_v1 as RecommendationCopyV1
    from fashion_recommendation_v2.schemas.summary import RecommendationResponse_v1 as RecommendationResponseV1
    from fashion_recommendation_v2.schemas.summary import RecommendationResponse_v3 as RecommendationResponseV3
    from fashion_recommendation_v2.schemas.summary import RecommendationCopy_v4 as RecommendationCopyV4
    from fashion_recommendation_v2.schemas.summary import RecommendationResponse_v4 as RecommendationResponseV4
    from fashion_recommendation_v2.schemas.summary import RecommendationResponse_v6 as RecommendationResponseV6


class BlockedSummaryGenerationInput(BlockedSummaryInput):
    validation_feedback: list[str] = Field(default_factory=list)
    failure_context: list[str] = Field(default_factory=list)


class SummaryCopyInput(StrictBaseModel):
    interaction_collection_enabled: bool = False
    profile_updates_enabled: bool = False
    user_request: str
    resolved_requirements: ResolvedRequirements
    requested_count: int
    returned_count: int
    status: Literal['complete', 'partial', 'empty']
    items: list[dict[str, Any]]
    shortfall_reasons: list[str]
    omitted_conditions: list[OmittedCondition] = Field(default_factory=list)
    relation_warnings: list[str] = Field(default_factory=list)
    validation_feedback: list[str] = Field(default_factory=list)


class SummaryExecutionError(RuntimeError):
    def __init__(self, *, code: str, message: str, attempts: list[dict]):
        self.code = code
        self.retry_count = len(attempts) - 1
        self.attempts = [dict(attempt) for attempt in attempts]
        super().__init__(f'{code}: {message}')


# Presentation fields, raw search history, scores and normalization diagnostics
# are deliberately not included in the copy-generation payload.
COPY_FIELDS = {
    'title', 'category_path', 'condition', 'condition_description', 'color',
    'size', 'fit', 'material', 'pattern', 'brand', 'strength', 'garment_care',
    'theme', 'season', 'occasion', 'detail',
}


def _preference_support(source, ranked):
    record = source.final_ranking.personalization_v12 or source.final_ranking.personalization_v11
    if record is not None:
        entry = record['items'].get(ranked.item_id, {})
        if not entry.get('p_active') or not record.get('bundle'):
            return []
        claims = {i['interpretation_id']: i for i in record['bundle']['profile']['interpretations']}
        return [dict(interpretation_id=a['interpretation_id'], preference=claims[a['interpretation_id']]['preference'],
            direction=claims[a['interpretation_id']]['direction'], judgment=a['judgment'],
            uncertainty=claims[a['interpretation_id']]['uncertainty'], explanation=a['explanation'],
            evidence_refs=sorted(set(ranked.preference_evidence_refs) & set(
                claims[a['interpretation_id']]['supporting_evidence_refs'] + claims[a['interpretation_id']]['counter_evidence_refs'])),
            basis='inferred_from_item_interactions')
            for a in entry['assessment']['interpretation_assessments'] if a['judgment'] in {'supports','opposes','neutral'}]
    from fashion_recommendation_v2.schemas.ranking import RankingAgentInput_base as RankingAgentInput
    from fashion_recommendation_v2.agents.ranking_preferences import request_profile
    from fashion_recommendation_v2.agents.preference_scoring import combined
    profile = request_profile(RankingAgentInput(
        candidate_set=source.candidate_set, user_request=source.user_request,
        requested_count=source.final_ranking.requested_count, preference_profile=source.preference_profile,
        preference_category=source.preference_category))
    if profile is None:
        return []
    refs = set(ranked.preference_evidence_refs)
    support = []
    for feature in [*profile.global_preferences.features, *profile.global_preferences.title_keywords]:
        used = refs & set(feature.evidence_refs)
        if used:
            support.append(dict(attribute=getattr(feature, 'attribute', 'title_keywords'),
                value=(feature.value.model_dump() if hasattr(feature.value, 'model_dump') else feature.value)
                      if hasattr(feature, 'value') else feature.normalized,
                direction='positive' if combined(feature)>0 else 'negative' if combined(feature)<0 else 'mixed',
                evidence_refs=sorted(used), basis='inferred_from_item_interactions'))
    return support


def _copy_input(source: SummaryAgentInput, *, version=None) -> SummaryCopyInput:
    ranking = source.final_ranking
    items = {candidate.item.item_id: candidate.item for candidate in source.candidate_set.candidates}
    analyses = {c.item.item_id: (c.search_analysis if source.candidate_set.search_policy_version in {'v26', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'} else None)
                for c in source.candidate_set.candidates}
    from fashion_recommendation_v2.search.evidence_projection import semantic_projection
    projected = []
    for ranked in sorted(ranking.ranked_items, key=lambda item: item.rank):
        assessments = []
        for assessment in ranked.requirement_assessments:
            assessments.append(dict(
                requirement_id=assessment.requirement_id, status=assessment.status,
                evidence_fields=assessment.evidence_fields, evidence=assessment.evidence,
                image_observations=[entry.observation for entry in assessment.image_evidence],
            ))
        conflicts = [dict(
            attribute=entry.attribute, requirement_id=entry.requirement_id,
            evidence_fields=entry.evidence_fields, metadata_evidence=entry.metadata_evidence,
            image_observations=[image.observation for image in entry.image_evidence],
            explanation=entry.explanation,
        ) for entry in ranked.conflicts]
        projected.append(dict(
            item_id=ranked.item_id, rank=ranked.rank,
            preference_support=_preference_support(source, ranked),
            relation_evaluation=ranked.relation_evaluation.model_dump() if ranked.relation_evaluation else None,
            relation_anchor=source.ralationRatio.intent.model_dump() if source.ralationRatio else None,
            preference_observations=[dict(attribute=o.attribute,
                value=o.value.model_dump() if hasattr(o.value, 'model_dump') else o.value,
                evidence_fields=o.evidence_fields, evidence=o.evidence,
                image_observations=[e.observation for e in o.image_evidence])
                for o in ranked.preference_observations],
            metadata=items[ranked.item_id].model_dump(include=(
                {'title', 'category_path', 'condition', 'condition_description'}
                if analyses[ranked.item_id] is not None else COPY_FIELDS), exclude_none=True),
            **({'search_analysis': semantic_projection(analyses[ranked.item_id])}
                if analyses[ranked.item_id] is not None else {}),
            hard_constraint_assessments=[entry.model_dump() for entry in ranked.hard_constraint_assessments],
            requirement_assessments=assessments, conflicts=conflicts,
            uncertainties=ranked.uncertainties,
        ))
    if version in {'v9', 'v10', 'v11'}:
        from fashion_recommendation_v2.summary.personalization_v9 import attach_context
        attach_context(source, projected)
    return SummaryCopyInput(
        interaction_collection_enabled=source.interaction_collection_enabled,
        profile_updates_enabled=source.profile_updates_enabled,
        user_request=source.user_request,
        resolved_requirements=source.candidate_set.resolved_requirements,
        requested_count=ranking.requested_count, returned_count=ranking.returned_count,
        status=ranking.status, items=projected, shortfall_reasons=ranking.shortfall_reasons,
        omitted_conditions=source.omitted_conditions,
        relation_warnings=source.ralationRatio.warnings if source.ralationRatio else [],
    )


_EMPTY_REASONS = {
    'hard_requirement_unmet': '필수 조건에 맞지 않는 상품이 있었어요.',
    'hard_requirement_unknown': '필수 조건 충족 여부를 확인할 정보가 부족한 상품이 있었어요.',
    'below_minimum_relevance': '요청과의 적합도가 추천 기준에 미치지 못한 상품이 있었어요.',
    'hard_requirement_conflict': '상품 정보와 평가 근거에서 필수 조건 위반이 확인된 상품이 있었어요.',
    'evaluation_failed': '일부 상품의 평가 처리에 실패했어요.',
}


def _empty_reasons(source: SummaryAgentInput) -> list[str]:
    reasons = []
    if not source.candidate_set.candidates:
        reasons.append('검색에서 반환된 상품이 없어요.')
    codes = {code for item in source.final_ranking.excluded_items for code in item.reason_codes}
    reasons.extend(text for code, text in _EMPTY_REASONS.items() if code in codes)
    if not reasons:
        reasons.extend(source.final_ranking.shortfall_reasons)
    return reasons


def _empty_copy(source: SummaryAgentInput) -> RecommendationCopy:
    reasons = _empty_reasons(source)
    return RecommendationCopy(
        intro=(f'요청하신 조건으로 상품을 찾아봤지만, 요청하신 {source.final_ranking.requested_count}개 중 '
               '추천할 수 있는 상품은 0개예요. ' + ' '.join(reasons) + ' eBay 검색 결과를 바탕으로 찾아봤어요.'),
        recommendations=[], source_notice='상품 정보는 eBay 검색 결과를 바탕으로 안내해 드려요.',
        outro='원하시는 조건을 조금 바꿔서 다시 찾아보셔도 좋아요.',
    )


def _empty_copy_v1(source: SummaryAgentInput):
    from fashion_recommendation_v2.schemas.summary import RecommendationCopy_v1 as CopyV1
    reasons = _empty_reasons(source)
    return CopyV1(
        intro=(f'요청하신 조건으로 상품을 찾아봤지만, 요청하신 {source.final_ranking.requested_count}개 중 '
               '추천할 수 있는 상품은 0개예요.'),
        remarks=' '.join([*reasons, '상품 정보는 eBay 검색 결과를 바탕으로 안내해 드려요.']),
        recommendations=[],
        outro='조건을 조정해 다시 요청하신다면, 꼭 유지하고 싶은 조건과 바꿔도 되는 조건을 알려주실래요?',
    )


def _empty_copy_v4(source: SummaryAgentInput):
    """Code-only empty copy; use upstream reasons without diagnosing new causes."""
    from fashion_recommendation_v2.schemas.summary import RecommendationCopy_v4 as CopyV4
    # Translate only a single, explicit resolved product type. Unknown/OR types
    # retain the neutral label instead of reinterpreting the user's request.
    labels = {'dress': '원피스', 'skirt': '스커트', 'shirt': '셔츠', 'trench coat': '트렌치 코트',
              'pants': '바지', 't-shirt': '티셔츠', 'jacket': '재킷', 'coat': '코트'}
    types = [r.value for r in source.candidate_set.resolved_requirements.requirements
             if r.attribute == 'product_type']
    label = labels.get(types[0], '상품') if len(types) == 1 and isinstance(types[0], str) else '상품'
    object_name = label + ('을' if (ord(label[-1]) - 0xAC00) % 28 else '를')
    candidates = source.candidate_set.candidates
    failures = {entry.item_id for entry in source.final_ranking.excluded_items
                if 'evaluation_failed' in entry.reason_codes}
    all_failed = bool(candidates) and all(c.item.item_id in failures for c in candidates)
    if not candidates:
        remarks = ('검색에서 반환된 후보 상품이 없어 추천할 상품을 고르지 못했어요. '
                   '제공된 결과만으로는 후보가 없었던 구체적인 이유를 확인하기 어려워요.')
        outro = f'어떤 {object_name} 원하시는지 좀 더 구체적으로 설명해주시면 다시 검색해볼게요.'
    elif all_failed:
        remarks = '후보 상품은 있었지만 모든 후보의 평가 처리에 실패해 추천을 확정하지 못했어요.'
        outro = '상품 평가 처리에 실패한 경우라, 원하시면 같은 조건으로 다시 검색해볼게요.'
    else:
        remarks = ' '.join(_empty_reasons(source)) or '제공된 평가 결과에서 추천을 확정할 수 있는 상품이 없어요.'
        outro = '우선할 조건이나 조정할 수 있는 조건을 말씀해주시면 다시 검색해볼게요.'
    return CopyV4(intro=f'조건에 맞는 {object_name} 찾지 못했어요.', remarks=remarks,
                  recommendations=[], outro=outro)


class SummaryAgent:
    def __init__(self, *, llm: StructuredLLM, version: Literal['v0', 'v1', 'v2', 'v3', 'v4', 'v5', 'v6', 'v7', 'v8', 'v9', 'v10', 'v11'] = 'v0'):
        if version not in {'v0', 'v1', 'v2', 'v3', 'v4', 'v5', 'v6', 'v7', 'v8', 'v9', 'v10', 'v11'}:
            raise ValueError(f'Unknown Summary version: {version}')
        self.version = version
        self.copy_schema = RecommendationCopy
        self.response_schema = RecommendationResponse
        self.summary_prompt = SUMMARY_PROMPT
        self.feedback_notice = feedback_notice
        if version == 'v1':
            from fashion_recommendation_v2.schemas.summary import RecommendationCopy_v1 as CopyV1
            from fashion_recommendation_v2.schemas.summary import RecommendationResponse_v1 as ResponseV1
            from fashion_recommendation_v2.prompts.summary import summary_v1__SUMMARY_PROMPT as PROMPT_V1
            self.copy_schema = CopyV1
            self.response_schema = ResponseV1
            self.summary_prompt = PROMPT_V1
        elif version == 'v2':
            from fashion_recommendation_v2.schemas.summary import RecommendationCopy_v2 as CopyV2
            from fashion_recommendation_v2.schemas.summary import RecommendationResponse_v2 as ResponseV2
            from fashion_recommendation_v2.prompts.summary import summary_v2__SUMMARY_PROMPT as PROMPT_V2
            self.copy_schema = CopyV2
            self.response_schema = ResponseV2
            self.summary_prompt = PROMPT_V2
        elif version == 'v3':
            from fashion_recommendation_v2.schemas.summary import RecommendationCopy_v3 as CopyV3
            from fashion_recommendation_v2.schemas.summary import RecommendationResponse_v3 as ResponseV3
            from fashion_recommendation_v2.prompts.summary import summary_v3__SUMMARY_PROMPT as PROMPT_V3
            self.copy_schema = CopyV3
            self.response_schema = ResponseV3
            self.summary_prompt = PROMPT_V3
        elif version == 'v4':
            from fashion_recommendation_v2.schemas.summary import RecommendationCopy_v4 as CopyV4
            from fashion_recommendation_v2.schemas.summary import RecommendationResponse_v4 as ResponseV4
            from fashion_recommendation_v2.prompts.summary import summary_v4__SUMMARY_PROMPT as PROMPT_V4
            self.copy_schema = CopyV4
            self.response_schema = ResponseV4
            self.summary_prompt = PROMPT_V4
        elif version == 'v5':
            from fashion_recommendation_v2.schemas.summary import RecommendationCopy_v5 as CopyV5
            from fashion_recommendation_v2.schemas.summary import RecommendationResponse_v5 as ResponseV5
            from fashion_recommendation_v2.schemas.summary import feedback_notice_v5 as notice_v5
            from fashion_recommendation_v2.prompts.summary import summary_v4__SUMMARY_PROMPT as PROMPT_V5
            self.copy_schema = CopyV5
            self.response_schema = ResponseV5
            self.summary_prompt = PROMPT_V5
            self.feedback_notice = notice_v5
        elif version == 'v6':
            from fashion_recommendation_v2.schemas.summary import RecommendationCopy_v6 as CopyV6
            from fashion_recommendation_v2.schemas.summary import RecommendationResponse_v6 as ResponseV6
            from fashion_recommendation_v2.schemas.summary import feedback_notice_v6 as notice_v6
            from fashion_recommendation_v2.prompts.summary import summary_v6__SUMMARY_PROMPT as PROMPT_V6
            self.copy_schema = CopyV6
            self.response_schema = ResponseV6
            self.summary_prompt = PROMPT_V6
            self.feedback_notice = notice_v6
        elif version in {'v7', 'v8'}:
            from fashion_recommendation_v2.schemas.summary import RecommendationCopy_v7 as CopyV7
            from fashion_recommendation_v2.schemas.summary import RecommendationResponse_v7 as ResponseV7
            from fashion_recommendation_v2.schemas.summary import feedback_notice_v7 as notice_v7
            from fashion_recommendation_v2.prompts.summary import summary_v6__SUMMARY_PROMPT as PROMPT_V7
            self.copy_schema = CopyV7
            self.response_schema = ResponseV7
            self.summary_prompt = PROMPT_V7
            self.feedback_notice = notice_v7
        if version in {'v9', 'v10', 'v11'}:
            from fashion_recommendation_v2.schemas.summary import RecommendationCopy_v9 as CopyV9
            from fashion_recommendation_v2.schemas.summary import RecommendationResponse_v9 as ResponseV9
            from fashion_recommendation_v2.schemas.summary import feedback_notice_v9 as notice_v9
            from fashion_recommendation_v2.prompts.summary import PREVIOUS_PROMPT as PROMPT_V9
            self.copy_schema, self.response_schema = CopyV9, ResponseV9
            self.summary_prompt, self.feedback_notice = PROMPT_V9, notice_v9
        if version in {'v10', 'v11'}:
            from fashion_recommendation_v2.prompts.summary import SUMMARY_PROMPT as PROMPT_V10
            self.summary_prompt = PROMPT_V10
        self.llm = llm
        self.generation_attempts: list[dict] = []

    def run_blocked(self, input_data: BlockedSummaryInput) -> BlockedResponse:
        """Explain an orchestrator decision without search or ranking inputs."""
        return self._run_blocked(input_data, failure_context=[], max_attempts=2)

    def run_blocked_fallback(self, input_data: BlockedSummaryInput, *, failure_context: list[str]) -> BlockedResponse:
        """One final LLM attempt, preserving original reasons; never recurse."""
        return self._run_blocked(input_data, failure_context=failure_context, max_attempts=1)

    def _run_blocked(self, input_data, *, failure_context, max_attempts):
        self.generation_attempts = []
        source = BlockedSummaryInput.model_validate(input_data.model_dump())
        feedback: list[str] = []
        for retry in range(max_attempts):
            request = BlockedSummaryGenerationInput(
                **source.model_dump(), validation_feedback=feedback, failure_context=failure_context,
            )
            code = 'api_error'
            result = None
            try:
                result = self.llm.generate(
                    system_prompt=BLOCKED_SUMMARY_PROMPT, user_input=request,
                    output_schema=BlockedSummaryCopy,
                )
                code = 'invalid_response'
                if not isinstance(result, BlockedSummaryCopy):
                    raise ValueError('Expected a BlockedSummaryCopy structured response.')
                copy = BlockedSummaryCopy.model_validate(result.model_dump()).validate_against(source)
            except Exception as exc:
                if isinstance(exc, (ValueError, TypeError)):
                    code = 'invalid_response'
                message = str(exc) or type(exc).__name__
                self.generation_attempts.append(dict(
                    retry_count=retry, status='error', code=code,
                    error_type=type(exc).__name__, message=message,
                ))
                if retry == max_attempts - 1:
                    raise SummaryExecutionError(
                        code=code, message=message, attempts=self.generation_attempts,
                    ) from exc
                feedback = [message] if code == 'invalid_response' else []
            else:
                self.generation_attempts.append(dict(retry_count=retry, status='success'))
                return BlockedResponse(
                    response_id=f'response_{uuid4().hex}', **copy.model_dump(),
                ).validate_against(source)
        raise AssertionError('unreachable')

    @reuse_for('summary')
    def run(self, input_data: SummaryAgentInput) -> RecommendationResponse | RecommendationResponseV1 | RecommendationResponseV3 | RecommendationResponseV4 | RecommendationResponseV6:
        self.generation_attempts = []
        # Revalidate mutable model instances and work on a detached snapshot.
        with measure_processing('summary.input_reconstruction_validation'):
            source = SummaryAgentInput.model_validate(input_data.model_dump())
        if source.final_ranking.status == 'empty' and not source.omitted_conditions:
            if self.version in {'v6', 'v7', 'v8', 'v9', 'v10', 'v11'}:
                copy = self.copy_schema(**_empty_copy_v4(source).model_dump(), next_recommendation=[]).validate_against(source)
            elif self.version in {'v4', 'v5'}:
                copy = _empty_copy_v4(source).validate_against(source)
            else:
                copy = (_empty_copy_v1(source) if self.version in {'v1', 'v2', 'v3'} else _empty_copy(source)).validate_against(source)
        else:
            copy = self._generate(source)
        items = {candidate.item.item_id: candidate.item for candidate in source.candidate_set.candidates}
        response = self.response_schema(
            feedback_notice=self.feedback_notice(source),
            response_id=f'response_{uuid4().hex}',
            **copy.model_dump(exclude={'recommendations'}),
            recommendations=[entry.model_dump() | dict(
                title=items[entry.item_id].title,
                price=items[entry.item_id].price.model_copy(deep=True) if items[entry.item_id].price is not None else None,
                item_web_url=items[entry.item_id].item_web_url,
                image_url=items[entry.item_id].image_url,
            ) for entry in copy.recommendations],
        )
        with measure_processing('summary.response_validation'):
            return response.validate_against(source)

    def _generate(self, source: SummaryAgentInput) -> RecommendationCopy | RecommendationCopyV1 | RecommendationCopyV4:
        request = _copy_input(source, version=self.version)
        mapping = None
        output_schema = self.copy_schema
        if self.version in {'v10', 'v11'}:
            from fashion_recommendation_v2.summary.evidence_references import reference_map
            from fashion_recommendation_v2.summary.evidence_references import project_references
            from fashion_recommendation_v2.summary.evidence_references import resolve_references
            from fashion_recommendation_v2.schemas.summary import response_schema
            mapping = reference_map(source)
            request = project_references(request, mapping)
            output_schema = response_schema(mapping['key_to_id'])
        initial_request = request.model_copy(deep=True)
        for retry in range(2):
            # API failures and copy-validation failures remain distinct. As with
            # Ranking, transient API failures receive at most one retry too.
            code = 'api_error'
            result = None
            try:
                result = self.llm.generate(
                    system_prompt=self.summary_prompt, user_input=request,
                    output_schema=output_schema,
                )
                code = 'invalid_response'
                if not isinstance(result, self.copy_schema):
                    raise ValueError('Expected a RecommendationCopy structured response.')
                payload = result.model_dump()
                if mapping is not None:
                    # Revalidate even mutable/mock instances before joining IDs.
                    raw_payload = getattr(result, '_model_response', None)
                    if raw_payload is not None:
                        payload = deepcopy(raw_payload)
                    output_schema.model_validate(payload)
                    payload = resolve_references(payload, mapping)
                with measure_processing('summary.copy_validation'):
                    copy = self.copy_schema.model_validate(payload).validate_against(source)
            except Exception as exc:
                # Adapter-side Pydantic parsing errors are response errors too.
                if isinstance(exc, (ValueError, TypeError)):
                    code = 'invalid_response'
                message = str(exc) or type(exc).__name__
                self.generation_attempts.append(dict(
                    retry_count=retry, status='error', code=code,
                    error_type=type(exc).__name__, message=message,
                ))
                if self.version in {'v9', 'v10', 'v11'}:
                    raw = getattr(result, '_model_response', None)
                    if raw is None and result is not None:
                        raw = result.model_dump(mode='json') if hasattr(result, 'model_dump') else deepcopy(result)
                    snapshot = getattr(exc, 'response_snapshot', {}) or {}
                    self.generation_attempts[-1].update(model_response=deepcopy(raw if raw is not None else snapshot.get('model_response')), model_response_text=getattr(result, '_model_response_text', None) or snapshot.get('model_response_text'), response_snapshot=deepcopy(snapshot), code_validation={'valid': False, 'error': message})
                if mapping is not None:
                    self.generation_attempts[-1].update(reference_map=deepcopy(mapping),
                        summary_version=self.version, attempt_id=retry, corrects_attempt=retry - 1 if retry else None,
                        code_derived=None)
                if retry == 1:
                    raise SummaryExecutionError(
                        code=code, message=message, attempts=self.generation_attempts,
                    ) from exc
                request = initial_request.model_copy(deep=True) if mapping is not None else _copy_input(source, version=self.version)
                if code == 'invalid_response':
                    request.validation_feedback = [message]
            else:
                self.generation_attempts.append(dict(retry_count=retry, status='success'))
                if self.version in {'v9', 'v10', 'v11'}:
                    raw = getattr(result, '_model_response', None)
                    self.generation_attempts[-1].update(model_response=deepcopy(raw if raw is not None else result.model_dump(mode='json')), model_response_text=getattr(result, '_model_response_text', None), code_validation={'valid': True})
                if mapping is not None:
                    self.generation_attempts[-1].update(reference_map=deepcopy(mapping),
                        summary_version=self.version, attempt_id=retry, corrects_attempt=retry - 1 if retry else None,
                        code_derived=copy.model_dump(mode='json'))
                return copy
        raise AssertionError('unreachable')
