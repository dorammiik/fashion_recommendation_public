"""Immutable fingerprints captured BEFORE public prompt consolidation."""
from fashion_recommendation_v2.module_compat import import_module as _role_module
import hashlib
import json
from pathlib import Path
import pytest
from prompt_capture import resolve
from prompt_capture import dynamic_prompts

FROZEN = json.loads((Path(__file__).parent/'fixtures/prompt_fingerprints.json').read_text())
CURRENT = json.loads((Path(__file__).parent/'fixtures/current_contract_fingerprints.json').read_text())['values']
STATIC = [key for key in FROZEN if not key.startswith('dynamic:')]


@pytest.mark.parametrize('key', STATIC)
def test_static_prompt_matches_before_consolidation(key):
    module, name = key.split(':')
    text = getattr(resolve(module), name)
    assert hashlib.sha256(text.encode('utf-8')).hexdigest() == CURRENT.get(key, FROZEN[key])


def test_dynamic_generation_and_correction_match_before_consolidation():
    actual = {'dynamic:'+key: hashlib.sha256(value.encode('utf-8')).hexdigest()
              for key, value in dynamic_prompts().items()}
    assert actual == {key: value for key, value in FROZEN.items() if key.startswith('dynamic:')}


def test_service_agents_use_frozen_prompts(monkeypatch):
    from types import SimpleNamespace
    from fashion_recommendation_v2.server.recommendation_factory import build_recommendation_service
    import fashion_recommendation_v2.llm.openai_adapter as adapter
    monkeypatch.setattr(adapter, 'OpenAIStructuredLLM', lambda **kwargs: SimpleNamespace(**kwargs, configure_unbounded_operations=lambda operations: None))
    runner = build_recommendation_service(SimpleNamespace(), model='offline').runner_factory()
    key = 'fashion_recommendation_v2.prompts.summary_v10:SUMMARY_PROMPT'
    assert hashlib.sha256(runner.summary.summary_prompt.encode()).hexdigest() == CURRENT.get(key, FROZEN[key])
    from fashion_recommendation_v2.agents.preference_interpretation_runner import PreferenceAgent
    agent = PreferenceAgent(SimpleNamespace(), version='v4')
    key = 'fashion_recommendation_v2.prompts.preference.interpretation.preference_interpretation_v4:PREFERENCE_INTERPRETATION_PROMPT'
    assert hashlib.sha256(agent.prompt.encode()).hexdigest() == CURRENT.get(key, FROZEN[key])
    assert runner.relation.version == 'v9'
    assert runner.stylist.evaluation_version == 'v8'
    assert runner.ranking.policy_version == 'ranking_eval_v17'
