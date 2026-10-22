"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- ranking ----

"""Backward-compatible public imports; implementation lives in Brain and Runner."""
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_validation import EvaluationBatchInput
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_validation import EvaluationBatchOutput
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_validation import EvaluationItem
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_validation import ItemJudgments
from fashion_recommendation_v2.agents.ranking_brain import RankingBrain
from fashion_recommendation_v2.agents.ranking_runner import RankingRunner
from fashion_recommendation_v2.agents.ranking_runner import RankingExecutionError
from fashion_recommendation_v2.search.product_validation import InvalidEvaluation
RankingAgent = RankingRunner
