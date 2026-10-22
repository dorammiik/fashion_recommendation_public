"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- ranking_brain ----

"""Text-only evaluation of Search metadata; no image loading or analysis."""
from pydantic import Field
from fashion_recommendation_v2.llm.base import StructuredLLM
from fashion_recommendation_v2.prompts.ranking import RANKING_PROMPT
from fashion_recommendation_v2.schemas.base import StrictBaseModel
from fashion_recommendation_v2.schemas.price import PriceConversion
from fashion_recommendation_v2.schemas.search.requirements.search_requirements import ResolvedRequirements_legacy as ResolvedRequirements
from fashion_recommendation_v2.schemas.product_evidence import HardConstraintAssessment
from fashion_recommendation_v2.schemas.product_evidence import RankingItemIssue
from fashion_recommendation_v2.schemas.product_evidence import PreferenceObservation
from fashion_recommendation_v2.schemas.product_evidence import RequirementJudgment
from fashion_recommendation_v2.schemas.product_evidence import EvidenceConflict
from fashion_recommendation_v2.schemas.product_evidence import DiversityFeature
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_validation import EvaluationItem
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_validation import EvaluationBatchInput
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_validation import ItemJudgments
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_validation import EvaluationBatchOutput

@_preserve_class('RankingBrain', 'fashion_recommendation_v2.agents.ranking_brain')
class RankingBrain:

    def __init__(self, llm: StructuredLLM, *, policy_version=None):
        self.llm = llm
        self.policy_version = policy_version

    def analyze(self, request: EvaluationBatchInput) -> EvaluationBatchOutput:
        return self.llm.generate(system_prompt=RANKING_PROMPT, user_input=request, output_schema=EvaluationBatchOutput)

    def request_profile_lookup(self):
        from fashion_recommendation_v2.ranking.ranking_contracts import RANKING_V11_CONTRACT
        from fashion_recommendation_v2.ranking.ranking_contracts import RANKING_V14_CONTRACT
        model = RANKING_V14_CONTRACT['profile_lookup_model'] if self.policy_version in {RANKING_V14_CONTRACT['policy'], 'ranking_eval_v15', 'ranking_eval_v16', 'ranking_eval_v17'} else RANKING_V11_CONTRACT['default_model']
        return self.llm.request_profile_lookup(model=model)

    def assess_preference(self, request):
        from fashion_recommendation_v2.prompts.ranking import ranking_personalization_v11__PREFERENCE_PROMPT as PREFERENCE_PROMPT
        from fashion_recommendation_v2.schemas.ranking_personalization.ranking_personalization import PreferenceAssessmentV11_v11 as PreferenceAssessmentV11
        from fashion_recommendation_v2.ranking.ranking_contracts import RANKING_V11_CONTRACT
        from fashion_recommendation_v2.schemas.ranking_personalization.ranking_personalization import PreferenceAssessmentInputV12
        from fashion_recommendation_v2.schemas.ranking_personalization.ranking_personalization import PreferenceAssessmentV12
        model = RANKING_V11_CONTRACT['default_model']
        output_schema = PreferenceAssessmentV11
        if isinstance(request, PreferenceAssessmentInputV12):
            from fashion_recommendation_v2.prompts.ranking import PREFERENCE_PROMPT
            from fashion_recommendation_v2.ranking.ranking_contracts import RANKING_V12_CONTRACT
            model = RANKING_V12_CONTRACT['default_model']
            output_schema = PreferenceAssessmentV12
        if self.policy_version in {'ranking_eval_v16', 'ranking_eval_v17'}:
            from fashion_recommendation_v2.prompts.ranking import PREFERENCE_PROMPT_ranking_personalization_v16 as PREFERENCE_PROMPT
            from fashion_recommendation_v2.schemas.ranking_personalization.ranking_personalization import PreferenceAssessmentV16_ranking_personalization_v16 as PreferenceAssessmentV16
            output_schema = PreferenceAssessmentV16
        return self.llm.generate(system_prompt=PREFERENCE_PROMPT, user_input=request, output_schema=output_schema, call_model_settings={'model': model})
