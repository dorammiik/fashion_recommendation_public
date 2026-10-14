"""Explicit opt-in Ranking wiring; existing service/Runner defaults stay v6."""
from fashion_recommendation_v2.module_compat import import_module as _role_module
from fashion_recommendation_v2.schemas.ranking import RANKING_V8
from fashion_recommendation_v2.schemas.ranking import RANKING_V8_RELATION

RANKING_V8_CONTRACT = dict(
    policy=RANKING_V8, relation_policy=RANKING_V8_RELATION,
    observations='tools.ranking_observations_v7.observation_assessments',
    requirement_derivation='tools.ranking_judgments_v6',
    scoring='ranking.ranking_scoring_v8', output='schemas.ranking.FinalRanking',
    validation='schemas.ranking_v0.validate_ranking_v0_against',
    similarity_relation_version='v4',
    search_contracts='search.contracts',
    saved_search_prompt=None,
    metadata_fallback='agents.ranking_brain.RankingBrain',
)


def v8_scoring():
    from fashion_recommendation_v2.module_compat import import_module
    return import_module('fashion_recommendation_v2.' + RANKING_V8_CONTRACT['scoring'])


RANKING_V9_CONTRACT = dict(RANKING_V8_CONTRACT, policy='ranking_eval_v9',
    relation_policy='ranking_eval_v9_relation', observations='search.product_evaluation_v36',
    requirement_derivation='ranking.ranking_scoring_v9.assessments', scoring='ranking.ranking_scoring_v9',
    required_search_version='v36', saved_search_prompt=None, metadata_fallback=None,
    base_relation_policy='ranking.ranking_scoring_v8', diversity_policy='ranking.ranking_policy_v9',
    consistency_policy='ranking.ranking_policy_v9',
    source_schema='schemas.search.product_evaluation.search_product_evaluation_v36')

# Explicit opt-in input revision; v36/v9 arithmetic remains unchanged.
RANKING_V9_SEARCH_V37_CONTRACT = dict(RANKING_V9_CONTRACT, required_search_version='v37',
    similarity_relation_version='v5', condition_routing='search.requirements_v37.ranking_condition_ids',
    score_application='ranking.ranking_scoring_v9.routed_score', inactive_relevance=None)


def v9_scoring():
    from fashion_recommendation_v2.module_compat import import_module
    return import_module('fashion_recommendation_v2.' + RANKING_V9_CONTRACT['scoring'])


def scoring_for_policy(policy):
    """Shared score-policy selection for Runner and output validation."""
    if policy in {RANKING_V9_CONTRACT['policy'], RANKING_V9_CONTRACT['relation_policy'],
                  RANKING_V10_CONTRACT['policy'], RANKING_V10_CONTRACT['relation_policy'],
                  'ranking_eval_v11', 'ranking_eval_v11_relation', 'ranking_eval_v12', 'ranking_eval_v12_relation', 'ranking_eval_v13', 'ranking_eval_v13_relation', 'ranking_eval_v14', 'ranking_eval_v14_relation', 'ranking_eval_v15', 'ranking_eval_v15_relation'}:
        return v9_scoring()
    if policy in {RANKING_V8_CONTRACT['policy'], RANKING_V8_CONTRACT['relation_policy']}:
        return v8_scoring()
    raise ValueError(f'Unsupported shared Ranking score policy: {policy}')


RANKING_V10_CONTRACT = dict(RANKING_V9_SEARCH_V37_CONTRACT, policy='ranking_eval_v10',
    relation_policy='ranking_eval_v10_relation', eligibility='ranking.partial_evaluation_v10',
    validation='ranking.partial_evaluation_v10.validate_against', recommended_relation_version='v7')


RANKING_V11_CONTRACT = dict(RANKING_V10_CONTRACT, policy='ranking_eval_v11',
    relation_policy='ranking_eval_v11_relation', recommended_relation_version='v8',
    input='schemas.ranking_v11.RankingAgentInputV11',
    preference_schema='schemas.ranking_personalization.ranking_personalization_v11',
    preference_prompt='prompts.ranking_personalization.ranking_personalization_v11',
    preference_execution='ranking.personalization_v11',
    preference_profile='preference-interpretation-v4',
    validation='ranking.personalization_v11.validate_against',
    default_model='gpt-5.6-sol', reasoning_effort='api_default',
    max_candidates=50, max_concurrency=20, max_calls=100, max_item_calls=2,
    orchestration_version='v2')


RANKING_V12_CONTRACT = dict(RANKING_V11_CONTRACT, default_model='gpt-6-luna', policy='ranking_eval_v12',
    relation_policy='ranking_eval_v12_relation', input='schemas.ranking_v12.RankingAgentInputV12',
    preference_schema='schemas.ranking_personalization.ranking_personalization_v12',
    preference_prompt='prompts.ranking_personalization.ranking_personalization_v12',
    preference_execution='ranking.personalization_v12',
    validation='ranking.personalization_v12.validate_against',
    selection='personalized_then_baseline', scope_precedence='scope_before_request_exclusion')


RANKING_V13_CONTRACT = dict(RANKING_V12_CONTRACT, policy='ranking_eval_v13',
    relation_policy='ranking_eval_v13_relation', input='schemas.ranking_v13.RankingAgentInputV13',
    similarity_personalization='cold', record_format='personalization_v12')


# v14 retains v13 semantics and its unchanged input/prompt contracts.
RANKING_V14_CONTRACT = dict(RANKING_V13_CONTRACT, policy='ranking_eval_v14',
    profile_lookup_model='gpt-6-luna',
    relation_policy='ranking_eval_v14_relation', validation_reuse='request_exact_snapshot')


RANKING_V15_CONTRACT = dict(RANKING_V14_CONTRACT, policy='ranking_eval_v15',
    relation_policy='ranking_eval_v15_relation', max_concurrency=40)
