"""Explicit Relation version wiring; no Search/Ranking policy changes."""
from fashion_recommendation_v2.module_compat import import_module as _role_module
from fashion_recommendation_v2.prompts._compat import resolve_prompt_module
from dataclasses import dataclass
from fashion_recommendation_v2.module_compat import import_module


@dataclass(frozen=True)
class RelationContract:
    schema_module: str
    input_name: str
    output_name: str
    prompt_module: str
    prompt_name: str
    evidence_module: str | None = None
    validation_name: str | None = None
    capture_response: bool = False
    scoring_module: str | None = None
    ratio_validation_name: str | None = None
    evaluation_revision: str | None = None
    breakdown_field: str = 'score_breakdowns_v3'
    recommended_ranking_policy: str = 'ranking_eval_v7'
    output_schema_builder: str | None = None
    execution_module: str | None = None
    default_model: str = "gpt-5.6-sol"

    def schema(self, name):
        module = 'relation' if name == 'RelationBatchOutput' else self.schema_module
        return getattr(import_module('fashion_recommendation_v2.schemas.' + module), name)

    def prompt(self):
        return getattr(resolve_prompt_module('fashion_recommendation_v2.prompts.' + self.prompt_module), self.prompt_name)

    def evidence(self):
        return import_module('fashion_recommendation_v2.' + self.evidence_module)

    def scorer(self):
        return import_module('fashion_recommendation_v2.' + self.scoring_module)


CONTRACTS = {
    'v8': RelationContract('relation_v6', 'RelationEvidenceBatchV6', 'RelationBatchOutputV6',
        'relation_v6', 'RELATION_PROMPT_V6', 'relation.relation_evidence_v6', 'validate_references', True,
        'relation.relation_scoring_v5', 'validate_ratio', 'relation-v8-gpt-6-luna-1',
        'score_breakdowns_v5', 'ranking_eval_v10', 'output_schema', 'relation.execution_v7', 'gpt-6-luna'),
    'v7': RelationContract('relation_v6', 'RelationEvidenceBatchV6', 'RelationBatchOutputV6',
        'relation_v6', 'RELATION_PROMPT_V6', 'relation.relation_evidence_v6', 'validate_references', True,
        'relation.relation_scoring_v5', 'validate_ratio', 'relation-v7-isolated-candidates-20-workers-1',
        'score_breakdowns_v5', 'ranking_eval_v10', 'output_schema', 'relation.execution_v7'),
    'v6': RelationContract('relation_v6', 'RelationEvidenceBatchV6', 'RelationBatchOutputV6',
        'relation_v6', 'RELATION_PROMPT_V6', 'relation.relation_evidence_v6', 'validate_references', True,
        'relation.relation_scoring_v5', 'validate_ratio', 'relation-v6-search-observation-selection-1',
        'score_breakdowns_v5', 'ranking_eval_v9', 'output_schema'),
    'v5': RelationContract('relation_v5', 'RelationEvidenceBatchV5', 'RelationBatchOutputV5',
        'relation_v5', 'RELATION_PROMPT_V5', 'relation.relation_evidence_v5', 'validate_references', True,
        'relation.relation_scoring_v5', 'validate_ratio', 'relation-v5-source-selection-1', 'score_breakdowns_v5', 'ranking_eval_v9', 'output_schema'),
    'legacy': RelationContract('relation', 'RelationBatchInput', 'RelationBatchOutput', 'relation', 'RELATION_PROMPT'),
    'v0': RelationContract('relation_v0', 'RelationEvidenceBatchV0', 'RelationBatchOutput',
        'relation_v0', 'RELATION_PROMPT_V0', 'schemas.relation_v0', 'validate_v0_references'),
    'v2': RelationContract('relation_v2', 'RelationEvidenceBatchV2', 'RelationBatchOutputV2',
        'relation_v2', 'RELATION_PROMPT_V2', 'relation.relation_evidence', 'validate_references', True,
        evaluation_revision='relation-v2-saved-search-evidence-1'),
    'v3': RelationContract('relation_v3', 'RelationEvidenceBatchV3', 'RelationBatchOutputV3',
        'relation_v3', 'RELATION_PROMPT_V3', 'relation.relation_evidence_v3', 'validate_references', True,
        'relation.relation_scoring_v3', 'validate_ratio', 'relation-v3-facet-weighted-1'),
    'v4': RelationContract('relation_v4', 'RelationEvidenceBatchV4', 'RelationBatchOutputV4',
        'relation_v4', 'RELATION_PROMPT_V4', 'relation.relation_evidence_v4', 'validate_references', True,
        'relation.relation_scoring_v4', 'validate_ratio', 'relation-v4-similarity-coverage-1', 'score_breakdowns_v4', 'ranking_eval_v8'),
}


def get_relation_contract(version):
    return CONTRACTS[version]
