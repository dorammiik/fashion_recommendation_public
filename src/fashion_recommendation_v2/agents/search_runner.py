from __future__ import annotations
from fashion_recommendation_v2.module_compat import import_module as _role_module

from fashion_recommendation_v2.search.execution import call_in_attempt
from fashion_recommendation_v2.agents.search_brain import PlanReviewOutputError
from collections import Counter
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import Future
from contextvars import copy_context
from dataclasses import dataclass
from math import ceil
import re
import unicodedata
from fashion_recommendation_v2.tools.price_translate import PriceFXRuntime
from fashion_recommendation_v2.schemas.price import PriceConstraint
from fashion_recommendation_v2.schemas.price import PriceConversion
from fashion_recommendation_v2.agents.candidate_pool import CandidatePoolManager
from fashion_recommendation_v2.agents.candidate_pool import normalize_title_key
from fashion_recommendation_v2.search.item_normalization import ItemMapper
from fashion_recommendation_v2.schemas.search.retrieval.search_retrieval import ProductRecord
from fashion_recommendation_v2.agents.search_brain import SearchBrain
from fashion_recommendation_v2.schemas.search.candidate_pool.search_candidate_pool import CandidateSet
from fashion_recommendation_v2.schemas.search.candidate_pool.search_candidate_pool import SearchAttempt
from fashion_recommendation_v2.schemas.search.candidate_pool.search_candidate_pool import SearchStrategyFailure
from fashion_recommendation_v2.schemas.search.retrieval.search_retrieval import EBayRawItem_base as EBayRawItem
from fashion_recommendation_v2.schemas.search.retrieval.search_retrieval import SearchRequestSnapshot
from fashion_recommendation_v2.schemas.search.retrieval.search_retrieval import SearchResults
from fashion_recommendation_v2.schemas.search.item_normalization.search_item_normalization import ItemPrice
from fashion_recommendation_v2.schemas.search.item_normalization.search_item_normalization import NormalizedItem
from fashion_recommendation_v2.schemas.search.item_normalization.search_item_normalization import NormalizationMetadata
from fashion_recommendation_v2.schemas.search.requirements.search_requirements import SearchAgentInput_legacy as SearchAgentInput
from fashion_recommendation_v2.schemas.search.planning.search_planning import SearchQueryPlan
from fashion_recommendation_v2.schemas.search.planning.search_planning import SearchInspection
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import SearchItemEvaluation
from fashion_recommendation_v2.tools.ebay_search import EBaySearchTool
from fashion_recommendation_v2.agents.ranking_runner import filter_requirement
from fashion_recommendation_v2.agents.search_visual_analysis import evaluate_batches
from fashion_recommendation_v2.agents.search_visual_analysis import evaluation_error
from collections import Counter
import json
import time
from fashion_recommendation_v2.search.policy import CORE_ATTRIBUTES
from fashion_recommendation_v2.search.policy import USER_ATTRIBUTES
from fashion_recommendation_v2.search.policy import GENDER_MINIMUM_SHARE
from fashion_recommendation_v2.search.policy import MAX_QUERY_RESTRICTIONS
from fashion_recommendation_v2.search.policy import TEXT_LIMITS
from fashion_recommendation_v2.search.planning_rules import validate_marketplace_query
from fashion_recommendation_v2.search.planning_rules import plan_signature
from fashion_recommendation_v2.agents.search_brain import validate_executable_plan
from fashion_recommendation_v2.search.policy import search_policy
from fashion_recommendation_v2.search.policy import search_timeout_seconds


class SearchRunner:
    """
    Search Agent 전체 실행 루프.

    Flow:

    Requirements Extraction → CandidatePool snapshot
    ↓
    Query Planning + LLM Filter Selection (SearchBrain)
    ↓
    Price FX Conversion (one rate snapshot per run)
    ↓
    eBay Search
    ↓
    Result Inspection
    ↓
    Strategy Revision / Diversification
    ↓
    Item Mapper
    ↓
    CandidatePool
    ↓
    Stop Condition
    ↓
    CandidateSet


    Runtime Policy:

    - target_candidate_count
        = requested_count * 10

    - minimum_search_attempts
        = 3

    - max_attempts
        = 5

    - search_limit
        = target_candidate_count // 2
          unless explicitly overridden

    Stop:

    (
        minimum_search_attempts satisfied
        AND all requirements used in successful searches
        AND
        target_candidate_count reached
        AND
        minimum_relevance_quality_met
    )
    OR
    search budget exhausted
    """

    def __init__(
        self,
        *,
        search_brain: SearchBrain,
        search_tool: EBaySearchTool,
        item_mapper: ItemMapper,
        minimum_search_attempts: int = 3,
        max_attempts: int = 5,
        search_limit: int | None = None,
        inspection_limit: int = 10,
        price_fx_runtime: PriceFXRuntime | None = None,
        combined_inspection: bool = False,
        target_candidate_count: int | None = None,
    ) -> None:
        if minimum_search_attempts < 1:
            raise ValueError(
                "minimum_search_attempts "
                "must be >= 1."
            )

        if max_attempts < 1:
            raise ValueError(
                "max_attempts must be >= 1."
            )

        if (
            minimum_search_attempts
            > max_attempts
        ):
            raise ValueError(
                "minimum_search_attempts "
                "cannot exceed max_attempts."
            )

        if (
            search_limit is not None
            and search_limit < 1
        ):
            raise ValueError(
                "search_limit must be >= 1."
            )

        if inspection_limit < 1:
            raise ValueError(
                "inspection_limit must be >= 1."
            )

        self.search_brain = search_brain
        self.search_tool = search_tool
        self.item_mapper = item_mapper
        self.price_fx_runtime = (
            price_fx_runtime if price_fx_runtime is not None else PriceFXRuntime()
        )

        self.minimum_search_attempts = (
            minimum_search_attempts
        )

        self.max_attempts = (
            max_attempts
        )

        self.search_limit = (
            search_limit
        )

        self.inspection_limit = (
            inspection_limit
        )
        self.combined_inspection = combined_inspection
        self.target_candidate_count = target_candidate_count

    # ============================================================
    # Public
    # ============================================================

    def run(self, input_data: SearchAgentInput) -> CandidateSet:
        requirements = self.search_brain.extract_requirements(input_data)
        manager = CandidatePoolManager(
            resolved_requirements=requirements,
            requested_count=input_data.requested_count,
            max_attempts=self.max_attempts,
            minimum_search_attempts=self.minimum_search_attempts,
            target_candidate_count=self.target_candidate_count,
        )
        warnings: list[str] = []
        current_plan = self.search_brain.plan_query(
            input_data, resolved_requirements=requirements.model_copy(deep=True),
        )
        conversion = None
        if current_plan.price_constraint is not None:
            conversion = self.price_fx_runtime.convert(
                constraint=current_plan.price_constraint,
                current_date=input_data.current_date,
                target_currency=self.search_tool.price_currency,
            )
        manager.pool.price_conversion = conversion
        current_plan = self.price_fx_runtime.apply(current_plan, conversion)
        limit = self._get_search_limit(target_candidate_count=manager.target_candidate_count)
        correcting_issue = None
        must_cover_unused = False

        while not manager.budget_exhausted():
            current_plan.validate_for_execution()
            usages = self.search_brain.assess_requirement_usage(
                input_data=input_data, query_plan=current_plan,
                resolved_requirements=requirements,
            ) if requirements.requirements else []
            used_ids = {usage.requirement_id for usage in usages}
            hard_ids = {entry.requirement_id for entry in requirements.requirements if entry.kind == "hard"}
            missing_hard = hard_ids - used_ids
            no_progress = must_cover_unused and not used_ids.intersection(manager.pool.unused_requirement_ids)
            if missing_hard or no_progress:
                warnings.append(f"Plan cannot execute: missing hard requirements={sorted(missing_hard)}; "
                                f"unused-condition progress={not no_progress}.")
                if correcting_issue:
                    correcting_issue.status = "not_applicable"
                    correcting_issue.disposition_reason = warnings[-1]
                return manager.build_candidate_set(no_viable_search_strategy=True, warnings=warnings)

            attempt_id = f"{input_data.request_id}_search_{manager.pool.search_budget.attempts_used + 1:03d}"
            if correcting_issue:
                correcting_issue.correction_attempts = 1
                correcting_issue.status = "in_progress"
            result = self.search_tool.search(attempt_id=attempt_id, plan=current_plan, limit=limit)
            if result.item_failures:
                warnings.append(f'{attempt_id}: skipped {len(result.item_failures)} items after detail retrieval/validation failures.')
            items = self._deduplicate_raw_items(result.items) if result.success else []
            inspected_items = items[:self.inspection_limit]
            inspection = None
            decision = None
            added = 0
            if result.success:
                if self.combined_inspection:
                    decision = self.search_brain.inspect_and_revise(
                        input_data=input_data, query_plan=current_plan, inspected_items=inspected_items,
                        resolved_requirements=requirements, previous_attempts=manager.pool.search_attempts,
                        requirement_usages=usages, unused_requirement_ids=manager.pool.unused_requirement_ids,
                        candidate_count=manager.pool.candidate_count,
                        target_candidate_count=manager.target_candidate_count,
                        projected_candidate_count=self._project_candidate_count(manager=manager, raw_items=items),
                        existing_candidates=[{'item_id': c.item.item_id, 'title': c.item.title,
                                              'image_url': c.item.image_url} for c in manager.pool.candidates],
                        completed_search_attempts=manager.successful_search_attempt_count() + 1,
                        minimum_search_attempts=self.minimum_search_attempts,
                        attempts_remaining=manager.pool.search_budget.attempts_remaining - 1,
                        quality_met=manager.minimum_relevance_quality_met(), correcting_issue=correcting_issue,
                    )
                    inspection = decision.inspection
                else:
                    inspection = self.search_brain.inspect_results(
                        input_data=input_data, query_plan=current_plan,
                        inspected_items=inspected_items,
                        candidate_count=self._project_candidate_count(manager=manager, raw_items=items),
                        target_candidate_count=manager.target_candidate_count,
                        completed_search_attempts=manager.successful_search_attempt_count() + 1,
                        minimum_search_attempts=self.minimum_search_attempts,
                        correcting_issue=correcting_issue,
                    )
                # Execution controls are not quality issues and never enter the queue.
                control = None
                remaining = set(manager.pool.unused_requirement_ids) - used_ids
                if remaining:
                    control = "unused_requirements"
                elif manager.successful_search_attempt_count() + 1 < self.minimum_search_attempts:
                    control = "minimum_search_attempts_not_met"
                quality = [issue for issue in inspection.issues
                           if issue not in {"unused_requirements", "minimum_search_attempts_not_met"}]
                inspection = inspection.model_copy(update={"issues": ([control] if control else []) + quality})
                admitted = items if inspection.continue_query else (
                    [item for item in inspected_items if item.item_id in decision.accepted_item_ids]
                    if decision else [])
                if admitted:
                    normalized = self._map_accepted_items(manager=manager, raw_items=admitted)
                    added = manager.add_items(attempt_id=attempt_id, items=normalized,
                                              native_orders={item.item_id: item.native_order for item in items})
            else:
                warnings.append(f"{attempt_id}: eBay search failed - {result.error_message or ''}")

            attempt = SearchAttempt(
                attempt_id=attempt_id, query=current_plan.query,
                category_ids=list(current_plan.category_ids), aspect_filters=dict(current_plan.aspect_filters),
                price_conversion=conversion, requirement_usages=usages,
                correcting_issue_id=correcting_issue.issue_id if correcting_issue else None,
                returned_item_count=result.returned_item_count if result.success else 0,
                added_candidate_count=added, status="success" if result.success else "failed",
                inspection=inspection, error_message=result.error_message,
                inspection_decision=decision,
                item_failures=[failure.model_copy(deep=True) for failure in result.item_failures],
                failure_stage=result.failure_stage,
            )
            manager.record_attempt(attempt)
            callback = getattr(self, 'progress_callback', None)
            if callback:
                callback(dict(stage='search', status='running',
                              completed_searches=manager.pool.search_budget.attempts_used))
            if correcting_issue:
                correcting_issue.status = ("resolved" if inspection and inspection.corrected_issue_resolved is True
                                           else "attempted")
                correcting_issue.disposition_reason = (
                    "Correction inspected as resolved." if correcting_issue.status == "resolved"
                    else "One correction attempt consumed; unresolved or unverified.")
            manager.enqueue_issues(attempt=attempt, plan=current_plan, inspected_items=inspected_items)

            # No planning/lookup after the last execution budget has been consumed.
            if manager.budget_exhausted() or manager.target_reached():
                break
            if not result.success and correcting_issue is None:
                continue  # Failed API attempts consume budget, but do not mark conditions used.
            correcting_issue = None

            if self.combined_inspection:
                if not result.success:
                    continue  # Retry transport failures within the existing budget.
                if decision.revision is None:
                    warnings.append('Brain stopped before target: ' + decision.decision_reason)
                    return manager.build_candidate_set(no_viable_search_strategy=True, warnings=warnings)
                try:
                    revision = self.search_brain.complete_inspection_revision(
                        input_data=input_data, current_query_plan=current_plan, revision=decision.revision)
                    revised = self._revision_to_plan(revision, conversion)
                    revised.validate_for_execution()
                    if self._plans_equal(current_plan, revised):
                        raise ValueError('Combined inspection proposed the same SearchQueryPlan.')
                except Exception as exc:
                    message = str(exc) or type(exc).__name__
                    warnings.append(f'{attempt_id}: Strategy completion failed ({type(exc).__name__}): {message}.')
                    partial = manager.build_candidate_set(no_viable_search_strategy=True, warnings=warnings)
                    partial.strategy_failures.append(SearchStrategyFailure(
                        source_attempt_id=attempt_id, trigger=decision.revision.trigger,
                        error_type=type(exc).__name__, message=message,
                        retained_candidate_count=partial.candidate_count))
                    return partial
                attempt.revision = revision
                correcting_issue = next((issue for issue in manager.pool.issue_queue
                    if issue.source_attempt_id == attempt_id and issue.issue_type == revision.trigger
                    and issue.status == 'pending'), None)
                current_plan = revised
                must_cover_unused = bool(manager.pool.unused_requirement_ids)
                continue

            while True:
                unused = list(manager.pool.unused_requirement_ids)
                base_plan = current_plan
                context_items = inspected_items
                queued = None
                if unused:
                    trigger = "unused_requirements"
                elif not manager.minimum_search_attempts_met():
                    trigger = "minimum_search_attempts_not_met"
                else:
                    queued = next((issue for issue in manager.pool.issue_queue
                                   if issue.status == "pending" and issue.correction_attempts == 0), None)
                    trigger = queued.issue_type if queued else "too_few_results"
                    if queued:
                        base_plan = queued.original_plan.model_copy(deep=True)
                        context_items = [item.model_copy(deep=True) for item in queued.inspected_items]
                context_inspection = queued.inspection if queued else inspection
                if context_inspection is None:
                    context_inspection = SearchInspection(inspected_count=0, relevant_result_ratio=0.0,
                                                          relevance_quality=0.0, continue_query=False)
                revision_inspection = context_inspection.model_copy(update={
                    "continue_query": False,
                    "issues": [trigger, *[issue for issue in context_inspection.issues if issue != trigger]],
                })
                try:
                    revision = self.search_brain.revise_strategy(
                        input_data=input_data, current_query_plan=base_plan,
                        inspection=revision_inspection, inspected_items=context_items,
                        previous_attempts=[entry.model_copy(deep=True) for entry in manager.pool.search_attempts],
                        resolved_requirements=requirements.model_copy(deep=True),
                        unused_requirement_ids=unused,
                        queued_issue=queued.model_copy(deep=True) if queued else None,
                    )
                    if queued and revision.issue_disposition != "correct":
                        queued.status = revision.issue_disposition
                        queued.disposition_reason = revision.disposition_reason
                        continue
                    revised = self._revision_to_plan(revision, conversion)
                except Exception as exc:
                    message = str(exc) or type(exc).__name__
                    warnings.append(f'{attempt_id}: Search strategy revision failed ({type(exc).__name__}): {message}. Returning collected candidates.')
                    if queued:
                        queued.disposition_reason = f'Strategy revision failed: {message}'
                    partial = manager.build_candidate_set(no_viable_search_strategy=True, warnings=warnings)
                    partial.strategy_failures.append(SearchStrategyFailure(
                        source_attempt_id=attempt_id, trigger=trigger,
                        error_type=type(exc).__name__, message=message,
                        retained_candidate_count=partial.candidate_count))
                    return partial
                attempt.revision = revision
                if self._plans_equal(base_plan, revised):
                    message = ("DIVERSIFY_RESULTS produced the same SearchQueryPlan."
                               if trigger == "minimum_search_attempts_not_met"
                               else "Strategy Revision produced the same SearchQueryPlan.")
                    warnings.append(f"{attempt_id}: Additional search was required. {message}")
                    if queued:
                        queued.disposition_reason = message
                    return manager.build_candidate_set(no_viable_search_strategy=True, warnings=warnings)
                current_plan = revised
                correcting_issue = queued
                must_cover_unused = bool(unused)
                break

        if manager.pool.unused_requirement_ids:
            warnings.append("Unexplored requirements: " + ", ".join(manager.pool.unused_requirement_ids))
        return manager.build_candidate_set(warnings=warnings)

    # ============================================================
    # Runtime Policy
    # ============================================================

    def _get_search_limit(
        self,
        *,
        target_candidate_count: int,
    ) -> int:
        """
        Search limit runtime policy.

        기본:

        target_candidate_count // 2

        Example:

        requested_count = 5
        target = 50
        search_limit = 25

        Explicit override가 있는 경우
        테스트/실험 목적으로 해당 값을 사용한다.
        """

        if self.search_limit is not None:
            return self.search_limit

        return max(
            target_candidate_count // 2,
            1,
        )

    # ============================================================
    # Raw Item Dedup
    # ============================================================

    @staticmethod
    def _deduplicate_raw_items(
        raw_items: list[EBayRawItem],
    ) -> list[EBayRawItem]:
        """
        한 SearchResult 내부 중복 제거.

        1차:
        item_id exact match

        2차:
        normalized title exact match

        먼저 나온 상품,
        즉 더 좋은 native_order를 유지한다.
        """

        seen_item_ids: set[str] = set()

        seen_title_keys: set[str] = set()

        result: list[EBayRawItem] = []

        for item in raw_items:
            title_key = (
                normalize_title_key(
                    item.title
                )
            )

            if (
                item.item_id
                in seen_item_ids
            ):
                continue

            if (
                title_key
                and title_key
                in seen_title_keys
            ):
                continue

            seen_item_ids.add(
                item.item_id
            )

            if title_key:
                seen_title_keys.add(
                    title_key
                )

            result.append(
                item
            )

        return result

    # ============================================================
    # Projected Candidate Count
    # ============================================================

    @staticmethod
    def _project_candidate_count(
        *,
        manager: CandidatePoolManager,
        raw_items: list[EBayRawItem],
    ) -> int:
        existing_item_ids = {
            candidate.item.item_id
            for candidate
            in manager.pool.candidates
        }

        existing_title_keys = {
            normalize_title_key(
                candidate.item.title
            )
            for candidate
            in manager.pool.candidates
            if normalize_title_key(
                candidate.item.title
            )
        }

        seen_image_urls = {
            candidate.item.image_url for candidate in manager.pool.candidates
            if candidate.item.image_url and candidate.item.image_url.strip()
        }

        seen_new_item_ids: set[str] = set()

        seen_new_title_keys: set[str] = set()

        new_candidate_count = 0

        for item in raw_items:
            if not manager.accepts_item(item):
                continue
            title_key = (
                normalize_title_key(
                    item.title
                )
            )

            if (
                item.item_id
                in existing_item_ids
            ):
                continue

            if (
                title_key
                and title_key
                in existing_title_keys
            ):
                continue

            if (
                item.item_id
                in seen_new_item_ids
            ):
                continue

            if (
                title_key
                and title_key
                in seen_new_title_keys
            ):
                continue

            if item.image_url and item.image_url.strip():
                if item.image_url in seen_image_urls:
                    continue
                seen_image_urls.add(item.image_url)

            seen_new_item_ids.add(
                item.item_id
            )

            if title_key:
                seen_new_title_keys.add(
                    title_key
                )

            new_candidate_count += 1

        return (
            manager.pool.candidate_count
            + new_candidate_count
        )

    # ============================================================
    # Mapper
    # ============================================================

    def _map_accepted_items(
        self,
        *,
        manager: CandidatePoolManager,
        raw_items: list[EBayRawItem],
    ) -> list[NormalizedItem]:
        """
        Accepted SearchResults만 Mapping한다.

        이미 CandidatePool에 존재하는 item_id는
        다시 LLM Mapping하지 않는다.
        """

        accepted = [item for item in raw_items if manager.accepts_item(item)]
        existing_by_id = {candidate.item.item_id: candidate.item for candidate in manager.pool.candidates}
        if getattr(self, 'combined_inspection', False):
            # Bound mapping costs as well as final candidate count. Reuse known IDs;
            # discard title/image duplicates before allocating the remaining slots.
            remaining = max(0, manager.target_candidate_count - manager.pool.candidate_count)
            titles = {normalize_title_key(item.title) for item in existing_by_id.values()}
            images = {item.image_url for item in existing_by_id.values() if item.image_url}
            limited = []
            for item in accepted:
                if item.item_id in existing_by_id:
                    limited.append(item)
                    continue
                title = normalize_title_key(item.title)
                if (title and title in titles) or (item.image_url and item.image_url in images) or remaining == 0:
                    continue
                limited.append(item)
                titles.add(title)
                if item.image_url:
                    images.add(item.image_url)
                remaining -= 1
            accepted = limited
        fresh = [item for item in accepted if item.item_id not in existing_by_id]
        # Batch through ItemMapper so the production Search path uses its bounded
        # parallelism. Legacy injected single-item adapters remain supported.
        batch_mapper = getattr(self.item_mapper, 'map_items', None)
        mapped = batch_mapper(fresh) if batch_mapper else [self.item_mapper.map_item(item) for item in fresh]
        by_id = {**existing_by_id, **{item.item_id: item for item in mapped}}
        # CandidatePool still receives native orders separately from raw items.
        return [by_id[item.item_id] for item in accepted]

    # ============================================================
    # Revision
    # ============================================================

    @staticmethod
    def _revision_to_plan(
        revision,
        price_conversion: PriceConversion | None = None,
    ) -> SearchQueryPlan:
        plan = SearchQueryPlan(
            price_constraint=revision.price_constraint,
            query=(
                revision.revised_query
            ),
            category_ids=list(
                revision.category_ids
            ),
            aspect_filters=dict(
                revision.aspect_filters
            ),
        )
        return PriceFXRuntime.apply(plan, price_conversion)

    # ============================================================
    # Plan Comparison
    # ============================================================

    @staticmethod
    def _plans_equal(
        first: SearchQueryPlan,
        second: SearchQueryPlan,
    ) -> bool:
        return (
            first.query.strip().casefold()
            == second.query.strip().casefold()
            and (
                first.category_ids
                == second.category_ids
            )
            and (
                first.aspect_filters
                == second.aspect_filters
            )
        )


# Run-local evaluation reuse (v5+)
def duplicate_keys(item):
    values = {'item_id': item.item_id, 'title': normalize_title_key(item.title),
              'image_url': item.image_url.strip() if item.image_url else ''}
    return [(name, value) for name, value in values.items() if value]


@dataclass
class CacheEntry:
    sequence: int
    item: ProductRecord
    outcome: SearchItemEvaluation
    attempt_id: str
    context_snapshot: str | None = None


class SearchEvaluationCache:
    """Construct inside run(); never share between cases, repetitions or requests."""
    def __init__(self, *, execution_profile=None):
        self.index = {}
        self.failed_snapshots = {}
        self.execution_profile = execution_profile
        self.sequence = 0
        self.seen_v36 = {}
        self.last_fresh_count = 0

    def keys(self, item):
        if self.execution_profile in {'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
            from fashion_recommendation_v2.search.candidate_records import evidence_snapshot_base as evidence_snapshot
            return [('evidence_snapshot', evidence_snapshot(item))]
        if self.execution_profile in {'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
            from hashlib import sha256
            # Same title/image alone cannot bind different products or stale
            # prices/metadata to a failed or successful representative.
            data = item.model_dump(mode='json')
            # Retrieval order is stored on candidate sources, not product evidence.
            data.get('raw_metadata', {}).pop('native_order', None)
            snapshot = json.dumps(data, sort_keys=True, ensure_ascii=False)
            return [('evidence_snapshot', sha256(snapshot.encode()).hexdigest())]
        return duplicate_keys(item)

    def find(self, item):
        matches = [(key[0], self.index[key]) for key in self.keys(item) if key in self.index]
        if not matches:
            return None, []
        entry = min((entry for _, entry in matches), key=lambda entry: entry.sequence)
        return entry, [field for field, candidate in matches if candidate is entry]

    def bind(self, item, entry):
        for key in self.keys(item):
            # In an ambiguous bridge, earliest validated evidence wins lookup;
            # never overwrite an existing representative's actual evidence.
            self.index.setdefault(key, entry)

    def discard(self, item):
        entry, _ = self.find(item)
        if entry is not None:
            self.index = {key: value for key, value in self.index.items() if value is not entry}

    def remember(self, item, outcome, attempt_id, context_snapshot=None):
        if outcome.status == 'evaluation_error' or outcome.analysis is None:
            return None
        self.sequence += 1
        entry = CacheEntry(self.sequence, item.model_copy(deep=True), outcome.model_copy(deep=True), attempt_id,
                           context_snapshot)
        self.bind(item, entry)
        return entry

    def reuse(self, item, entry, fields):
        outcome = entry.outcome.model_copy(deep=True)
        outcome.item_id = item.item_id
        outcome.batch_id = 'cache'
        outcome.retained_in_pool = False
        outcome.evaluation_mode = 'reused'
        outcome.evaluation_source_attempt_id = entry.attempt_id
        outcome.evaluation_source_item_id = entry.item.item_id
        outcome.evaluation_source_item = entry.item.model_copy(deep=True)
        outcome.duplicate_match_fields = fields
        # analysis.item_id and all image/metadata evidence remain the source's.
        self.bind(item, entry)
        return outcome, entry.item.model_copy(deep=True)

    def evaluate(self, brain, *, attempt_id, items, source_attempt_ids=None, **kwargs):
        """Yield (outcome, evaluated representative), preserving per-batch admission."""
        if self.execution_profile in {'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
            fresh, duplicates = [], []
            for item in items:
                keys = duplicate_keys(item)
                matches = [(field, self.seen_v36[(field, value)]) for field, value in keys if (field, value) in self.seen_v36]
                if matches:
                    duplicates.append((item, matches))
                else:
                    fresh.append(item)
                representative_id = matches[0][1] if matches else item.item_id
                for key in keys:
                    self.seen_v36.setdefault(key, representative_id)
            self.last_fresh_count = len(fresh)
            for outcome in evaluate_batches(brain, items=fresh, **kwargs):
                yield outcome, next(i for i in fresh if i.item_id == outcome.item_id)
            for item, matches in duplicates:
                yield SearchItemEvaluation(item_id=item.item_id, batch_id='dedup', status='duplicate_skipped',
                    evaluation_mode='skipped', evaluation_source_item_id=matches[0][1],
                    duplicate_match_fields=[field for field, _ in matches], reasons=['duplicate_before_evaluation']), None
            return
        from fashion_recommendation_v2.search.candidate_records import evaluation_context_snapshot
        from fashion_recommendation_v2.search.candidate_records import invalid_record_base as invalid_record
        from fashion_recommendation_v2.search.candidate_records import validate_record_base as validate_record
        isolate_records = self.execution_profile in {'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}
        context_snapshot = evaluation_context_snapshot(kwargs) if isolate_records else None
        source_attempt_ids = source_attempt_ids or {}
        fresh = []
        groups = {}
        pending_keys = {}
        by_id = {item.item_id: item for item in items}
        for item in items:
            entry, fields = self.find(item)
            if entry is not None:
                outcome, representative = self.reuse(item, entry, fields)
                if isolate_records:
                    if entry.context_snapshot != context_snapshot:
                        outcome = invalid_record(outcome, ValueError('Cached evaluation conditions changed.'))
                    else:
                        outcome = validate_record(outcome, item, representative,
                            kwargs.get('requirements'), kwargs.get('conversion'))
                    if outcome.status == 'evaluation_error':
                        self.discard(item)
                        self.failed_snapshots[tuple(self.keys(item))] = outcome.model_copy(deep=True)
                yield outcome, representative
                continue
            failed = self.failed_snapshots.get(tuple(self.keys(item)))
            if failed is not None:
                # This is an error checkpoint, never valid cached product evidence.
                outcome = failed.model_copy(deep=True)
                outcome.evaluation_mode = 'duplicate_unresolved'
                yield outcome, None
                continue
            matches = [(name, pending_keys[(name, value)]) for name, value in self.keys(item)
                       if (name, value) in pending_keys]
            if matches:
                representative_id = matches[0][1]
                fields = [name for name, key in matches if key == representative_id]
                groups[representative_id].append((item, fields))
            else:
                representative_id = item.item_id
                fresh.append(item)
                groups[representative_id] = []
            for key in self.keys(item):
                pending_keys.setdefault(key, representative_id)

        self.last_fresh_count = len(fresh)
        for outcome in evaluate_batches(brain, items=fresh, **kwargs):
            item = by_id.get(outcome.item_id)
            if item is None:  # Preserve unknown response ID errors without caching them.
                yield outcome, None
                continue
            source_attempt_id = source_attempt_ids.get(item.item_id, attempt_id)
            outcome.evaluation_source_attempt_id = source_attempt_id
            outcome.evaluation_source_item_id = item.item_id
            if isolate_records:
                outcome = validate_record(outcome, item, item, kwargs.get('requirements'), kwargs.get('conversion'))
            yield outcome, item
            # Admission may mark a mapping failure or a code exclusion. Cache only
            # the final normal result after the caller has processed this item.
            entry = self.remember(item, outcome, source_attempt_id, context_snapshot)
            if self.execution_profile in {'v28', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'} and outcome.status == 'evaluation_error':
                self.failed_snapshots[tuple(self.keys(item))] = outcome.model_copy(deep=True)
            for alias, fields in groups.get(item.item_id, []):
                if entry is not None:
                    reused, representative = self.reuse(alias, entry, fields)
                    if isolate_records:
                        reused = validate_record(reused, alias, representative,
                            kwargs.get('requirements'), kwargs.get('conversion'))
                    yield reused, representative
                else:
                    # Do not treat a failed representative as a reusable evaluation.
                    # Keep this unresolved duplicate visible; a later search can retry.
                    skipped = evaluation_error(alias.item_id, outcome.batch_id,
                        ValueError('Duplicate representative evaluation failed; no cached result.'))
                    skipped.evaluation_mode = 'duplicate_unresolved'
                    skipped.evaluation_source_attempt_id = source_attempt_id
                    skipped.evaluation_source_item_id = item.item_id
                    skipped.duplicate_match_fields = fields
                    yield skipped, None


# Visual search execution and pool policies (v2+)
def _dress_or_skirt(value):
    """Positive product-type values only; never classify listing titles or footwear."""
    text = unicodedata.normalize('NFKC', value).casefold()
    text = re.sub(r'[_-]+', ' ', text).strip()
    if re.search(r'\b(no|not|without|exclude|excluding)\b|제외|아닌', text):
        return False
    alternatives = re.split(r'\s+or\s+|\s*[/|]\s*', text)
    return all(re.fullmatch(r'(?:[\w]+\s+)*(?:(?:sun)?dress(?:es)?|skirts?)(?:\s+sets?)?', part.strip())
               or part.strip() in {'원피스', '스커트', '치마'} for part in alternatives)


def gender_diversity_exemption(requirements):
    if requirements.gender_diversity_policy is not None:
        return requirements.gender_diversity_policy.exemption
    entries = requirements.requirements
    if any(r.source == 'user' and r.attribute == 'gender' for r in entries):
        return 'explicit_user_gender'
    for requirement in entries:
        if (requirement.source != 'user' or requirement.kind != 'hard'
                or requirement.attribute not in {'category', 'product_type', 'product_group', 'type'}):
            continue
        values = requirement.value if isinstance(requirement.value, list) else [requirement.value]
        if values and all(isinstance(v, str) and _dress_or_skirt(v) for v in values):
            return 'dress_or_skirt_product_type'
    return None


def gender_diversity_required(requirements):
    if requirements.gender_diversity_policy is not None:
        return requirements.gender_diversity_policy.required
    return gender_diversity_exemption(requirements) is None


def gender_distribution(candidates):
    counts = Counter(c.search_analysis.gender if c.search_analysis else 'unknown' for c in candidates)
    total = len(candidates)
    return {g: counts[g] / total if total else 0.0 for g in ('men', 'women', 'unisex', 'unknown')}


def gender_minimum_share(version):
    from fashion_recommendation_v2.search.policy import GENDER_MINIMUM_SHARE
    return GENDER_MINIMUM_SHARE if search_policy(version).enabled('concise_query_contract') else .2


def gender_coverage_met(candidates, minimum_share=.2):
    counts = Counter(c.search_analysis.gender if c.search_analysis else 'unknown' for c in candidates)
    return bool(candidates) and all(counts[g] / len(candidates) >= minimum_share for g in ('men', 'women'))


def product_metadata(raw):
    """Lossless raw evidence plus mechanical field copies; no Mapper LLM call."""
    values = {name: getattr(raw, name) for name in (
        'item_id', 'title', 'category_path', 'category_id_path', 'image_url', 'item_web_url',
        'condition', 'condition_description', 'brand')}
    values['image_url'] = raw.image_url.strip() or None if raw.image_url else None
    for field in ('color', 'size', 'material', 'pattern'):
        value = getattr(raw, field)
        values[field] = [value] if value else []
    detail = {}
    for aspect in raw.localized_aspects:
        detail.setdefault(aspect.name, []).append(aspect.value)
    return NormalizedItem(**values, raw_metadata=raw.model_copy(deep=True), detail=detail,
        price=ItemPrice(value=float(raw.price.value), currency=raw.price.currency) if raw.price else None,
        normalization_metadata=NormalizationMetadata(deterministic_fields=list(values),
                                                      unresolved_fields=[]))


def map_visual_candidate(item, analysis, *, mapper=None, cache=None):
    """Map passing products; v21 integrates evaluation through ItemMapper.

    Legacy versions keep the original metadata-only behavior. Evaluation evidence
    is retained separately before normalization so Ranking can revalidate it.
    """
    if analysis.item_id != item.item_id:
        raise ValueError('Mapper item identity mismatch.')
    if mapper is not None:
        if item.raw_metadata is None:
            raise ValueError('ItemMapper requires original marketplace metadata.')
        key = (item.model_dump_json(), analysis.model_dump_json())
        if cache is not None and key in cache:
            return cache[key].model_copy(deep=True)
        mapped = mapper.map_item(item.raw_metadata, analysis=analysis)
        if cache is not None:
            cache[key] = mapped.model_copy(deep=True)
        return mapped
    return item.model_copy(deep=True)



def parallel_candidate_mappings(outcomes, *, mapper, cache, workers):
    """One shared round executor, unique snapshots only, stable pool commit order.

    Submit as evaluation yields items; workers continuously take the next ready
    item. Only the caller updates the pool/cache. Propagate individual failures
    through Future.result to the existing mapping_error handler. The executor is
    drained on exit so usage recording cannot outlive the run.
    """
    if workers != 4:
        raise ValueError('Parallel ItemMapper requires exactly four workers.')
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix='search-item-mapper') as executor:
        scheduled = {}
        entries = []
        for outcome, representative in outcomes:
            future = None
            if outcome.status == 'accepted':
                key = (representative.model_dump_json(), outcome.analysis.model_dump_json())
                if key not in scheduled:
                    if key in cache:
                        future = Future()
                        future.set_result(cache[key].model_copy(deep=True))
                    else:
                        future = executor.submit(copy_context().run, map_visual_candidate,
                            representative, outcome.analysis, mapper=mapper)
                    scheduled[key] = future
                future = scheduled[key]
            entries.append((outcome, representative, future))
        # Preserve representative selection/source ownership independently of API
        # completion order, while the executor refills its four slots immediately.
        yield from entries


def inspection_evaluation_summary(analysis):
    if analysis is not None and analysis.evaluation_policy in {'v36', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
        return dict(admission_checks=analysis.admission_checks.model_dump(),
            consistency_warnings=[dict(attribute=a.attribute,
                status=a.metadata_image_consistency.status, reason=a.metadata_image_consistency.reason)
                for a in analysis.attributes if a.metadata_image_consistency.status not in {'consistent', 'metadata_missing', 'not_applicable'}])
    return dict(relavance_quality=getattr(analysis, 'relavance_quality', None),
        thum_quality=getattr(analysis, 'thum_quality', None))


def pool_summary(candidates):
    return [{'item_id': c.item.item_id, 'title': c.item.title,
             'gender': c.search_analysis.gender,
             'attributes': [a.model_dump(mode='json') for a in c.search_analysis.attributes],
             **(dict(admission_checks=c.search_analysis.admission_checks.model_dump()) if c.search_analysis.evaluation_policy in {'v36', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'} else dict(relavance_quality=c.search_analysis.relavance_quality, thum_quality=c.search_analysis.thum_quality))} for c in candidates]


class VisualCandidatePool(CandidatePoolManager):
    search_policy_version = 'v2'

    def accepts_item(self, item):
        return True if self.search_policy_version in {'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'} else super().accepts_item(item)
    def coverage_met(self):
        if self.search_policy_version in {'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
            return not self.pool.unused_requirement_ids
        return (not self.pool.unused_requirement_ids
                and (not gender_diversity_required(self.pool.resolved_requirements)
                     or gender_coverage_met(self.pool.candidates, gender_minimum_share(self.search_policy_version))))

    def minimum_relevance_quality_met(self):
        # Compatibility hook for the inherited pool builder; v2 never uses a ratio.
        return self.coverage_met()

    def trim(self):
        """Keep best passing items, reserving both gender shares when applicable."""
        levels = {'high': 2, 'medium': 1, 'low': 0}
        ordered = sorted(self.pool.candidates, key=lambda c: (
            -levels[c.search_analysis.relavance_quality], -levels[c.search_analysis.thum_quality],
            c.retrieval_signals.best_native_order or 999999, c.item.item_id))
        capacity = self.target_candidate_count
        reserved = []
        if gender_diversity_required(self.pool.resolved_requirements):
            quota = ceil(min(capacity, len(ordered)) * 0.2)
            for gender in ('men', 'women'):
                reserved.extend([c for c in ordered if c.search_analysis.gender == gender][:quota])
        selected_ids = {c.item.item_id for c in reserved}
        selected = reserved + [c for c in ordered if c.item.item_id not in selected_ids][:capacity-len(reserved)]
        keep = {c.item.item_id for c in selected}
        self.pool.candidates = [c for c in ordered if c.item.item_id in keep]
        self._refresh_counts()

    def build_candidate_set(self, **kwargs):
        if self.search_policy_version in {'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
            from fashion_recommendation_v2.search.candidate_records import sanitize_pool
            sanitize_pool(self)
        elif self.search_policy_version == 'v30':
            from fashion_recommendation_v2.search.candidate_records import validate_pool_records
            validate_pool_records(self.pool)
            self._refresh_counts()
        result = super().build_candidate_set(**kwargs)
        if kwargs.get('no_viable_search_strategy'):
            result.stop_reason = 'no_viable_search_strategy'
        result.search_policy_version = self.search_policy_version
        result.gender_diversity_exemption = gender_diversity_exemption(self.pool.resolved_requirements)
        result.gender_distribution = gender_distribution(result.candidates)
        result.coverage_requirements_met = self.coverage_met()
        result.minimum_relevance_quality_met = None
        if self.search_policy_version in {'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
            from fashion_recommendation_v2.search.candidate_records import finish_diagnostics
            finish_diagnostics(self, result)
        return result


from fashion_recommendation_v2.search.semantic_validation import observed

class SearchVisualRunner(SearchRunner):
    """Uses shared query/FX/dedup helpers, never the v0/v1 inspection loop."""
    def __init__(self, *, search_brain, search_tool, target_candidate_count=None,
                 minimum_search_attempts=1, max_attempts=None, search_limit=20, price_fx_runtime=None,
                 search_policy_version='v2', item_mapper=None, execution_profile=None):
        from fashion_recommendation_v2.search.policy import search_default_target_candidate_count
        if target_candidate_count is None:
            target_candidate_count = search_default_target_candidate_count(search_policy_version)
        if execution_profile is not None:
            from fashion_recommendation_v2.search.contracts import SEARCH_EVAL_CONTRACTS
            if execution_profile not in {'v28', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'} or SEARCH_EVAL_CONTRACTS[execution_profile].version != search_policy_version:
                raise ValueError('Execution profile must select its registered semantic contract.')
        self.execution_profile = execution_profile or (search_policy_version if search_policy_version in {'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'} else None)
        # v34 supplies its image limits per call, without mutating v32 operations.
        if search_policy_version in {'v29', 'v30', 'v31', 'v32', 'v33'} and hasattr(search_brain.llm, 'operation_timeout_overrides'):
            from fashion_recommendation_v2.search.policy import search_image_timeout_overrides
            search_brain.llm.operation_timeout_overrides.update(search_image_timeout_overrides(search_policy_version))
        search_brain.search_execution_profile = execution_profile or search_policy_version
        max_attempts = search_policy(search_policy_version).query_budget if max_attempts is None else max_attempts
        if search_policy(search_policy_version).enabled('per_item_evidence_contract') and max_attempts != 4:
            raise ValueError('v18 uses a fixed budget of 4 queries, at most 2 per round.')
        if search_policy(search_policy_version).enabled('three_query_budget') and max_attempts != 3:
            raise ValueError('v7 normal search budget is 3; coverage extensions are managed separately.')
        if not 1 <= minimum_search_attempts <= max_attempts or search_limit != 20 or target_candidate_count < 2:
            raise ValueError('v2 requires search_limit=20, positive attempt bounds and target >=2.')
        if not search_policy(search_policy_version).enabled('supported'):
            raise ValueError('Visual runner supports v2 through v7.')
        self.search_policy_version = search_policy_version
        self.item_mapper = (item_mapper or ItemMapper(llm=search_brain.llm)) if search_policy(search_policy_version).enabled('common_item_mapping') else None
        self.mapping_cache = {}
        self.search_brain = search_brain
        self.search_tool = search_tool
        self.target_candidate_count = target_candidate_count
        self.minimum_search_attempts = minimum_search_attempts
        self.max_attempts = max_attempts
        self.search_limit = search_limit
        self.price_fx_runtime = price_fx_runtime or PriceFXRuntime()
        if search_timeout_seconds(search_policy_version, 1) is None:
            # Bound methods work through the recording proxies as well. Do not
            # assign attributes on a proxy instead of its actual HTTP client.
            for client in (getattr(search_tool, 'client', None), getattr(self.price_fx_runtime, 'fx_client', None)):
                configure = getattr(client, 'set_timeout', None)
                if callable(configure):
                    configure(None)

    @observed('run')
    def run(self, input_data):
        if self.search_policy_version in {'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
            from fashion_recommendation_v2.schemas.search.requirements.search_requirements import prepare_input_v25 as prepare_input
            if self.search_policy_version in {'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
                from fashion_recommendation_v2.schemas.search.requirements.search_requirements import prepare_input_v37 as prepare_input
            input_data = prepare_input(input_data)
        if search_policy(self.search_policy_version).enabled('parallel_queries'):
            return run_parallel_search(self, input_data)
        from fashion_recommendation_v2.agents.ranking_runner import filter_requirement
        requirements = (self.search_brain.extract_requirements(input_data, search_policy_version=self.search_policy_version)
                        if search_policy(self.search_policy_version).enabled('legacy_visual_inspection') else self.search_brain.extract_requirements(input_data))
        if search_policy(self.search_policy_version).enabled('legacy_visual_inspection') and requirements.gender_diversity_policy is None:
            raise ValueError('v3 requires Brain gender diversity policy at requirement extraction.')
        manager = VisualCandidatePool(requested_count=input_data.requested_count,
            target_candidate_count=self.target_candidate_count, max_attempts=self.max_attempts,
            minimum_search_attempts=self.minimum_search_attempts, resolved_requirements=requirements)
        manager.search_policy_version = self.search_policy_version
        current = self.search_brain.plan_query(input_data, resolved_requirements=requirements.model_copy(deep=True))
        conversion = (self.price_fx_runtime.convert(constraint=current.price_constraint,
            current_date=input_data.current_date, target_currency=self.search_tool.price_currency)
            if current.price_constraint else None)
        manager.pool.price_conversion = conversion
        current = self.price_fx_runtime.apply(current, conversion)
        # Local lifetime prevents any reuse between eval repetitions or cases.
        evaluation_cache = SearchEvaluationCache() if search_policy(self.search_policy_version).enabled('standalone_evaluation_cache') else None
        warnings = []
        must_cover_unused = False
        hard_ids = {r.requirement_id for r in requirements.requirements if r.kind == 'hard'}
        budget_requirements = [r for r in requirements.requirements if isinstance(r.value, PriceConstraint)]
        executed_plans = []
        while not manager.budget_exhausted():
            current.validate_for_execution()
            usages = self.search_brain.assess_requirement_usage(input_data=input_data,
                query_plan=current, resolved_requirements=requirements) if requirements.requirements else []
            used = {u.requirement_id for u in usages}
            if hard_ids - used or (must_cover_unused and not used.intersection(manager.pool.unused_requirement_ids)):
                warnings.append('Execution blocked: missing hard requirements or no unused-condition progress.')
                return manager.build_candidate_set(no_viable_search_strategy=True, warnings=warnings)
            attempt_id = f'{input_data.request_id}_search_{manager.pool.search_budget.attempts_used + 1:03d}'
            executed_plans.append(current.model_copy(deep=True))
            result = self.search_tool.search(attempt_id=attempt_id, plan=current, limit=self.search_limit)
            if evaluation_cache is not None:
                # Keep title/image aliases for cache accounting; exact repeated IDs
                # in one response still denote a single item and retain first rank.
                raw_items = list({item.item_id: item for item in reversed(result.items)}.values()) if result.success else []
                raw_items.sort(key=lambda item: item.native_order)
            else:
                raw_items = self._deduplicate_raw_items(result.items) if result.success else []
            decision = None
            added = 0
            error = result.error_message
            failure_stage = result.failure_stage
            successful = result.success
            evaluations = []
            summary = {}
            inspection_error = None
            if result.item_failures:
                warnings.append(f'{attempt_id}: {len(result.item_failures)} items failed retrieval/validation.')
            if successful:
                # Input copies provide stable evidence paths; candidate mapping happens
                # only after each item's response passes validation and quality gates.
                items = [product_metadata(raw) for raw in raw_items]
                by_id = {item.item_id: item for item in items}
                native_orders = {r.item_id: r.native_order for r in raw_items}
                price_checks = {item.item_id: [filter_requirement(item, r, conversion)
                                               for r in budget_requirements] for item in items}
                before = pool_summary(manager.pool.candidates)
                old_ids = {c.item.item_id for c in manager.pool.candidates}
                evaluation_args = dict(input_data=input_data, items=items, requirements=requirements,
                    conversion=conversion, price_checks=price_checks, search_policy_version=self.search_policy_version)
                if evaluation_cache is not None:
                    outcomes = evaluation_cache.evaluate(self.search_brain, attempt_id=attempt_id, **evaluation_args)
                else:
                    outcomes = ((outcome, by_id.get(outcome.item_id)) for outcome in
                                evaluate_batches(self.search_brain, **evaluation_args))
                admitted_representatives = set()
                for outcome, evaluated_item in outcomes:
                    if outcome.status == 'accepted':
                        try:
                            mapped = map_visual_candidate(evaluated_item, outcome.analysis)
                            if not manager.accepts_item(mapped):
                                outcome.status = 'rejected'
                                outcome.reasons.append('excluded_childrenswear')
                            elif mapped.item_id not in admitted_representatives:
                                manager.add_items(attempt_id=attempt_id, items=[mapped],
                                    native_orders={mapped.item_id: native_orders[outcome.item_id]})
                                admitted_representatives.add(mapped.item_id)
                                for candidate in manager.pool.candidates:
                                    if candidate.item.item_id == mapped.item_id and candidate.search_analysis is None:
                                        candidate.search_analysis = outcome.analysis.model_copy(deep=True)
                        except Exception as exc:
                            outcome.status = 'evaluation_error'
                            if evaluation_cache is not None:
                                evaluation_cache.discard(evaluated_item)
                            outcome = evaluation_error(outcome.item_id, outcome.batch_id, exc)
                    evaluations.append(outcome)
                # Stable order in artifacts independent of which batch finished first.
                evaluations.sort(key=lambda e: (native_orders.get(e.item_id, 999999), e.item_id))
                manager.trim()
                retained = {c.item.item_id for c in manager.pool.candidates}
                added = len(retained - old_ids)
                for outcome in evaluations:
                    outcome.retained_in_pool = (outcome.evaluation_source_item_id or outcome.item_id) in retained
                    if outcome.status == 'accepted' and not outcome.retained_in_pool:
                        outcome.reasons.append('duplicate_or_pool_cap')
                counts = Counter(e.status for e in evaluations)
                summary = {status: counts[status] for status in ('accepted', 'rejected', 'evaluation_error')}
                summary['added_candidate_count'] = added
                if evaluation_cache is not None:
                    summary['fresh_evaluated_count'] = evaluation_cache.last_fresh_count
                    summary['reused_evaluation_count'] = sum(e.evaluation_mode == 'reused' for e in evaluations)
                    summary['duplicate_unresolved_count'] = sum(e.evaluation_mode == 'duplicate_unresolved' for e in evaluations)
                    summary['visual_batch_count'] = ceil(summary['fresh_evaluated_count'] / 10)
                if summary.get('evaluation_error'):
                    warnings.append(f'{attempt_id}: {summary["evaluation_error"]} evaluation_error; '
                                    'other validated items preserved; no image evaluation retry.')
                context = {
                    'search_policy_version': self.search_policy_version,
                    'gender_diversity_policy': (requirements.gender_diversity_policy.model_dump(mode='json')
                                                if requirements.gender_diversity_policy else None),
                    'query_plan': current.model_dump(mode='json'),
                    'unused_requirements_after_current': [r for r in manager.pool.unused_requirement_ids if r not in used],
                    'target_candidate_count': self.target_candidate_count,
                    'candidate_count_before': len(before), 'candidate_count_after': len(retained),
                    'gender_diversity_required': gender_diversity_required(requirements),
                    'gender_diversity_exemption': gender_diversity_exemption(requirements),
                    'gender_distribution_after': gender_distribution(manager.pool.candidates),
                    'pool_before': before, 'pool_after': pool_summary(manager.pool.candidates),
                    'added_candidates': pool_summary([c for c in manager.pool.candidates if c.item.item_id not in old_ids]),
                    'evaluation_summary': summary,
                    'evaluation_error_count': summary.get('evaluation_error', 0),
                    'item_outcomes': [dict(item_id=e.item_id, status=e.status, reasons=e.reasons,
                        evaluation_mode=e.evaluation_mode, evaluation_source_item_id=e.evaluation_source_item_id,
                        error_type=e.error_type, error_message=e.error_message,
                        retained_in_pool=e.retained_in_pool,
                        **inspection_evaluation_summary(e.analysis)) for e in evaluations],
                    'attempts_remaining_after_current': manager.pool.search_budget.attempts_remaining - 1,
                    'previous_attempts': [a.model_dump(mode='json', exclude={
                        'visual_inspection', 'inspection', 'inspection_decision', 'item_evaluations', 'item_failures'})
                        for a in manager.pool.search_attempts],
                }
                try:
                    decision = self.search_brain.inspect_visual_results(input_data=input_data,
                        requirements=requirements, context=context)
                except Exception as exc:
                    inspection_error = exc
                    error = f'{type(exc).__name__}: {exc}'
                    warnings.append(f'{attempt_id}: inspection failed; validated candidates preserved. {error}')
            attempt = SearchAttempt(attempt_id=attempt_id, query=current.query,
                category_ids=current.category_ids, aspect_filters=current.aspect_filters,
                price_conversion=conversion, requirement_usages=usages,
                returned_item_count=result.returned_item_count if result.success else 0,
                added_candidate_count=added, status='success' if successful else 'failed',
                error_message=error, failure_stage=failure_stage, item_failures=result.item_failures,
                visual_strategy=decision, item_evaluations=evaluations, evaluation_summary=summary)
            manager.record_attempt(attempt)
            callback = getattr(self, 'progress_callback', None)
            if callback:
                callback(dict(stage='search', status='running', completed_searches=manager.pool.search_budget.attempts_used))
            if inspection_error is not None:
                partial = manager.build_candidate_set(no_viable_search_strategy=True, warnings=warnings)
                partial.strategy_failures.append(SearchStrategyFailure(source_attempt_id=attempt_id,
                    trigger='too_few_results', error_type=type(inspection_error).__name__,
                    message=str(inspection_error), retained_candidate_count=partial.candidate_count))
                return partial
            if manager.budget_exhausted() or (successful and manager.target_reached() and not decision.continue_query):
                break
            if not successful:
                continue
            if not decision.continue_query and not manager.target_reached():
                warnings.append('Premature stop proposal rejected: candidate/condition/gender goals remain unmet.')
            # A model stop proposal cannot waive coverage. An executable revision is
            # still needed; if absent, return a visibly incomplete result, never success.
            if decision.revision is None:
                warnings.append('Brain supplied no viable revision before completion: ' + decision.decision_reason)
                return manager.build_candidate_set(no_viable_search_strategy=True, warnings=warnings)
            expected_trigger = ('unused_requirements' if manager.pool.unused_requirement_ids else
                'gender_diversity' if gender_diversity_required(requirements) and not gender_coverage_met(manager.pool.candidates)
                else None)
            try:
                if search_policy(self.search_policy_version).enabled('legacy_visual_inspection'):
                    allowed = ([expected_trigger] if expected_trigger else
                               ['irrelevant_results', 'wrong_gender_or_category', 'too_broad', 'too_few_results'])
                    if decision.revision.trigger not in allowed:
                        policy = requirements.gender_diversity_policy
                        reason = (f'unused_requirements={manager.pool.unused_requirement_ids}; '
                                  f'gender_policy={policy.model_dump(mode="json")}; '
                                  f'gender_distribution={gender_distribution(manager.pool.candidates)}; '
                                  f'candidate_count={manager.pool.candidate_count}/{self.target_candidate_count}')
                        attempt.revision_repair = dict(status='requested', expected_triggers=allowed,
                            application_reason=reason, original_revision=decision.revision.model_dump(mode='json'))
                        repaired = self.search_brain.repair_visual_revision(input_data=input_data, context={
                            **context, 'expected_triggers': allowed, 'application_reason': reason,
                            'previous_revision': decision.revision.model_dump(mode='json'),
                            'resolved_requirements': requirements.model_dump(mode='json'),
                            'instruction': 'Repair only the priority-violating revision; do not repeat evaluation.'})
                        attempt.revision_repair['repaired_revision'] = repaired.revision.model_dump(mode='json')
                        if repaired.revision.trigger not in allowed:
                            raise ValueError(f'Repaired priority mismatch: expected {allowed}, got {repaired.revision.trigger}.')
                        decision.revision = repaired.revision
                        decision.decision_reason = repaired.decision_reason
                        attempt.visual_strategy = decision.model_copy(deep=True)
                        attempt.revision_repair['status'] = 'repaired'
                if not gender_diversity_required(requirements) and decision.revision.trigger == 'gender_diversity':
                    raise ValueError('Gender diversification is disabled for this request.')
                if expected_trigger and decision.revision.trigger != expected_trigger:
                    raise ValueError(f'Priority mismatch: expected {expected_trigger}, got {decision.revision.trigger}.')
                revision = self.search_brain.complete_inspection_revision(input_data=input_data,
                    current_query_plan=current, revision=decision.revision)
                revised = self._revision_to_plan(revision, conversion)
                revised.validate_for_execution()
                if any(self._plans_equal(plan, revised) for plan in executed_plans):
                    raise ValueError('Visual inspection proposed a previously executed SearchQueryPlan.')
            except Exception as exc:
                if attempt.revision_repair is not None:
                    attempt.revision_repair['status'] = 'failed'
                    attempt.revision_repair['error'] = f'{type(exc).__name__}: {exc}'
                warnings.append(f'{attempt_id}: strategy completion failed: {type(exc).__name__}: {exc}')
                partial = manager.build_candidate_set(no_viable_search_strategy=True, warnings=warnings)
                partial.strategy_failures.append(SearchStrategyFailure(source_attempt_id=attempt_id,
                    trigger=decision.revision.trigger, error_type=type(exc).__name__, message=str(exc),
                    retained_candidate_count=partial.candidate_count))
                return partial
            attempt.revision = revision
            current = revised
            must_cover_unused = bool(manager.pool.unused_requirement_ids)
        if not manager.coverage_met():
            warnings.append(f'Coverage incomplete: unused={manager.pool.unused_requirement_ids}; '
                            f'gender={gender_distribution(manager.pool.candidates)}.')
        return manager.build_candidate_set(warnings=warnings)


# Parallel query rounds (v6+)
def parallel_limit(unused, remaining, version=None):
    if search_policy(version).enabled('concise_query_contract'):
        return min(2, remaining)
    return min(remaining, 2 if len(unused) >= 2 else 1)


def retrieve_round(runner, branches):
    """Each submitted query consumes a slot, including transport exceptions."""
    def fetch(branch):
        plan, attempt_id = branch['plan'], branch['attempt_id']
        try:
            return runner.search_tool.search(attempt_id=attempt_id, plan=plan, limit=runner.search_limit)
        except Exception as exc:
            return SearchResults(attempt_id=attempt_id, request=SearchRequestSnapshot(
                query=plan.query, category_ids=plan.category_ids, aspect_filters=plan.aspect_filters),
                items=[], returned_item_count=0, success=False, failure_stage='search',
                error_message=f'{type(exc).__name__}: {exc}')
    with ThreadPoolExecutor(max_workers=min(2, len(branches)), thread_name_prefix='search-query') as executor:
        futures = [executor.submit(copy_context().run, fetch, branch) for branch in branches]
        # Stable branch order, irrespective of network completion order.
        return [future.result() for future in futures]


def round_attempts(branches, results, conversion):
    """Record submitted queries even if evaluation/inspection later aborts."""
    return [SearchAttempt(attempt_id=branch['attempt_id'], round_id=branch['round_id'],
        query=branch['plan'].query, category_ids=branch['plan'].category_ids,
        aspect_filters=branch['plan'].aspect_filters, price_conversion=conversion,
        requirement_usages=branch['usages'], returned_item_count=result.returned_item_count if result.success else 0,
        added_candidate_count=0, status='success' if result.success else 'failed',
        error_message=result.error_message, failure_stage=result.failure_stage, item_failures=result.item_failures)
        for branch, result in zip(branches, results)]


def evaluate_round(runner, source, manager, cache, branches, results, conversion):
    requirements = manager.pool.resolved_requirements
    price_requirements = [r for r in requirements.requirements if isinstance(r.value, PriceConstraint)]
    items, origins, native_orders = {}, defaultdict(list), {}
    source_items = {}
    isolate_records = runner.search_policy_version in {'v30', 'v31', 'v32', 'v33', 'v34', 'v35'}
    if isolate_records:
        from fashion_recommendation_v2.search.candidate_records import evidence_snapshot_base as evidence_snapshot
        from fashion_recommendation_v2.search.candidate_records import evaluation_context_snapshot
        context_snapshot = evaluation_context_snapshot(dict(input_data=source, requirements=requirements,
            conversion=conversion, search_policy_version=runner.search_policy_version))
        if not hasattr(manager, 'candidate_evaluation_contexts'):
            manager.candidate_evaluation_contexts = {}
    attempts = round_attempts(branches, results, conversion)
    if runner.search_policy_version in {'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
        runner._v31_active_attempts = attempts
    old_ids = {c.item.item_id for c in manager.pool.candidates}
    if runner.search_policy_version in {'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
        runner._v31_round_before_ids = set(old_ids)
    for branch, result in zip(branches, results):
        attempt_id, plan = branch['attempt_id'], branch['plan']
        if result.success:
            seen = set()
            for raw in sorted(result.items, key=lambda i: i.native_order):
                if raw.item_id in seen:
                    continue
                seen.add(raw.item_id)
                if runner.search_policy_version in {'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
                    from fashion_recommendation_v2.schemas.search.retrieval.search_retrieval import RetrievedProductV26
                    product = RetrievedProductV26.from_raw(raw)
                    items.setdefault(raw.item_id, product)
                    if isolate_records:
                        source_items[attempt_id, raw.item_id] = product
                else:
                    items.setdefault(raw.item_id, product_metadata(raw))
                origins[raw.item_id].append(attempt_id)
                native_orders[attempt_id, raw.item_id] = raw.native_order
    if runner.search_policy_version in {'v31', 'v32', 'v33', 'v34', 'v35'}:
        runner._v31_active_attempts = attempts
        if not hasattr(manager, 'latest_evidence'):
            manager.latest_evidence = {}
        manager.latest_evidence.update({key: (item.model_copy(deep=True), context_snapshot) for key, item in items.items()})
    by_attempt = {a.attempt_id: a for a in attempts}
    origin_order = {a.attempt_id: n for n, a in enumerate(attempts)}
    admitted = set()
    new_owners = {}
    batch_owners = {}
    fresh_by_attempt = Counter()
    outcomes = cache.evaluate(runner.search_brain, attempt_id=attempts[0].attempt_id,
        source_attempt_ids={key: ids[0] for key, ids in origins.items()},
        input_data=source, items=list(items.values()), requirements=requirements,
        conversion=conversion, price_checks={item.item_id: [filter_requirement(item, r, conversion)
            for r in price_requirements] for item in items.values()}, search_policy_version=runner.search_policy_version)
    if search_policy(runner.search_policy_version).enabled('parallel_item_mapping'):
        outcomes = parallel_candidate_mappings(outcomes, mapper=runner.item_mapper,
            cache=runner.mapping_cache, workers=search_policy(runner.search_policy_version).mapper_workers)
    else:
        outcomes = ((outcome, representative, None) for outcome, representative in outcomes)
    for outcome, representative, mapping_future in outcomes:
        owners = origins.get(outcome.item_id, [attempts[0].attempt_id])
        invalid_owners = {}
        if isolate_records:
            from fashion_recommendation_v2.search.candidate_records import validate_record_base as validate_record
            checked = validate_record(outcome, items.get(outcome.item_id), representative, requirements, conversion)
            if checked is not outcome:
                # The cache generator observes this error after the yield, too.
                outcome.__dict__.update(checked.__dict__)
            existing = next((c for c in manager.pool.candidates if c.item.item_id == outcome.item_id), None)
            current_item = items.get(outcome.item_id)
            if existing is not None and current_item is not None and (
                    evidence_snapshot(existing.evaluation_item or existing.item) != evidence_snapshot(current_item)
                    or manager.candidate_evaluation_contexts.get(outcome.item_id, context_snapshot) != context_snapshot):
                # An earlier snapshot is not an independent valid evaluation of
                # changed evidence. Preserve it in the trace, then admit only a
                # valid evaluation of the current product/conditions below.
                outcome.evaluation_recovery = {**(outcome.evaluation_recovery or {}),
                    'invalidated_candidate': existing.model_dump(mode='json'),
                    'candidate_validation': {'status': 'invalid', 'reason': 'product_or_conditions_changed'}}
                if runner.search_policy_version in {'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
                    from fashion_recommendation_v2.search.candidate_records import invalidate
                    event = invalidate(manager, existing, round_id=attempts[0].round_id,
                        reason='product_or_conditions_changed', current_item=current_item, context_snapshot=context_snapshot)
                    outcome.evaluation_recovery['invalidation_id'] = event['invalidation_id']
                else:
                    manager.pool.candidates.remove(existing)
                    manager._refresh_counts()
                    old_ids.discard(outcome.item_id)
            for owner in owners:
                checked = validate_record(outcome, source_items.get((owner, outcome.item_id)),
                                          representative, requirements, conversion)
                if checked is not outcome:
                    invalid_owners[owner] = checked
        if outcome.evaluation_mode == 'fresh' and outcome.item_id in items and outcome.status != 'image_fetch_error':
            fresh_by_attempt[owners[0]] += 1
            batch_owners[outcome.batch_id] = min(batch_owners.get(outcome.batch_id, len(attempts)),
                                                origin_order[owners[0]])
        if outcome.status == 'duplicate_skipped':
            existing = next((c for c in manager.pool.candidates if c.item.item_id == outcome.evaluation_source_item_id), None)
            if existing is not None:
                for owner in owners:
                    manager._update_existing_candidate(candidate=existing, attempt_id=owner, native_order=native_orders[owner, outcome.item_id])
        if outcome.status == 'accepted':
            try:
                if mapping_future is not None:
                    mapped = mapping_future.result().model_copy(deep=True)
                    key = (representative.model_dump_json(), outcome.analysis.model_dump_json())
                    runner.mapping_cache[key] = mapped.model_copy(deep=True)
                else:
                    mapped = map_visual_candidate(representative, outcome.analysis,
                        mapper=runner.item_mapper, cache=runner.mapping_cache)
                if not manager.accepts_item(mapped):
                    outcome.status = 'rejected'
                    outcome.reasons.append('excluded_childrenswear')
                else:
                    for owner in owners:
                        if owner in invalid_owners:
                            continue
                        # One source per representative per query, even for aliases.
                        if (owner, mapped.item_id) in admitted:
                            continue
                        manager.add_items(attempt_id=owner, items=[mapped], native_orders={
                            mapped.item_id: native_orders[owner, outcome.item_id]})
                        admitted.add((owner, mapped.item_id))
                        if mapped.item_id not in old_ids:
                            previous = new_owners.get(mapped.item_id, owner)
                            new_owners[mapped.item_id] = min(previous, owner, key=origin_order.get)
                        for candidate in manager.pool.candidates:
                            if candidate.item.item_id == mapped.item_id and candidate.search_analysis is None:
                                candidate.search_analysis = outcome.analysis.model_copy(deep=True)
                                if runner.item_mapper is not None:
                                    candidate.evaluation_item = representative.model_copy(deep=True)
                                if isolate_records:
                                    manager.candidate_evaluation_contexts[candidate.item.item_id] = context_snapshot
            except Exception as exc:
                # Mutate the yielded object too: cache remembers only after this yield.
                outcome.status = 'evaluation_error'
                if representative is not None:
                    cache.discard(representative)
                outcome.error_type = type(exc).__name__
                outcome.error_message = str(exc)
                outcome.reasons.append('mapping_error')
        for index, owner in enumerate(owners):
            if owner in invalid_owners:
                by_attempt[owner].item_evaluations.append(invalid_owners[owner])
                continue
            record = outcome.model_copy(deep=True)
            if index and runner.search_policy_version in {'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
                record = SearchItemEvaluation(item_id=outcome.item_id, batch_id='dedup', status='duplicate_skipped',
                    evaluation_mode='skipped', evaluation_source_item_id=outcome.item_id, duplicate_match_fields=['item_id'],
                    reasons=['duplicate_before_evaluation'])
            if index and record.evaluation_mode == 'fresh':
                record.evaluation_mode = 'duplicate_unresolved' if record.status in {'evaluation_error', 'image_fetch_error'} else 'reused'
                record.duplicate_match_fields = ['item_id']
                if representative is not None:
                    record.evaluation_source_item = representative.model_copy(deep=True)
            by_attempt[owner].item_evaluations.append(record)
        if outcome.status == 'accepted' and runner.search_policy_version in {'v52', 'v53', 'v54', 'v55', 'v56'}:
            from fashion_recommendation_v2.search.candidate_records import notify_committed_candidate
            notify_committed_candidate(runner, manager, attempts, mapped.item_id)
    manager.trim()
    retained = {c.item.item_id for c in manager.pool.candidates}
    for index, attempt in enumerate(attempts):
        attempt.item_evaluations.sort(key=lambda e: (native_orders.get((attempt.attempt_id, e.item_id), 999999), e.item_id))
        for outcome in attempt.item_evaluations:
            outcome.retained_in_pool = (outcome.evaluation_source_item_id or outcome.item_id) in retained
            if outcome.status == 'accepted' and not outcome.retained_in_pool:
                outcome.reasons.append('duplicate_or_pool_cap')
        attempt.added_candidate_count = sum(owner == attempt.attempt_id and key in retained
                                            for key, owner in new_owners.items())
        counts = Counter(e.status for e in attempt.item_evaluations)
        attempt.evaluation_summary = {key: counts[key] for key in ('accepted', 'rejected', 'evaluation_error')}
        if runner.search_policy_version in {'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
            attempt.evaluation_summary['duplicate_skipped'] = counts['duplicate_skipped']
        if search_policy(runner.search_policy_version).enabled('scoped_requirements'):
            attempt.evaluation_summary['image_fetch_error'] = counts['image_fetch_error']
        attempt.evaluation_summary.update(added_candidate_count=attempt.added_candidate_count,
            fresh_evaluated_count=fresh_by_attempt[attempt.attempt_id],
            reused_evaluation_count=sum(e.evaluation_mode == 'reused' for e in attempt.item_evaluations),
            duplicate_unresolved_count=sum(e.evaluation_mode == 'duplicate_unresolved' for e in attempt.item_evaluations),
            visual_batch_count=sum(owner == index for owner in batch_owners.values()))
    return attempts


def prepare_branches(runner, source, manager, decision, current, context, executed, warnings, failures, owner):
    """Validate branches independently; a bad sibling cannot discard a valid plan."""
    requirements = manager.pool.resolved_requirements
    unused = set(manager.pool.unused_requirement_ids)
    hard = {r.requirement_id for r in requirements.requirements if r.kind == 'hard'}
    expected = ('unused_requirements' if unused else 'gender_diversity'
        if gender_diversity_required(requirements) and not gender_coverage_met(manager.pool.candidates) else None)
    allowed = [expected] if expected else ['irrelevant_results', 'wrong_gender_or_category', 'too_broad', 'too_few_results']
    branches, assigned, repairs = [], set(), []
    for proposal in decision.revisions:
        if len(branches) >= context['max_parallel_queries']:
            warnings.append('Extra revision skipped: per-round query/budget limit.')
            break
        draft = proposal.revision
        try:
            if draft.trigger not in allowed:
                trace = dict(status='requested', expected_triggers=allowed,
                    application_reason=f'unused={sorted(unused)}; gender_policy={requirements.gender_diversity_policy.model_dump()}',
                    original_revision=draft.model_dump(mode='json'))
                repairs.append(trace)
                repaired = runner.search_brain.repair_visual_revision(input_data=source, context={
                    **context, **trace, 'previous_revision': draft.model_dump(mode='json'),
                    'resolved_requirements': requirements.model_dump(mode='json'),
                    'assigned_target_requirement_ids': sorted(assigned),
                    'target_requirement_ids': proposal.target_requirement_ids})
                draft = repaired.revision
                trace['repaired_revision'] = draft.model_dump(mode='json')
                trace['status'] = 'repaired' if draft.trigger in allowed else 'failed'
            if draft.trigger not in allowed:
                raise ValueError(f'Priority mismatch: expected {allowed}, got {draft.trigger}.')
            if draft.issue_disposition != 'correct' or draft.preference_evidence_refs:
                raise ValueError('Revision must be executable and profile-free.')
            runner.search_brain._convert_aspect_filters(draft.aspect_filters)
            targets = set(proposal.target_requirement_ids)
            if unused and (not targets or not targets <= unused or targets & assigned):
                raise ValueError('Each branch must target distinct, currently unused requirement IDs.')
            if not unused and targets:
                raise ValueError('No unused requirements remain; target_requirement_ids must be empty.')
            revision = runner.search_brain.complete_inspection_revision(input_data=source,
                current_query_plan=current, revision=draft)
            plan = runner._revision_to_plan(revision, manager.pool.price_conversion)
            plan.validate_for_execution()
            if any(runner._plans_equal(p, plan) for p in executed + [b['plan'] for b in branches]):
                raise ValueError('Previously executed or sibling SearchQueryPlan proposed again.')
            usages = runner.search_brain.assess_requirement_usage(input_data=source,
                query_plan=plan, resolved_requirements=requirements) if requirements.requirements else []
            used = {u.requirement_id for u in usages}
            if hard - used or not targets <= used or (unused and not (used & unused) - assigned):
                raise ValueError('Missing hard requirements or assigned unused condition absent from final executable plan.')
            # Prevent a second branch merely repeating unused conditions already
            # covered by the first (including accidental undeclared overlap).
            assigned.update(used & unused)
            branches.append(dict(plan=plan, usages=usages))
            if owner.planned_revisions is None:
                owner.planned_revisions = []
            owner.planned_revisions.append(revision)
        except Exception as exc:
            if repairs and repairs[-1]['status'] == 'requested':
                repairs[-1].update(status='failed', error=f'{type(exc).__name__}: {exc}')
            warnings.append(f'{owner.attempt_id}: branch rejected: {type(exc).__name__}: {exc}')
            failures.append(SearchStrategyFailure(source_attempt_id=owner.attempt_id, trigger=draft.trigger,
                error_type=type(exc).__name__, message=str(exc), retained_candidate_count=manager.pool.candidate_count))
    if repairs:
        owner.revision_repair = {**(owner.revision_repair or {}), 'branches': repairs}
    return branches


@observed('run')
def run_parallel_search(runner, source):
    if runner.search_policy_version not in {'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
        return _run_parallel_search(runner, source)
    runner._v31_manager = None
    runner._v31_active_attempts = []
    runner._v31_round_before_ids = set()
    try:
        return _run_parallel_search(runner, source)
    except Exception as exc:
        manager = runner._v31_manager
        if manager is None:
            raise  # Requirements failure: no evaluated pool exists to preserve.
        recorded = {a.attempt_id for a in manager.pool.search_attempts}
        for attempt in runner._v31_active_attempts:
            if attempt.attempt_id not in recorded:
                manager.record_attempt(attempt)
        manager.partial_failure = dict(error_type=type(exc).__name__, message=str(exc))
        from fashion_recommendation_v2.search.candidate_records import settle_partial_attempts
        settle_partial_attempts(manager, runner._v31_active_attempts, runner._v31_round_before_ids)
        return manager.build_candidate_set(no_viable_search_strategy=True,
            warnings=[f'Partial search failure: {type(exc).__name__}: {exc}; validated candidates preserved.'])


def _run_parallel_search(runner, source):
    v7 = search_policy(runner.search_policy_version).enabled('revision_intent_contract')
    runner.mapping_cache.clear()
    requirements = runner.search_brain.extract_requirements(source, search_policy_version=runner.search_policy_version)
    if requirements.gender_diversity_policy is None:
        raise ValueError(f'{runner.search_policy_version} requires the shared Brain gender diversity policy.')
    manager_class = CandidatePoolV8 if search_policy(runner.search_policy_version).enabled('scoped_requirements') else AppendOnlyCandidatePoolV7 if v7 else VisualCandidatePool
    if search_policy(runner.search_policy_version).enabled('concise_query_contract'):
        manager_class = CandidatePoolV16
    if search_policy(runner.search_policy_version).enabled('per_item_evidence_contract'):
        manager_class = CandidatePoolV18
    manager = manager_class(requested_count=source.requested_count,
        target_candidate_count=runner.target_candidate_count, max_attempts=runner.max_attempts,
        minimum_search_attempts=runner.minimum_search_attempts, resolved_requirements=requirements)
    runner.last_pool = manager.pool
    if runner.search_policy_version in {'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
        runner._v31_manager = manager
    manager.search_policy_version = runner.search_policy_version
    manager.fixed_search_budget = getattr(runner, 'fixed_search_budget', False) or search_policy(runner.search_policy_version).enabled('concise_query_contract')
    initial_branches = None
    if search_policy(runner.search_policy_version).enabled('concise_query_contract'):
        initial_branches, conversion, repair = prepare_initial(runner, source, manager)
        manager.initial_plan_repair = repair
        if not initial_branches:
            return manager.build_candidate_set(no_viable_search_strategy=True, warnings=['Initial plans failed: ' + str(repair)])
        current, usages = initial_branches[0]['plan'], initial_branches[0]['usages']
    elif search_policy(runner.search_policy_version).enabled('scoped_requirements'):
        current, conversion, usages, repair = prepare_initial_v8(runner, source, manager)
        manager.initial_plan_repair = repair
        if current is None:
            return manager.build_candidate_set(no_viable_search_strategy=True,
                warnings=['Initial plan failed after one text-only repair: ' + repair['final_error']])
    else:
        current = runner.search_brain.plan_query(source, resolved_requirements=requirements.model_copy(deep=True))
        conversion = (runner.price_fx_runtime.convert(constraint=current.price_constraint,
            current_date=source.current_date, target_currency=runner.search_tool.price_currency) if current.price_constraint else None)
        manager.pool.price_conversion = conversion
        current = runner.price_fx_runtime.apply(current, conversion)
        current.validate_for_execution()
        usages = runner.search_brain.assess_requirement_usage(input_data=source,
            query_plan=current, resolved_requirements=requirements) if requirements.requirements else []
        hard = {r.requirement_id for r in requirements.requirements if r.kind == 'hard'}
        if hard - {u.requirement_id for u in usages}:
            return manager.build_candidate_set(no_viable_search_strategy=True,
                warnings=['Initial execution blocked: missing hard requirement usage.'])
    pending = initial_branches or [dict(plan=current, usages=usages)]
    cache = SearchEvaluationCache(execution_profile=runner.execution_profile)
    warnings, failures, executed = [], [], []
    if search_policy(runner.search_policy_version).enabled('concise_query_contract') and repair and repair['status'] == 'partial_result':
        warnings.append('Some initial branches failed; valid siblings retained. ' + str(repair['final_error']))
    round_number, no_viable = 0, False
    while pending and not manager.budget_exhausted():
        round_number += 1
        pending = pending[:parallel_limit(manager.pool.unused_requirement_ids, manager.pool.search_budget.attempts_remaining, runner.search_policy_version)]
        for index, branch in enumerate(pending, start=1):
            branch['attempt_id'] = f'{source.request_id}_search_{manager.pool.search_budget.attempts_used + index:03d}'
            branch['round_id'] = f'{source.request_id}_round_{round_number:03d}'
            executed.append(branch['plan'].model_copy(deep=True))
        before = pool_summary(manager.pool.candidates)
        before_ids = {row['item_id'] for row in before}
        if runner.search_policy_version in {'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
            runner._v31_active_attempts = []
            runner._v31_round_before_ids = set(before_ids)
        results = retrieve_round(runner, pending)
        if runner.search_policy_version in {'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
            # Charge retrieved queries and know their current evidence even if
            # category bookkeeping fails before the first evaluation is yielded.
            from fashion_recommendation_v2.search.candidate_records import evaluation_context_snapshot
            from fashion_recommendation_v2.schemas.search.retrieval.search_retrieval import RetrievedProductV26
            runner._v31_active_attempts = round_attempts(pending, results, conversion)
            current_context = evaluation_context_snapshot(dict(input_data=source, requirements=requirements,
                conversion=conversion, search_policy_version=runner.search_policy_version))
            if not hasattr(manager, 'latest_evidence'):
                manager.latest_evidence = {}
            first_items = {}
            for result in results:
                if result.success:
                    for raw in sorted(result.items, key=lambda item: item.native_order):
                        first_items.setdefault(raw.item_id, RetrievedProductV26.from_raw(raw))
            manager.latest_evidence.update({key:(item, current_context) for key,item in first_items.items()})
        if v7:
            runner.search_brain.observe_category_context([item for result in results for item in result.items])
        attempts = evaluate_round(runner, source, manager, cache, pending, results, conversion)
        # Each query is charged, including a failed branch. Used conditions only
        # advance for successful queries through the existing manager contract.
        for attempt in attempts:
            manager.record_attempt(attempt)
            if attempt.item_failures:
                warnings.append(f'{attempt.attempt_id}: {len(attempt.item_failures)} item retrieval failures.')
            if attempt.evaluation_summary['evaluation_error']:
                warnings.append(f'{attempt.attempt_id}: {attempt.evaluation_summary["evaluation_error"]} evaluation_error; other items preserved.')
        if v7:
            manager.refresh_execution_budget()
        callback = getattr(runner, 'progress_callback', None)
        if callback:
            callback(dict(stage='search', status='running', completed_searches=manager.pool.search_budget.attempts_used))
        summary = {key: sum(a.evaluation_summary.get(key, 0) for a in attempts)
                   for key in attempts[0].evaluation_summary}
        owner = attempts[-1]
        owner.round_summary = {**summary, 'query_count': len(attempts),
            'search_attempts_used': manager.pool.search_budget.attempts_used,
            'search_attempts_remaining': manager.pool.search_budget.attempts_remaining}
        context = dict(search_policy_version=runner.search_policy_version, round_id=owner.round_id,
            gender_diversity_policy=requirements.gender_diversity_policy.model_dump(mode='json'),
            query_plan=pending[-1]['plan'].model_dump(mode='json'),
            current_round_queries=[dict(attempt_id=a.attempt_id,
                query_plan=b['plan'].model_dump(mode='json'), status=a.status, error_message=a.error_message,
                requirement_usages=[u.model_dump(mode='json') for u in a.requirement_usages],
                returned_item_count=a.returned_item_count, evaluation_summary=a.evaluation_summary) for a, b in zip(attempts, pending)],
            unused_requirements_after_current=list(manager.pool.unused_requirement_ids),
            target_candidate_count=runner.target_candidate_count,
            candidate_count_before=len(before), candidate_count_after=manager.pool.candidate_count,
            gender_diversity_required=gender_diversity_required(requirements),
            gender_diversity_exemption=gender_diversity_exemption(requirements),
            gender_distribution_after=gender_distribution(manager.pool.candidates),
            pool_before=before, pool_after=pool_summary(manager.pool.candidates),
            added_candidates=pool_summary([c for c in manager.pool.candidates if c.item.item_id not in before_ids]),
            evaluation_summary=summary, evaluation_error_count=summary.get('evaluation_error', 0),
            item_outcomes=[dict(attempt_id=a.attempt_id, item_id=e.item_id, status=e.status,
                reasons=e.reasons, evaluation_mode=e.evaluation_mode,
                error_type=e.error_type, error_message=e.error_message, retained_in_pool=e.retained_in_pool,
                **inspection_evaluation_summary(e.analysis))
                for a in attempts for e in a.item_evaluations],
            attempts_remaining_after_current=manager.pool.search_budget.attempts_remaining,
            max_parallel_queries=parallel_limit(manager.pool.unused_requirement_ids, manager.pool.search_budget.attempts_remaining, runner.search_policy_version),
            previous_attempts=[a.model_dump(mode='json', exclude={'item_evaluations', 'item_failures',
                'visual_inspection', 'inspection', 'inspection_decision'}) for a in manager.pool.search_attempts])
        if runner.search_policy_version in {'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
            from fashion_recommendation_v2.search.planning import condition_pool
            from fashion_recommendation_v2.search.planning import usage_history
            context['search_condition_pool'] = condition_pool(requirements, source)
            context['condition_usage_history'] = usage_history(context['search_condition_pool'], manager.pool.search_attempts)
            owner.round_summary['condition_pool_v50'] = context['search_condition_pool']
            owner.round_summary['condition_usage_history_v50'] = context['condition_usage_history']
        if search_policy(runner.search_policy_version).enabled('compact_strategy_context'):
            context['added_candidate_ids'] = [c['item_id'] for c in context.pop('added_candidates')]
        context['gender_minimum_share'] = gender_minimum_share(runner.search_policy_version)
        if search_policy(runner.search_policy_version).enabled('separate_plan_review'):
            from fashion_recommendation_v2.search.policy import required_audience
            context['code_required_audience'] = required_audience(context)
            if search_policy(runner.search_policy_version).enabled('concise_query_contract'):
                context['code_required_audience'] = None  # Pool goal; parallel branches may target different audiences.
            owner.code_required_audience = context['code_required_audience']
            if search_policy(runner.search_policy_version).enabled('keyed_condition_contract'):
                context['code_preferred_audience'] = required_audience({**context, 'unused_requirements_after_current': []})
                owner.code_preferred_audience = context['code_preferred_audience']
        if v7:
            context.update(v7_inspection_context(manager, before_ids, attempts, before))
            if search_policy(runner.search_policy_version).enabled('scoped_requirements'):
                context['alternative_coverage'] = manager.alternative_coverage()
                context['unsearched_hard_alternatives'] = manager.unsearched_hard_alternatives()
            owner.round_summary.update(context['code_metrics'])
            if runner.search_policy_version in {'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
                owner.round_summary['invalidated_candidate_count'] = context['invalidated_candidate_count']
            owner.round_summary['normal_search_budget'] = manager.normal_search_budget
            owner.round_summary['coverage_extension_attempts'] = max(0, manager.pool.search_budget.attempts_used - manager.normal_search_budget)
        if search_policy(runner.search_policy_version).enabled('concise_query_contract'):
            from fashion_recommendation_v2.search.planning_rules import retrieval_contract
            context['resolved_requirements'] = requirements.model_dump(mode='json')
            context['retrieval_contract'] = retrieval_contract(requirements, runner.search_policy_version)
            context['hard_requirement_ids'] = [r.requirement_id for r in requirements.requirements if r.kind == 'hard']
            diagnose(context, attempts)
        from fashion_recommendation_v2.search.planning import evaluation_limited
        if runner.search_policy_version in {'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
            from fashion_recommendation_v2.search.semantic_validation import inspection_warnings
            from fashion_recommendation_v2.search.semantic_validation import experiment_records
            from dataclasses import asdict
            from fashion_recommendation_v2.search.requirement_sources import source_rules
            context['semantic_warnings'] = inspection_warnings(pending, experiment_records())
            # The original documents are already in user_input. Share only their
            # authoritative field/path rules here; never duplicate or project them.
            context['semantic_warning_source_rules'] = {key: asdict(value) for key, value in source_rules(source).items()}
            if not hasattr(manager, 'semantic_inspection_inputs'):
                manager.semantic_inspection_inputs = []
            warning_input = dict(round_id=owner.round_id, semantic_warnings=context['semantic_warnings'],
                disposition='pending')
            manager.semantic_inspection_inputs.append(warning_input)
            context['_semantic_warning_trace'] = warning_input
        if runner.search_policy_version in {'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'} and manager.target_reached():
            from fashion_recommendation_v2.schemas.search.planning.search_planning import SearchVisualStrategyV7_legacy as SearchVisualStrategyV7
            owner.round_strategy = SearchVisualStrategyV7(continue_query=False, revisions=[],
                issues=[], diagnoses=[], decision_reason='Target reached; gender diversity only guides searches needed for candidate shortfall.')
            finalize_v7_inspection(owner.round_strategy, context)
            warning_input['disposition'] = 'target_reached_without_gender_gate'
            break
        if evaluation_limited(context):
            if runner.search_policy_version in {'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
                warning_input['disposition'] = 'skipped_evaluation_limited'
            from fashion_recommendation_v2.schemas.search.planning.search_planning import SearchVisualStrategyV7_legacy as SearchVisualStrategyV7
            reason = 'evaluation_limited: unresolved product evaluations explain candidate shortage; no replenishment search.'
            owner.round_strategy = SearchVisualStrategyV7(continue_query=False, revisions=[],
                issues=[], diagnoses=[], decision_reason=reason)
            finalize_v7_inspection(owner.round_strategy, context)
            owner.round_summary['evaluation_limited'] = True
            warnings.append(reason + ' Validated candidates preserved.')
            no_viable = True
            break
        if (search_policy(runner.search_policy_version).enabled('bounded_evaluation_recovery')
                and search_timeout_seconds(runner.search_policy_version, 1) is not None):
            import time
            context['_strategy_deadline'] = time.monotonic() + (50.0 if search_policy(runner.search_policy_version).enabled('compact_strategy_context') else 25.0)
        try:
            decision = runner.search_brain.inspect_visual_results(input_data=source, requirements=requirements, context=context)
            if runner.search_policy_version in {'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
                if warning_input['disposition'] == 'pending':
                    warning_input['disposition'] = 'code_decision_without_warning_review'
            if v7:
                finalize_v7_inspection(decision, context)
            owner.round_strategy = decision
        except Exception as exc:
            if runner.search_policy_version in {'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
                warning_input['disposition'] = 'inspection_failed'
            warnings.append(f'{owner.attempt_id}: round inspection failed; validated candidates preserved: {exc}')
            if v7:
                from fashion_recommendation_v2.schemas.search.planning.search_planning import SearchVisualStrategyV7_legacy as SearchVisualStrategyV7
                try:
                    if manager.budget_exhausted() or manager.target_reached():
                        recovered = []
                    else:
                        expected = ('unused_requirements' if manager.pool.unused_requirement_ids else
                            'gender_diversity' if not manager.coverage_met() else 'too_few_results')
                        if search_policy(runner.search_policy_version).enabled('bounded_evaluation_recovery'):
                            context['text_recovery_already_used'] = True
                        recovered = [runner.search_brain.repair_v7_revision(input_data=source, context={
                            **context, 'error': f'{type(exc).__name__}: {exc}', 'expected_triggers': [expected],
                            **({'validation_feedback': exc.feedback} if hasattr(exc, 'feedback') else {}),
                            'resolved_requirements': requirements.model_dump(mode='json'),
                            'observed_categories': runner.search_brain.category_evidence,
                            'current_query_plan': pending[-1]['plan'].model_dump(mode='json')})]
                        context['text_recovery_already_used'] = True
                    decision = SearchVisualStrategyV7(continue_query=bool(recovered), revisions=recovered,
                        issues=[], diagnoses=[], decision_reason='Recovered inspection without image reevaluation.')
                    finalize_v7_inspection(decision, context)
                    owner.round_strategy = decision
                    owner.revision_repair = {'inspection_recovery': 'repaired' if recovered else 'code_termination',
                                             'original_error': str(exc)}
                except Exception as recovery_error:
                    if search_policy(runner.search_policy_version).enabled('bounded_evaluation_recovery'):
                        owner.revision_repair = {'inspection_recovery': 'failed', 'original_error': str(exc),
                            'final_error': f'{type(recovery_error).__name__}: {recovery_error}'}
                    failures.append(SearchStrategyFailure(source_attempt_id=owner.attempt_id, trigger='too_few_results',
                        error_type=type(recovery_error).__name__, message=str(recovery_error), retained_candidate_count=manager.pool.candidate_count))
                    no_viable = True
                    break
            else:
                failures.append(SearchStrategyFailure(source_attempt_id=owner.attempt_id, trigger='too_few_results',
                    error_type=type(exc).__name__, message=str(exc), retained_candidate_count=manager.pool.candidate_count))
                no_viable = True
                break
        if manager.budget_exhausted() or (manager.target_reached() and not decision.continue_query):
            break
        if not decision.continue_query and not manager.target_reached():
            warnings.append('Premature stop proposal rejected: candidate/condition/gender goals remain unmet.')
        prepare = prepare_v7_branches if v7 else prepare_branches
        pending = prepare(runner, source, manager, decision, pending[-1]['plan'], context,
                                   executed, warnings, failures, owner)
        if not pending:
            warnings.append('No executable next revision before completion: ' + decision.decision_reason)
            no_viable = True
    if not manager.coverage_met():
        warnings.append(f'Coverage incomplete: unused={manager.pool.unused_requirement_ids}; '
                        f'gender={gender_distribution(manager.pool.candidates)}.')
    result = manager.build_candidate_set(no_viable_search_strategy=no_viable, warnings=warnings)
    result.strategy_failures.extend(failures)
    return result


# v7: uncapped append-only pool, coverage extensions and final-plan validation.
class AppendOnlyCandidatePoolV7(VisualCandidatePool):
    normal_search_budget = 3

    def trim(self):
        # Deliberately no ordering, removal, replacement or quota reservation.
        self._refresh_counts()

    def budget_exhausted(self):
        return self.pool.search_budget.attempts_used >= self.normal_search_budget and (getattr(self, 'fixed_search_budget', False) or self.coverage_met())

    def refresh_execution_budget(self):
        if getattr(self, 'fixed_search_budget', False):
            return
        from fashion_recommendation_v2.schemas.search.candidate_pool.search_candidate_pool import SearchBudget
        used = self.pool.search_budget.attempts_used
        if used >= self.normal_search_budget:
            slots = (2 if len(self.pool.unused_requirement_ids) >= 2 else 1) if not self.coverage_met() else 0
            self.pool.search_budget = SearchBudget(max_attempts=max(1, used + slots),
                attempts_used=used, attempts_remaining=slots)


def v7_inspection_context(manager, before_ids, attempts, before):
    from fashion_recommendation_v2.search.planning_rules import rejection_counts
    after_ids = {c.item.item_id for c in manager.pool.candidates}
    rows = [e for a in attempts for e in a.item_evaluations]
    added, removed = len(after_ids - before_ids), len(before_ids - after_ids)
    if manager.search_policy_version in {'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
        from fashion_recommendation_v2.search.candidate_records import verified_removed_ids
        verified = verified_removed_ids(manager, attempts[0].round_id)
        unexplained = (before_ids - after_ids) - verified
        if unexplained or len(after_ids) - len(before_ids) != added - removed:
            raise RuntimeError('v31 unexplained candidate removal: ' + ', '.join(sorted(unexplained)))
    elif removed or len(after_ids) - len(before_ids) != added:
        raise RuntimeError('v7 append-only candidate invariant violated.')
    metrics = dict(pool_before=len(before), pool_after=len(after_ids), new_candidates_added=added,
        net_pool_growth=len(after_ids)-len(before_ids), removed_candidates=removed,
        retrieved_count=sum(a.returned_item_count for a in attempts),
        fresh_evaluated_count=sum(a.evaluation_summary.get('fresh_evaluated_count', 0) for a in attempts),
        reused_evaluation_count=sum(e.evaluation_mode == 'reused' for e in rows),
        duplicate_unresolved_count=sum(e.evaluation_mode == 'duplicate_unresolved' for e in rows),
        **rejection_counts(rows, manager.search_policy_version),
        evaluation_error_count=sum(e.status == 'evaluation_error' for e in rows),
        search_attempts_used=manager.pool.search_budget.attempts_used,
        search_attempts_remaining=manager.pool.search_budget.attempts_remaining)
    duplicate_directions = []
    for a in manager.pool.search_attempts:
        duplicates = a.evaluation_summary.get('reused_evaluation_count', 0) + a.evaluation_summary.get('duplicate_unresolved_count', 0)
        if a.returned_item_count and duplicates * 2 >= a.returned_item_count:
            duplicate_directions.append(dict(query=a.query, category_ids=a.category_ids,
                aspect_filters=a.aspect_filters, returned_count=a.returned_item_count,
                duplicate_count=duplicates, added_candidate_count=a.added_candidate_count))
    return dict(code_metrics=metrics, duplicate_directions=duplicate_directions,
        normal_search_budget=manager.normal_search_budget, coverage_exception_active=not manager.coverage_met(),
        coverage_extension_attempts=max(0, manager.pool.search_budget.attempts_used - manager.normal_search_budget),
        candidate_pool_policy=('evidence_validated_uncapped' if manager.search_policy_version in {'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'} else 'append_only_uncapped'),
        removed_candidate_count=removed,
        **(dict(invalidated_candidate_count=sum(e['round_id'] == attempts[0].round_id
            for e in getattr(manager, 'candidate_invalidations', []))) if manager.search_policy_version in {'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'} else {}),
        image_fetch_error_count=sum(e.status == 'image_fetch_error' for e in rows))


def finalize_v7_inspection(decision, context):
    """Persist facts from code, never an LLM's restatement of numeric counts."""
    from fashion_recommendation_v2.schemas.search.planning.search_planning import SearchInspectionMetricsV7
    m = context['code_metrics']
    diagnoses, issues = [], []
    checks = [
        ('retrieval_shortage', m['retrieved_count'] < 20 * len(context['current_round_queries']),
         f"조회 {m['retrieved_count']}개: 검색어별 목표 조회량 미달"),
        ('duplicate_excess', bool(m['retrieved_count']) and (m['reused_evaluation_count'] + m['duplicate_unresolved_count']) * 2 >= m['retrieved_count'],
         f"평가 재사용 {m['reused_evaluation_count']}개 / 미판정 중복 {m['duplicate_unresolved_count']}개"),
        ('relevance_rejection', m['relevance_rejection_count'] > 0, f"관련성·hard 조건 탈락 {m['relevance_rejection_count']}개"),
        ('thumbnail_rejection', m['thumbnail_rejection_count'] > 0, f"사진 품질 탈락 {m['thumbnail_rejection_count']}개"),
        ('evaluation_error', m['evaluation_error_count'] > 0, f"평가 오류 {m['evaluation_error_count']}개"),
    ]
    for key, flag, description in checks:
        if flag:
            diagnoses.append(key)
            issues.append(description)
    if context.get('image_fetch_error_count'):
        issues.append(f"이미지 확보 실패 {context['image_fetch_error_count']}개 (상품 평가 전 격리)")
    decision.code_metrics = SearchInspectionMetricsV7(**m)
    decision.diagnoses = diagnoses
    decision.issues = issues
    priority = ('미사용 조건 사용' if context['unused_requirements_after_current'] else
        '성별 비율 충족' if context['gender_diversity_required'] and any(
            context['gender_distribution_after'][g] < context.get('gender_minimum_share', .2) for g in ('men', 'women')) else '품질·후보 부족 대응')
    if search_policy(context.get('search_policy_version')).enabled('concise_query_contract'):
        priority = '원인별 품질 개선·대안 탐색·성별 5% 보완 (고정 예산)'
    decision.decision_reason = (f"후보 {m['pool_before']}→{m['pool_after']}개; 신규 {m['new_candidates_added']}개; "
        f"순증가 {m['net_pool_growth']}개; 제거 {m['removed_candidates']}개. "
        f"다음 우선순위: {priority}. 검색 사용 {m['search_attempts_used']}회; "
        f"현재 실행 가능 잔여 {m['search_attempts_remaining']}회.")


from fashion_recommendation_v2.search.planning_rules import effective_category_scope


from fashion_recommendation_v2.search.planning_rules import changed_plan_dimensions


@observed('planning')
def validate_v7_revision_intent(proposal, current, plan, categories, context):
    from fashion_recommendation_v2.search.planning_rules import normalized_type
    intent = proposal.intent
    changed = set(changed_plan_dimensions(current, plan))
    if set(intent.changed_dimensions) != changed or len(intent.changed_dimensions) != len(changed):
        raise ValueError(f'Revision changed_dimensions must match actual plan changes: {sorted(changed)}.')
    scope = effective_category_scope(plan, categories)
    # Unrestricted categories permit a query targeting one audience. A restricted
    # category cannot support an opposite-audience or gender-neutral intention.
    if intent.audience_scope != 'unspecified' and scope not in {'all', intent.audience_scope}:
        message = f'Revision audience intent={intent.audience_scope}, final category scope={scope}.'
        if context.get('search_policy_version') in {'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
            from fashion_recommendation_v2.search.semantic_validation import semantic_failure
            semantic_failure('query_conditions', message, query_plan=plan.model_dump(mode='json'))
        else:
            raise ValueError(message)
    old_words, new_words = set(normalized_type(current.query).split()), set(normalized_type(plan.query).split())
    if intent.change_type == 'broaden_by_removal':
        filters_removed = all(k in current.aspect_filters and current.aspect_filters[k] == v
                              for k, v in plan.aspect_filters.items()) and plan.aspect_filters != current.aspect_filters
        category_widened = effective_category_scope(current, categories) in {'men', 'women'} and scope == 'all'
        if not new_words <= old_words or not (new_words < old_words or filters_removed or category_widened):
            raise ValueError('broaden_by_removal requires actual restriction removal, not added descriptors.')
    for past in context.get('duplicate_directions', []):
        if past['category_ids'] != plan.category_ids or past['aspect_filters'] != plan.aspect_filters:
            continue
        a, b = normalized_type(past['query']), normalized_type(plan.query)
        if a.replace(' ', '') == b.replace(' ', '') or set(a.split()) == set(b.split()):
            raise ValueError('High-duplicate direction repeated with only spelling/punctuation/word order changes.')


@observed('planning')
def prepare_v7_branches(runner, source, manager, decision, current, context, executed, warnings, failures, owner):
    """One text-only recovery per rejected proposal, regardless of failure type."""
    from fashion_recommendation_v2.search.planning_rules import validate_specific_product_types
    def query_failure(message):
        if runner.search_policy_version in {'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
            from fashion_recommendation_v2.search.semantic_validation import semantic_failure
            semantic_failure('query_conditions', message, query_plan=plan.model_dump(mode='json'))
        else:
            raise ValueError(message)
    requirements = manager.pool.resolved_requirements
    v16 = search_policy(runner.search_policy_version).enabled('concise_query_contract')
    unused = set(manager.pool.unused_requirement_ids)
    hard = {r.requirement_id for r in requirements.requirements if r.kind == 'hard'}
    expected = ('unused_requirements' if unused else 'gender_diversity'
        if gender_diversity_required(requirements) and not gender_coverage_met(manager.pool.candidates, gender_minimum_share(runner.search_policy_version)) else None)
    allowed = [expected] if expected else ['irrelevant_results', 'wrong_gender_or_category', 'too_broad', 'too_few_results']
    if v16:
        from fashion_recommendation_v2.search.planning_rules import required_retrieval_ids
        hard = required_retrieval_ids(requirements, runner.search_policy_version)
        allowed = ['unused_requirements', 'gender_diversity', 'irrelevant_results', 'wrong_gender_or_category', 'too_broad', 'too_few_results']
    if runner.search_policy_version in {'v24', 'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
        from fashion_recommendation_v2.search.planning_rules import strategy_trigger_contract
        from fashion_recommendation_v2.search.planning_rules import validate_strategy_choice
        context.update(search_policy_version=runner.search_policy_version, resolved_requirements=requirements.model_dump(mode='json'))
        allowed = list(strategy_trigger_contract(context))
    branches, assigned, repairs = [], set(), []
    # An erroneous false/no-revision response cannot waive unmet coverage. Request
    # one text-only proposal; if still unusable, preserve pool and report failure.
    proposals = decision.revisions or [None]
    for proposal_index, proposal in enumerate(proposals, 1):
        if len(branches) >= context['max_parallel_queries']:
            break
        trace = None
        review_retry = None
        for retry in range(2):
            plan, usages = None, []
            try:
                if proposal is None:
                    raise ValueError('No executable revision while search goals remain unmet.')
                draft = runner.search_brain._canonical_proposal(proposal.revision) if search_policy(runner.search_policy_version).enabled('canonical_proposal_filters') else proposal.revision
                if runner.search_policy_version in {'v24', 'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
                    # Check diagnosis before category/filter calls or semantic review.
                    # A repaired query with the same forbidden trigger fails here.
                    validate_strategy_choice(proposal, {**context,
                        **({'validation_feedback': trace['validation_feedback']}
                           if trace and 'validation_feedback' in trace else {})})
                if draft.trigger not in allowed:
                    raise ValueError(f'Priority mismatch: expected {allowed}, got {draft.trigger}.')
                if draft.issue_disposition != 'correct' or draft.preference_evidence_refs:
                    raise ValueError('Revision must be executable and profile-free.')
                if any(f.name not in {'Condition', 'Size'} for f in draft.aspect_filters):
                    raise ValueError('Unsupported/unverified LLM filter: only resolved Condition/Size are allowed; price is inherited.')
                targets = set(proposal.target_requirement_ids)
                if not v16 and unused and (not targets or not targets <= unused or targets & assigned):
                    raise ValueError('Each branch must target distinct currently unused conditions.')
                if not v16 and not unused and targets:
                    raise ValueError('No unused requirements remain; target IDs must be empty.')
                if search_policy(runner.search_policy_version).enabled('separate_plan_review') and context.get('code_required_audience'):
                    if proposal.intent.audience_scope != context['code_required_audience']:
                        query_failure('Revision must target the code-selected missing audience.')
                if review_retry is None:
                    revision = call_in_attempt(bool(retry or context.get('text_recovery_already_used')),
                        runner.search_brain.complete_inspection_revision, input_data=source,
                        current_query_plan=current, revision=draft)
                    plan = runner._revision_to_plan(revision, manager.pool.price_conversion)
                else:
                    # A reviewer format error never re-generates/completes the
                    # proposal, reselects options, or reapplies the price.
                    revision, plan = review_retry
                plan.validate_for_execution()
                known = {c['category_id'] for c in runner.search_brain.category_evidence}
                if not set(plan.category_ids) <= known:
                    raise ValueError('Final category IDs must have marketplace evidence.')
                from fashion_recommendation_v2.search.planning_rules import plan_signature
                if any((plan_signature(p) == plan_signature(plan) if v16 else runner._plans_equal(p, plan))
                       for p in executed + [b['plan'] for b in branches]):
                    raise ValueError('Previously executed or sibling plan proposed again.')
                if search_policy(runner.search_policy_version).enabled('code_revision_fields'):
                    proposal.intent.changed_dimensions = changed_plan_dimensions(current, plan)
                validate_v7_revision_intent(proposal, current, plan, runner.search_brain.category_evidence, context)
                usages = call_in_attempt(bool(retry or context.get('text_recovery_already_used')),
                    runner.search_brain.assess_requirement_usage, input_data=source, query_plan=plan,
                    resolved_requirements=requirements, review_context={
                        'proposal': proposal.model_dump(mode='json'), 'inspection': decision.model_dump(mode='json'),
                        'code_metrics': context['code_metrics'], 'expected_triggers': allowed,
                        **({'validation_feedback': trace} if review_retry is not None else {})})
                if not v16:
                    validate_specific_product_types(plan, requirements, usages, runner.search_brain.category_evidence, singular=search_policy(runner.search_policy_version).enabled('legacy_hard_query_coverage'))
                if search_policy(runner.search_policy_version).enabled('scoped_requirements'):
                    from fashion_recommendation_v2.search.planning_rules import validate_v8_query_usage
                    if v16:
                        from fashion_recommendation_v2.agents.search_brain import validate_executable_plan
                        from fashion_recommendation_v2.agents.search_brain import validate_revision
                        validate_executable_plan(runner.search_brain, plan, requirements, usages)
                        validate_revision(proposal, context, requirements, usages, plan=plan)
                    else:
                        validate_v8_query_usage(requirements, usages, max_soft=3 if search_policy(getattr(runner, 'search_policy_version', 'v8')).enabled('three_soft_search_terms') else 1)
                        manager.validate_alternative_progress(plan, targets)
                review = getattr(runner.search_brain, 'last_plan_review', None)
                scope = effective_category_scope(plan, runner.search_brain.category_evidence)
                if review and scope in {'men', 'women'} and review['assessed_audience_scope'] != scope:
                    query_failure('LLM audience assessment disagrees with actual category scope.')
                if search_policy(runner.search_policy_version).enabled('separate_plan_review') and context.get('code_required_audience'):
                    if not review or review['assessed_audience_scope'] != context['code_required_audience']:
                        query_failure('Executed plan does not target the code-selected missing audience.')
                used = {u.requirement_id for u in usages}
                if hard - used or not targets <= used or (not v16 and unused and not (used & unused) - assigned):
                    query_failure('Hard condition or assigned unused condition absent from executable plan.')
                assigned.update(used & unused)
                branches.append(dict(plan=plan, usages=usages))
                owner.planned_revisions = (owner.planned_revisions or []) + [revision]
                if trace is not None:
                    trace.update(status='repaired', repaired_revision=proposal.model_dump(mode='json'))
                break
            except Exception as exc:
                feedback_v49 = None
                if runner.search_policy_version in {'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
                    from fashion_recommendation_v2.search.planning_feedback import plan_feedback
                    feedback_v49 = plan_feedback(exc, version=runner.search_policy_version, plan_id=f'{owner.attempt_id}:revision_{proposal_index}',
                        stage='revision_validation', plan=plan, requirements=requirements, usages=usages,
                        categories=runner.search_brain.category_evidence,
                        valid_plans=[b['plan'] for b in branches], context=context, proposal=proposal)
                if retry == 0 and not context.get('text_recovery_already_used'):
                    if search_policy(runner.search_policy_version).enabled('bounded_evaluation_recovery'):
                        context['text_recovery_already_used'] = True
                    trace = dict(status='requested', expected_triggers=allowed, error=f'{type(exc).__name__}: {exc}',
                        original_revision=proposal.model_dump(mode='json') if proposal else None)
                    if hasattr(exc, 'feedback'):
                        trace['validation_feedback'] = exc.feedback
                    if feedback_v49 is not None:
                        trace['plan_id'] = feedback_v49['plan_id']
                        trace['structured_feedback_v49'] = feedback_v49
                    repairs.append(trace)
                    if runner.search_policy_version in {'v24', 'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'} and isinstance(exc, PlanReviewOutputError):
                        trace.update(recovery_kind='review_output', execution_plan=plan.model_dump(mode='json'))
                        review_retry = (revision, plan)
                        continue
                    try:
                        proposal = runner.search_brain.repair_v7_revision(input_data=source, context={
                            **context, **trace, 'previous_revision': trace['original_revision'],
                            'resolved_requirements': requirements.model_dump(mode='json'),
                            'observed_categories': runner.search_brain.category_evidence,
                            'current_query_plan': current.model_dump(mode='json'),
                            'assigned_target_requirement_ids': sorted(assigned)})
                        continue
                    except Exception as repair_exc:
                        exc = repair_exc
                        if runner.search_policy_version in {'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
                            feedback_v49 = plan_feedback(exc, version=runner.search_policy_version, plan_id=f'{owner.attempt_id}:revision_{proposal_index}',
                                stage='revision_correction_response', requirements=requirements, context=context, proposal=proposal)
                if trace is not None:
                    trace.update(status='failed', final_error=f'{type(exc).__name__}: {exc}')
                    if feedback_v49 is not None:
                        trace['final_structured_feedback_v49'] = feedback_v49
                warnings.append(f'{owner.attempt_id}: v7 revision failed after text recovery: {exc}')
                failures.append(SearchStrategyFailure(source_attempt_id=owner.attempt_id,
                    trigger=expected or 'too_few_results', error_type=type(exc).__name__, message=str(exc),
                    retained_candidate_count=manager.pool.candidate_count))
                if search_policy(runner.search_policy_version).enabled('bounded_evaluation_recovery') and isinstance(exc, TimeoutError):
                    owner.revision_repair = {**(owner.revision_repair or {}), 'branches': repairs}
                    return branches if v16 else []
                break
    if repairs:
        owner.revision_repair = {**(owner.revision_repair or {}), 'branches': repairs}
    return branches


from fashion_recommendation_v2.search.planning_rules import query_covers_alternative


class CandidatePoolV8(AppendOnlyCandidatePoolV7):
    """Query coverage excludes item-only preferences; hard OR options each get a search."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.initial_plan_repair = None
        self.searched_alternatives = set()
        self.refresh_unused()

    def unsearched_hard_alternatives(self):
        from fashion_recommendation_v2.search.planning_rules import requirement_alternatives
        hard = {r.requirement_id for r in self.pool.resolved_requirements.requirements if r.kind == 'hard'}
        return [dict(requirement_id=k, value=v) for k, v in requirement_alternatives(self.pool.resolved_requirements)
                if k in hard and (k, v) not in self.searched_alternatives]

    def refresh_unused(self):
        missing_or = {a['requirement_id'] for a in self.unsearched_hard_alternatives()}
        used = set(self.pool.used_requirement_ids)
        self.pool.unused_requirement_ids = [r.requirement_id for r in self.pool.resolved_requirements.requirements
            if r.evaluation_scope != 'item' and not r.unrestricted
            and (r.requirement_id not in used or r.requirement_id in missing_or)]

    def record_attempt(self, attempt):
        from fashion_recommendation_v2.search.planning_rules import requirement_alternatives
        super().record_attempt(attempt)
        if attempt.status == 'success':
            self.searched_alternatives.update((k, v) for k, v in requirement_alternatives(self.pool.resolved_requirements)
                if any(u.requirement_id == k and u.location == 'query'
                       and query_covers_alternative(u.evidence, v) for u in attempt.requirement_usages))
        self.refresh_unused()

    def validate_alternative_progress(self, plan, targets):
        for key in targets:
            missing = [a['value'] for a in self.unsearched_hard_alternatives() if a['requirement_id'] == key]
            if missing and not any(query_covers_alternative(plan.query, v) for v in missing):
                raise ValueError(f'Hard OR search coverage missing: {key}: choose one of {missing}.')

    def alternative_coverage(self):
        from fashion_recommendation_v2.search.planning_rules import requirement_alternatives
        from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import HARD_PASS_STATUSES_v40 as HARD_PASS_STATUSES
        accepted = HARD_PASS_STATUSES if self.search_policy_version in {'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'} else {'met'}
        rows = []
        for key, value in requirement_alternatives(self.pool.resolved_requirements):
            ids = [c.item.item_id for c in self.pool.candidates if c.search_analysis and any(
                a.requirement_id == key and a.value == value and a.status in accepted
                for a in c.search_analysis.alternative_judgments)]
            rows.append(dict(requirement_id=key, value=value, searched=(key, value) in self.searched_alternatives,
                             present=bool(ids), candidate_count=len(ids), item_ids=ids))
        return rows

    def build_candidate_set(self, **kwargs):
        result = super().build_candidate_set(**kwargs)
        result.initial_plan_repair = self.initial_plan_repair
        result.alternative_coverage = self.alternative_coverage()
        result.completion_status = ('partial_result' if result.candidates else 'failed') if result.stop_reason == 'no_viable_search_strategy' else 'normal_completion'
        return result


def prepare_initial_v8(runner, source, manager):
    """One text-only retry covering initial planning and completed-plan validation."""
    from fashion_recommendation_v2.search.planning_rules import validate_v8_query_usage
    from fashion_recommendation_v2.search.planning_rules import validate_specific_product_types
    requirements = manager.pool.resolved_requirements
    conversion, previous, trace = None, None, None
    for attempt in range(2):
        try:
            kwargs = dict(resolved_requirements=requirements.model_copy(deep=True))
            if attempt:
                kwargs['validation_feedback'] = dict(error=trace['original_error'], previous_plan=previous,
                    requirements=requirements.model_dump(mode='json'))
            plan = call_in_attempt(attempt > 0, runner.search_brain.plan_query, source, **kwargs)
            previous = plan.model_dump(mode='json')
            if requirements.price_constraint and conversion is None:
                conversion = runner.price_fx_runtime.convert(constraint=requirements.price_constraint,
                    current_date=source.current_date, target_currency=runner.search_tool.price_currency)
            plan = runner.price_fx_runtime.apply(plan, conversion)
            manager.pool.price_conversion = conversion
            plan.validate_for_execution()
            usages = call_in_attempt(attempt > 0, runner.search_brain.assess_requirement_usage, input_data=source, query_plan=plan,
                resolved_requirements=requirements)
            validate_v8_query_usage(requirements, usages, max_soft=3 if search_policy(getattr(runner, 'search_policy_version', 'v8')).enabled('three_soft_search_terms') else 1)
            validate_specific_product_types(plan, requirements, usages, runner.search_brain.category_evidence, singular=True)
            if trace:
                trace.update(status='repaired', repaired_plan=plan.model_dump(mode='json'))
            return plan, conversion, usages, trace
        except Exception as exc:
            error = f'{type(exc).__name__}: {exc}'
            if attempt == 0:
                trace = dict(status='requested', original_error=error, original_plan=previous)
            else:
                trace.update(status='failed', final_error=error)
    return None, conversion, [], trace


class CandidatePoolV16(CandidatePoolV8):
    """Fixed retrieval budget, optional soft exploration and value-level coverage."""
    search_policy_version = 'v16'
    fixed_search_budget = True

    def unsearched_hard_alternatives(self):
        from fashion_recommendation_v2.search.planning_rules import required_retrieval_ids
        core = required_retrieval_ids(self.pool.resolved_requirements, self.search_policy_version)
        return [a for a in super().unsearched_hard_alternatives() if a['requirement_id'] in core]

    def refresh_unused(self):
        from fashion_recommendation_v2.search.planning_rules import required_retrieval_ids
        required = required_retrieval_ids(self.pool.resolved_requirements, self.search_policy_version)
        missing_or = {a['requirement_id'] for a in self.unsearched_hard_alternatives()}
        used = set(self.pool.used_requirement_ids)
        self.pool.unused_requirement_ids = [r.requirement_id for r in self.pool.resolved_requirements.requirements
            if r.requirement_id in required and (r.requirement_id not in used or r.requirement_id in missing_or)]

    def record_attempt(self, attempt):
        super().record_attempt(attempt)
        if attempt.status == 'success':
            from fashion_recommendation_v2.search.planning_rules import alternative_targets
            self.searched_alternatives.update(alternative_targets(self.pool.resolved_requirements, attempt.requirement_usages))
        self.refresh_unused()


class CandidatePoolV18(CandidatePoolV16):
    search_policy_version = 'v18'
    normal_search_budget = 4

    def _update_existing_candidate(self, *, candidate, attempt_id, native_order):
        super()._update_existing_candidate(candidate=candidate, attempt_id=attempt_id, native_order=native_order)
        if self.search_policy_version in {'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
            # Keep all observed ranks, but appearances count distinct queries.
            candidate.retrieval_signals.appearance_count = len({s.attempt_id for s in candidate.sources})


def diagnose(context, attempts):
    m = context['code_metrics']
    causes = []
    if any(a.status == 'success' and a.returned_item_count < 20 for a in attempts):
        causes.append('retrieval_shortage')
    if m['retrieved_count'] and (m['reused_evaluation_count'] + m['duplicate_unresolved_count']) * 2 >= m['retrieved_count']:
        causes.append('duplicate_excess')
    for key in ('relevance_rejection', 'thumbnail_rejection', 'evaluation_error'):
        if m[key + '_count']:
            causes.append(key)
    from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import HARD_PASS_STATUSES_v40 as HARD_PASS_STATUSES
    accepted = HARD_PASS_STATUSES if context.get('search_policy_version') in {'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'} else {'met'}
    failures = Counter(j.requirement_id for a in attempts for e in a.item_evaluations
        if e.evaluation_mode != 'reused' and e.analysis for j in e.analysis.judgments
        if j.status not in accepted and j.requirement_id in context.get('hard_requirement_ids', []))
    context.update(code_diagnoses=causes, hard_failure_counts=dict(failures))


@observed('planning')
def prepare_initial(runner, source, manager):
    """Resolve FX once; validate all siblings before repairing only failed branches."""
    from pydantic import ValidationError
    from fashion_recommendation_v2.search.execution import without_profile
    from fashion_recommendation_v2.search.execution import call_in_attempt
    from fashion_recommendation_v2.schemas.search.planning.search_planning import SearchQueryPlanLLM_legacy as SearchQueryPlanLLM
    from fashion_recommendation_v2.schemas.search.planning.search_planning import SearchInitialPlansV16_v16 as SearchInitialPlansV16
    from fashion_recommendation_v2.search.contracts import search_prompts
    if runner.search_policy_version in {'v24', 'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
        from fashion_recommendation_v2.search.contracts import search_schemas
        SearchInitialPlansV16 = search_schemas(runner.search_policy_version, purpose='planning').SearchInitialPlansV16
    initial_plan_prompt = search_prompts(runner.search_policy_version).initial_plan_prompt
    if runner.search_policy_version in {'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
        from functools import partial
        runner.search_brain._planning_source_v32 = source
        initial_plan_prompt = partial(initial_plan_prompt, source=source)
    from fashion_recommendation_v2.tools.price_client import FXRateUnavailableError
    requirements = manager.pool.resolved_requirements
    conversion, valid = None, []
    trace = dict(status='requested', original_error=None, final_error=None,
        failure_stage=None, fx_attempts=[], generation_attempts=[], branches=[])
    brain = runner.search_brain
    brain.category_evidence.clear()
    brain.filter_resolution_history.clear()

    def failure(stage, exc):
        error = f'{type(exc).__name__}: {exc}'
        trace['original_error'] = trace['original_error'] or error
        trace.update(final_error=error, failure_stage=stage)
        result = dict(stage=stage, error=error, error_type=type(exc).__name__)
        if runner.search_policy_version in {'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
            from fashion_recommendation_v2.search.planning_feedback import plan_feedback
            result['validation_feedback'] = plan_feedback(exc, version=runner.search_policy_version, plan_id='initial_generation',
                stage=stage, requirements=requirements, context={'price_conversion': conversion})
        return result

    # A transport failure does not consume query repair or change a search query.
    if requirements.price_constraint:
        for retry in range(2):
            try:
                conversion = runner.price_fx_runtime.convert(constraint=requirements.price_constraint,
                    current_date=source.current_date, target_currency=runner.search_tool.price_currency)
                trace['fx_attempts'].append(dict(attempt=retry + 1, status='success'))
                break
            except FXRateUnavailableError as exc:
                trace['fx_attempts'].append(dict(attempt=retry + 1, status='failed', **failure('price_conversion', exc)))
                if retry == 0:
                    time.sleep(1.0)
                else:
                    trace['status'] = 'failed'
                    return [], None, trace
            except Exception as exc:
                trace['fx_attempts'].append(dict(attempt=retry + 1, status='failed', **failure('price_conversion', exc)))
                trace['status'] = 'failed'
                return [], None, trace
    manager.pool.price_conversion = conversion

    for retry in range(2):
        try:
            prompt = initial_plan_prompt(requirements, generation_error=trace['final_error'] if retry else None,
                **({'validation_error': trace['generation_attempts'][-1]}
                   if runner.search_policy_version in {'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'} and retry else {}))
            output = brain._generate(system_prompt=prompt, user_input=without_profile(source),
                output_schema=SearchInitialPlansV16, recovery=bool(retry))
            output = SearchInitialPlansV16.model_validate(output.model_dump())
            trace['generation_attempts'].append(dict(attempt=retry + 1, status='success'))
            break
        except Exception as exc:
            trace['generation_attempts'].append(dict(attempt=retry + 1, status='failed', **failure('query_planning', exc)))
            if retry:
                trace['status'] = 'failed'
                return [], conversion, trace

    pending = []

    def validate_branch(draft, record, *, recovery=False, existing_plan=None):
        stage = 'plan_completion'
        plan, usages = existing_plan, []
        response_start = len(getattr(brain, 'model_response_history', []))
        try:
            plan = existing_plan or call_in_attempt(recovery, brain.complete_initial_plan, source, draft, requirements)
            if existing_plan is None or runner.search_policy_version not in {'v24', 'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
                plan = runner.price_fx_runtime.apply(plan, conversion)
            plan.validate_for_execution()
            validate_marketplace_query(plan.query)
            if any(plan_signature(b['plan']) == plan_signature(plan) for b in valid):
                raise ValueError('Initial sibling plans must be distinct; propose a different eligible alternative.')
            record['completed_plan'] = plan.model_dump(mode='json')
            stage = 'plan_validation'
            review_context = {'validation_feedback': record['attempts'][-1]} if recovery and record['attempts'] else None
            usages = call_in_attempt(recovery, brain.assess_requirement_usage, input_data=source,
                query_plan=plan, resolved_requirements=requirements, review_context=review_context)
            validate_executable_plan(brain, plan, requirements, usages)
            if runner.search_policy_version in {'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'} and (record['branch_id'] == f'initial_{len(output.plans)}' or recovery):
                from fashion_recommendation_v2.search.planning import condition_pool
                from fashion_recommendation_v2.search.planning import validate_initial_use
                trace['condition_pool_v50'] = condition_pool(requirements, source)
                trace['stylist_initial_use_v50'] = validate_initial_use(trace['condition_pool_v50'],
                    valid + [dict(plan=plan, usages=usages)],
                    getattr(brain, '_stylist_nonuse_v50', {}).get(draft.query) or output.stylist_nonuse_reason)
            valid.append(dict(plan=plan, usages=usages))
            record['attempts'].append(dict(stage=stage, status='success'))
            record['status'] = 'repaired' if recovery else 'valid'
            return None
        except Exception as exc:
            entry = dict(status='failed', **failure(stage, exc))
            if runner.search_policy_version in {'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
                from fashion_recommendation_v2.search.planning_feedback import plan_feedback
                entry['validation_feedback'] = plan_feedback(exc, version=runner.search_policy_version, plan_id=record['branch_id'],
                    stage=stage, plan=plan, requirements=requirements, usages=usages,
                    categories=brain.category_evidence, valid_plans=[b['plan'] for b in valid],
                    context={'price_conversion': conversion, 'original_claims':
                        getattr(brain, '_plan_claims', {}).get(plan.query, []) if plan else []})
            record['attempts'].append(entry)
            record['status'] = 'failed'
            # A malformed reviewer response is repaired against the SAME plan.
            if (runner.search_policy_version in {'v24', 'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'} and stage == 'plan_validation'
                    and isinstance(exc, PlanReviewOutputError)):
                record['recovery_kind'] = 'review_output'
                return plan
            return plan if stage == 'plan_validation' and isinstance(exc, ValidationError) else False
        finally:
            if runner.search_policy_version in {'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
                record.setdefault('response_links', []).append(dict(
                    plan_id=record['branch_id'], phase='correction' if recovery else 'initial',
                    response_indices=list(range(response_start, len(getattr(brain, 'model_response_history', []))))))

    # Never let failure in branch 1 skip branch 2's original validation.
    for index, draft in enumerate(output.plans, 1):
        record = dict(branch_id=f'initial_{index}', original_plan=draft.model_dump(mode='json'), attempts=[])
        if runner.search_policy_version in {'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
            record['generation_response_indices'] = [i for i, row in enumerate(getattr(brain, 'model_response_history', []))
                if row.get('operation', '').startswith('SearchInitialPlansV16')]
        trace['branches'].append(record)
        review_plan = validate_branch(draft, record)
        if record['status'] == 'failed':
            pending.append((draft, record, review_plan))

    for draft, record, review_plan in pending:
        if len(valid) >= 2:
            break
        try:
            if runner.search_policy_version in {'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
                record['correction_response_start'] = len(getattr(brain, 'model_response_history', []))
            if review_plan is not False:
                validate_branch(draft, record, recovery=True, existing_plan=review_plan)
                continue
            prompt = initial_plan_prompt(requirements, failed_plan=draft.model_dump(mode='json'),
                validation_error=record['attempts'][-1], valid_plans=[b['plan'].model_dump(mode='json') for b in valid])
            replacement = brain._generate(system_prompt=prompt, user_input=without_profile(source),
                output_schema=SearchQueryPlanLLM, recovery=True)
            replacement = SearchQueryPlanLLM.model_validate(replacement.model_dump())
            record['repaired_plan'] = replacement.model_dump(mode='json')
            validate_branch(replacement, record, recovery=True)
        except Exception as exc:
            entry = dict(status='failed', **failure('query_planning_recovery', exc))
            if runner.search_policy_version in {'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
                entry['validation_feedback']['plan_id'] = record['branch_id']
            record['attempts'].append(entry)
            record['status'] = 'failed'
        finally:
            if runner.search_policy_version in {'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
                record['correction_response_indices'] = list(range(record['correction_response_start'],
                    len(getattr(brain, 'model_response_history', []))))
    failed = [r for r in trace['branches'] if r['status'] == 'failed']
    trace['status'] = ('partial_result' if valid else 'failed') if failed else 'repaired'
    if runner.search_policy_version in {'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'} and all(r['status'] == 'valid' for r in trace['branches']):
        trace['status'] = 'passed'
    if failed:
        trace.update(final_error=failed[-1]['attempts'][-1]['error'],
            failure_stage=failed[-1]['attempts'][-1]['stage'])
    else:
        trace.update(final_error=None, failure_stage=None)
    if runner.search_policy_version in {'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'} and valid:
        from fashion_recommendation_v2.search.planning import condition_pool
        from fashion_recommendation_v2.search.planning import validate_initial_use
        try:
            trace['condition_pool_v50'] = condition_pool(requirements, source)
            trace['stylist_initial_use_v50'] = validate_initial_use(trace['condition_pool_v50'], valid,
                (trace.get('stylist_initial_use_v50') or {}).get('exception_reason') or output.stylist_nonuse_reason)
        except ValueError as exc:
            trace.update(status='failed', final_error=str(exc), failure_stage='initial_stylist_coverage',
                retained_valid_plans=[b['plan'].model_dump(mode='json') for b in valid])
            return [], conversion, trace
    return valid, conversion, trace if trace['original_error'] or runner.search_policy_version in {'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'} else None
