"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- recommendation_factory ----

"""Live factories. Every request gets independent mutable agent/runner instances."""

@_preserve_function('build_recommendation_service', 'fashion_recommendation_v2.server.recommendation_factory')
def build_recommendation_service(preference_service, *, model):
    from fashion_recommendation_v2.server.recommendation_service import RecommendationService
    from fashion_recommendation_v2.llm.openai_adapter import OpenAIStructuredLLM
    from fashion_recommendation_v2.agents.orchestrator_brain import OrchestratorBrain
    from fashion_recommendation_v2.agents.orchestrator_runner import OrchestratorRunner
    from fashion_recommendation_v2.agents.planner import PlannerAgent
    from fashion_recommendation_v2.agents.planner import PLANNER_MODEL
    from fashion_recommendation_v2.agents.planner import PLANNER_REASONING_EFFORT
    from fashion_recommendation_v2.agents.planner import PLANNER_MAX_OUTPUT_TOKENS
    from fashion_recommendation_v2.agents.stylist_brain import StylistAgent
    from fashion_recommendation_v2.agents.ranking import RankingAgent
    from fashion_recommendation_v2.agents.summary import SummaryAgent
    from fashion_recommendation_v2.agents.relation import RelationAgent
    from fashion_recommendation_v2.summary.summary_policy import SUMMARY_V12_MODEL
    from fashion_recommendation_v2.relation.relation_contracts import get_relation_contract

    def brain_factory():
        return OrchestratorBrain(llm=OpenAIStructuredLLM(model=model), version='v12')

    def runner_factory():
        llm = OpenAIStructuredLLM(model=model)
        llm.configure_unbounded_operations({'StylistCopyV6'})
        planner_llm = OpenAIStructuredLLM(model=PLANNER_MODEL, operation_settings={'ExecutionPlan': {'model': PLANNER_MODEL, 'reasoning_effort': PLANNER_REASONING_EFFORT}})

        class LazySearch:
            search_policy_version = 'v61'

            def run(self, request):
                from fashion_recommendation_v2.agents.search_brain import SearchBrain
                from fashion_recommendation_v2.agents.search_runner import SearchVisualRunner
                from fashion_recommendation_v2.search.policy import DEFAULT_SEARCH_MODEL
                from fashion_recommendation_v2.search.policy import search_model_routes
                from fashion_recommendation_v2.search.policy import search_policy
                from fashion_recommendation_v2.search.policy import search_default_target_candidate_count
                from fashion_recommendation_v2.tools.ebay_client import EBayLiveBrowseClient
                from fashion_recommendation_v2.tools.ebay_search import EBaySearchTool
                from fashion_recommendation_v2.tools.price_client import FrankfurterFXClient
                from fashion_recommendation_v2.tools.price_translate import PriceFXRuntime
                version = self.search_policy_version
                search_llm = OpenAIStructuredLLM(model=DEFAULT_SEARCH_MODEL, operation_settings=search_model_routes(version))
                search_llm.configure_unbounded_operations({'SearchInitialPlansV16'})
                tool = EBaySearchTool(EBayLiveBrowseClient.from_env(), detail_workers=5)
                brain = SearchBrain(search_llm, search_tool=tool)
                brain.ranking_observation_version = 'v5'
                # expose intake diagnostics even when the lazy runner fails
                self.search_brain = brain
                runner = SearchVisualRunner(search_brain=brain, search_tool=tool, target_candidate_count=max(search_default_target_candidate_count(version), request.requested_count), search_policy_version=version, minimum_search_attempts=1, max_attempts=search_policy(version).query_budget, search_limit=20, price_fx_runtime=PriceFXRuntime(FrankfurterFXClient()))
                runner.progress_callback = getattr(self, 'progress_callback', None)
                runner.candidate_committed_callback = getattr(self, 'candidate_committed_callback', None)
                return runner.run(request)
        return OrchestratorRunner(brain=OrchestratorBrain(llm=llm, version='v12'), planner=PlannerAgent(planner_llm, max_output_tokens=PLANNER_MAX_OUTPUT_TOKENS), stylist=StylistAgent(llm=llm, version='v8'), search=LazySearch(), ranking=RankingAgent(llm=llm, policy_version='ranking_eval_v17'), relation=RelationAgent(llm=OpenAIStructuredLLM(model=get_relation_contract('v9').default_model), version='v9'), summary=SummaryAgent(llm=OpenAIStructuredLLM(model=SUMMARY_V12_MODEL), version='v13'))
    return RecommendationService(preference_service, brain_factory=brain_factory, runner_factory=runner_factory, profile_updates_enabled=True, default_personalization_mode='warm')
