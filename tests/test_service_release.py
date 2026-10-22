"""Public snapshot dependency and service wiring checks; no paid API calls."""
from fashion_recommendation_v2.module_compat import import_module as _role_module
from fashion_recommendation_v2.module_compat import import_module
from types import SimpleNamespace


def test_current_service_factories(monkeypatch):
    from fashion_recommendation_v2.server.recommendation_factory import build_recommendation_service
    import fashion_recommendation_v2.llm.openai_adapter as adapter
    monkeypatch.setattr(adapter, 'OpenAIStructuredLLM', lambda **kwargs: SimpleNamespace(**kwargs, configure_unbounded_operations=lambda operations: None))
    service = build_recommendation_service(SimpleNamespace(), model='offline-placeholder')
    assert service.brain_factory().evaluation_version == 'v12'
    runner = service.runner_factory()
    assert runner.brain.evaluation_version == 'v12'
    assert runner.search.search_policy_version == 'v61'
    assert runner.stylist.evaluation_version == 'v8'
    assert runner.summary.version == 'v13'
    assert runner.relation.version == 'v9'
    assert runner.ranking.policy_version == 'ranking_eval_v17'


def test_current_dynamic_contract_dependencies():
    from fashion_recommendation_v2.search.contracts import get_search_contracts
    from fashion_recommendation_v2.orchestrator_policy import assessment_contract
    from fashion_recommendation_v2.relation.relation_contracts import get_relation_contract
    from fashion_recommendation_v2.ranking.ranking_contracts import scoring_for_policy
    from fashion_recommendation_v2.agents.preference_interpretation_runner import PreferenceAgent
    from fashion_recommendation_v2.agents.search_brain import SearchBrain
    from fashion_recommendation_v2.agents.search_runner import SearchVisualRunner
    contract = get_search_contracts('v61')
    for role in [contract.requirements, contract.planning, contract.product_evaluation, contract.ranking_observation]:
        assert role.prompts
        assert role.schemas
    assert contract.planning_code
    assert import_module('fashion_recommendation_v2.search.requirements_'+contract.requirements.version)
    orchestrator = assessment_contract('v12')
    from fashion_recommendation_v2.prompts._compat import resolve_prompt_module
    assert resolve_prompt_module('fashion_recommendation_v2.prompts.'+orchestrator.prompt_module)
    relation = get_relation_contract('v9')
    assert relation.prompt()
    assert relation.schema(relation.input_name)
    assert relation.schema(relation.output_name)
    assert relation.evidence()
    assert relation.scorer()
    assert import_module('fashion_recommendation_v2.'+relation.execution_module)
    from fashion_recommendation_v2.ranking.ranking_contracts import RANKING_V17_CONTRACT
    assert RANKING_V17_CONTRACT
    assert PreferenceAgent(SimpleNamespace(), version='v4').profile_schema
