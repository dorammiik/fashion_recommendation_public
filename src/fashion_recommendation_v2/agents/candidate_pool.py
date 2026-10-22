"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- candidate_pool ----

import re
from fashion_recommendation_v2.tools.age_scope import excluded_childrenswear
import unicodedata
from uuid import uuid4
from fashion_recommendation_v2.schemas.search.candidate_pool.search_candidate_pool import Candidate
from fashion_recommendation_v2.schemas.search.candidate_pool.search_candidate_pool import CandidatePool
from fashion_recommendation_v2.schemas.search.candidate_pool.search_candidate_pool import CandidateSet
from fashion_recommendation_v2.schemas.search.candidate_pool.search_candidate_pool import CandidateSource
from fashion_recommendation_v2.schemas.search.candidate_pool.search_candidate_pool import RetrievalSignals
from fashion_recommendation_v2.schemas.search.candidate_pool.search_candidate_pool import SearchIssue
from fashion_recommendation_v2.schemas.search.candidate_pool.search_candidate_pool import SearchAttempt
from fashion_recommendation_v2.schemas.search.candidate_pool.search_candidate_pool import SearchBudget
from fashion_recommendation_v2.schemas.search.retrieval.search_retrieval import ProductRecord
from fashion_recommendation_v2.schemas.search.requirements.search_requirements import ResolvedRequirements_legacy as ResolvedRequirements
from fashion_recommendation_v2.schemas.search.planning.search_planning import SearchInspection
from fashion_recommendation_v2.schemas.search.planning.search_planning import SearchQueryPlan
from fashion_recommendation_v2.schemas.common import EBayRawItem

@_preserve_function('normalize_title_key', 'fashion_recommendation_v2.agents.candidate_pool')
def normalize_title_key(title: str) -> str:
    """
    Candidate title dedup용 deterministic key.

    Unicode normalization, casefold, punctuation 제거,
    whitespace normalization을 적용한다.

    "MAX MARA  Black-Trousers"와 "Max Mara Black Trousers"는
    "max mara black trousers"로 정규화된다.
    """
    normalized = unicodedata.normalize("NFKC", title).casefold()
    normalized = re.sub(r"[\W_]+", " ", normalized, flags=re.UNICODE)
    return " ".join(normalized.split())

@_preserve_class('CandidatePoolManager', 'fashion_recommendation_v2.agents.candidate_pool')
class CandidatePoolManager:
    """
    Search Agent 내부 CandidatePool 상태를 관리한다.

    담당:
    - CandidatePool 초기화
    - NormalizedItem 추가
    - item_id, normalized title 및 동일한 image_url 기준 dedup
    - CandidateSource 누적
    - retrieval_signals 갱신
    - SearchAttempt 기록
    - minimum relevance quality 계산
    - target reached 계산
    - CandidateSet 생성

    담당하지 않음:
    - eBay 검색
    - Item Mapping
    - LLM Result Inspection
    - Strategy Revision
    """

    def __init__(self, *, requested_count: int, max_attempts: int, minimum_search_attempts: int=1, resolved_requirements: ResolvedRequirements | None=None, target_candidate_count: int | None=None) -> None:
        if requested_count < 1:
            raise ValueError("requested_count must be >= 1.")
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1.")
        if minimum_search_attempts < 1:
            raise ValueError("minimum_search_attempts must be >= 1.")
        if minimum_search_attempts > max_attempts:
            raise ValueError('minimum_search_attempts cannot exceed max_attempts.')
        self.minimum_search_attempts = minimum_search_attempts
        self.requested_count = requested_count
        if target_candidate_count is not None and target_candidate_count < requested_count:
            raise ValueError("target_candidate_count must be >= requested_count.")
        self.target_candidate_count = target_candidate_count or requested_count * 10
        self.pool = CandidatePool(unused_requirement_ids=[entry.requirement_id for entry in resolved_requirements.requirements] if resolved_requirements is not None else [], resolved_requirements=resolved_requirements.model_copy(deep=True) if resolved_requirements is not None else None, target_candidate_count=self.target_candidate_count, candidates=[], candidate_count=0, remaining_candidate_count=self.target_candidate_count, search_attempts=[], search_budget=SearchBudget(max_attempts=max_attempts, attempts_used=0, attempts_remaining=max_attempts))

    # ============================================================
    # ============================================================
    # Public
    def accepts_item(self, item) -> bool:
        return not excluded_childrenswear(item, self.pool.resolved_requirements)

    def add_items(self, *, attempt_id: str, items: list[ProductRecord], native_orders: dict[str, int]) -> int:
        """
        Accepted Search Attempt에서 생성된 NormalizedItem들을
        CandidatePool에 추가한다.

        동일 item_id, normalized title 또는 비어 있지 않은 image_url이 이미 존재하면:
        - Candidate는 새로 만들지 않는다.
        - 먼저 추가된 상품의 ID·제목·사이즈 등 원본 정보는 유지한다.
        - CandidateSource를 추가한다.
        - appearance_count += 1
        - best_native_order를 갱신한다.

        반환값:
        이번 attempt에서 새롭게 추가된 Candidate 수.
        """
        added_candidate_count = 0
        for item in items:
            if not self.accepts_item(item):
                continue
            native_order = native_orders.get(item.item_id)
            if native_order is None:
                raise ValueError(f'native_order is missing for item_id={item.item_id}')
            if native_order < 1:
                raise ValueError("native_order must be >= 1.")
            existing = self._find_candidate(item.item_id)
            if existing is None:
                existing = self._find_candidate_by_normalized_title(item.title)
            if existing is None:
                existing = self._find_candidate_by_image_url(item.image_url)
            if existing is None:
                candidate = Candidate(item=item, sources=[CandidateSource(attempt_id=attempt_id, native_order=native_order)], retrieval_signals=RetrievalSignals(best_native_order=native_order, appearance_count=1))
                self.pool.candidates.append(candidate)
                added_candidate_count += 1
            else:
                self._update_existing_candidate(candidate=existing, attempt_id=attempt_id, native_order=native_order)
        # ============================================================
        # ============================================================
        # Count Helpers
        self._refresh_counts()
        return added_candidate_count

    def record_attempt(self, attempt: SearchAttempt) -> None:
        """
        SearchAttempt를 기록하고 SearchBudget을 갱신한다.
        """
        if self.pool.search_budget.attempts_used >= self.pool.search_budget.max_attempts:
            raise RuntimeError("Search budget already exhausted.")
        if attempt.status == "success":
            used = set(self.pool.used_requirement_ids)
            used.update((usage.requirement_id for usage in attempt.requirement_usages))
            entries = self.pool.resolved_requirements.requirements if self.pool.resolved_requirements is not None else []
            self.pool.used_requirement_ids = [entry.requirement_id for entry in entries if entry.requirement_id in used]
            self.pool.unused_requirement_ids = [entry.requirement_id for entry in entries if entry.requirement_id not in used]
        self.pool.search_attempts.append(attempt)
        attempts_used = self.pool.search_budget.attempts_used + 1
        self.pool.search_budget = SearchBudget(max_attempts=self.pool.search_budget.max_attempts, attempts_used=attempts_used, attempts_remaining=max(self.pool.search_budget.max_attempts - attempts_used, 0))

    def enqueue_issues(self, *, attempt: SearchAttempt, plan: SearchQueryPlan, inspected_items: list[EBayRawItem]) -> None:
        """FIFO by observation order; merge identical issues in the same direction."""
        inspection = attempt.inspection
        if inspection is None:
            return
        controls = {"minimum_search_attempts_not_met", "unused_requirements"}
        codes = {"too_broad", "irrelevant_results", "too_few_results", "wrong_gender_or_category"}
        observations = [issue for issue in inspection.issues if issue not in controls]
        if not observations and (not inspection.continue_query):
            observations = ["irrelevant_results"]
        direction = (normalize_title_key(plan.query), sorted(plan.category_ids), plan.aspect_filters)
        typed = [issue for issue in observations if issue in codes]
        details = [issue for issue in observations if issue not in codes]
        for observation in dict.fromkeys(typed or observations):
            # Free-text observations retain their own identity and evidence.
            issue_type = observation if observation in codes else "irrelevant_results"
            key = normalize_title_key(observation)
            existing = next((issue for issue in self.pool.issue_queue if normalize_title_key(issue.evidence[0]) == key and (normalize_title_key(issue.original_plan.query), sorted(issue.original_plan.category_ids), issue.original_plan.aspect_filters) == direction), None)
            if existing:
                if attempt.attempt_id not in existing.occurrence_attempt_ids:
                    existing.occurrence_attempt_ids.append(attempt.attempt_id)
                continue
            self.pool.issue_queue.append(SearchIssue(issue_id=f'issue_{uuid4().hex}', issue_type=issue_type, evidence=[observation, *[detail for detail in details if detail != observation]], source_attempt_id=attempt.attempt_id, occurrence_attempt_ids=[attempt.attempt_id], original_plan=plan.model_copy(deep=True), requirement_usages=[usage.model_copy(deep=True) for usage in attempt.requirement_usages], inspection=inspection.model_copy(deep=True), inspected_items=[item.model_copy(deep=True) for item in inspected_items]))

    def successful_search_attempt_count(self) -> int:
        """
        실제 SearchResults가 성공적으로 반환된 Search Attempt 수.

        API failure attempt는 minimum search attempts에 포함하지 않는다.
        """
        return sum((1 for attempt in self.pool.search_attempts if attempt.status == "success"))

    def minimum_search_attempts_met(self) -> bool:
        return self.successful_search_attempt_count() >= self.minimum_search_attempts

    def minimum_relevance_quality_met(self) -> bool:
        """
        Freeze된 Search 종료 조건.

        candidate_count >= requested_count * 2

        AND

        accepted inspection 중 하나 이상이:
        - continue_query == True
        - relevant_result_ratio >= 0.5
        """
        if self.pool.candidate_count < self.requested_count * 2:
            return False
        return any((attempt.inspection is not None and attempt.inspection.continue_query and (attempt.inspection.relevant_result_ratio >= 0.5) for attempt in self.pool.search_attempts))

    def target_reached(self) -> bool:
        """
        최종 target 조건.

        1. minimum search attempts 충족
        2. candidate_count >= requested_count * 10
        3. minimum relevance quality 충족
        """
        return self.minimum_search_attempts_met() and (not self.pool.unused_requirement_ids) and (self.pool.candidate_count >= self.target_candidate_count) and self.minimum_relevance_quality_met()

    def budget_exhausted(self) -> bool:
        return self.pool.search_budget.attempts_remaining == 0

    def should_stop(self) -> bool:
        return self.target_reached() or self.budget_exhausted()

    def build_candidate_set(self, *, no_viable_search_strategy: bool=False, warnings: list[str] | None=None) -> CandidateSet:
        """
        현재 CandidatePool을 최종 CandidateSet으로 변환한다.

        stop_reason 우선순위:

        1. target_reached
        2. no_viable_search_strategy
        3. search_budget_exhausted
        """
        if self.target_reached():
            stop_reason = "target_reached"
        elif no_viable_search_strategy:
            stop_reason = "no_viable_search_strategy"
        elif self.budget_exhausted():
            stop_reason = "search_budget_exhausted"
        else:
            raise RuntimeError('CandidateSet cannot be built before a stop condition is met.')
        return CandidateSet(used_requirement_ids=list(self.pool.used_requirement_ids), unused_requirement_ids=list(self.pool.unused_requirement_ids), issue_queue=[issue.model_copy(deep=True) for issue in self.pool.issue_queue], resolved_requirements=self.pool.resolved_requirements.model_copy(deep=True) if self.pool.resolved_requirements is not None else None, price_conversion=self.pool.price_conversion.model_copy(deep=True) if self.pool.price_conversion is not None else None, candidate_set_id=f'candidate_set_{uuid4().hex}', target_candidate_count=self.target_candidate_count, candidate_count=self.pool.candidate_count, candidates=list(self.pool.candidates), search_attempts=list(self.pool.search_attempts), minimum_relevance_quality_met=self.minimum_relevance_quality_met(), stop_reason=stop_reason, warnings=warnings or [])

    def _find_candidate(self, item_id: str) -> Candidate | None:
        for candidate in self.pool.candidates:
            if candidate.item.item_id == item_id:
                return candidate
        return None

    def _find_candidate_by_normalized_title(self, title: str) -> Candidate | None:
        title_key = normalize_title_key(title)
        if not title_key:
            return None
        for candidate in self.pool.candidates:
            candidate_title_key = normalize_title_key(candidate.item.title)
            if candidate_title_key == title_key:
                # ============================================================
                # ============================================================
                # Candidate Helpers
                return candidate
        return None

    def _find_candidate_by_image_url(self, image_url: str | None) -> Candidate | None:
        # Exact URL only: do not collapse case, strip query parameters, or infer
        # visual similarity. Missing/blank images are not duplicate keys.
        if image_url is None or not image_url.strip():
            return None
        return next((candidate for candidate in self.pool.candidates if candidate.item.image_url == image_url), None)

    @staticmethod
    def _update_existing_candidate(*, candidate: Candidate, attempt_id: str, native_order: int) -> None:
        """
        이미 존재하는 Candidate를 갱신한다.

        같은 attempt_id + native_order source가
        이미 존재하면 중복 source는 추가하지 않는다.
        """
        source_exists = any((source.attempt_id == attempt_id and source.native_order == native_order for source in candidate.sources))
        if not source_exists:
            candidate.sources.append(CandidateSource(attempt_id=attempt_id, native_order=native_order))
            candidate.retrieval_signals = RetrievalSignals(best_native_order=CandidatePoolManager._best_native_order(current=candidate.retrieval_signals.best_native_order, new=native_order), appearance_count=candidate.retrieval_signals.appearance_count + 1)

    @staticmethod
    def _best_native_order(*, current: int | None, new: int) -> int:
        if current is None:
            return new
        return min(current, new)

    def _refresh_counts(self) -> None:
        candidate_count = len(self.pool.candidates)
        self.pool.candidate_count = candidate_count
        self.pool.remaining_candidate_count = max(self.target_candidate_count - candidate_count, 0)
