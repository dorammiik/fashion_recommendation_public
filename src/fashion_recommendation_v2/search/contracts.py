"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- contracts ----

"""search.contracts: definitions relocated without semantic changes."""
from types import MappingProxyType
from fashion_recommendation_v2.prompts.search.planning import V21Prompts
from fashion_recommendation_v2.prompts.search.planning import V24Prompts as _V24Planning
from dataclasses import dataclass
from fashion_recommendation_v2.module_compat import import_module as import_module

@_preserve_class('RoleContract', 'fashion_recommendation_v2.search.contracts')
@dataclass(frozen=True)
class RoleContract:
    role: str
    version: str

    @property
    def relative_module(self):
        return f'search.{self.role}.search_{self.role}_{self.version}'

    @property
    def prompts(self):
        return import_module('fashion_recommendation_v2.prompts.' + self.relative_module)

    @property
    def schemas(self):
        return import_module('fashion_recommendation_v2.schemas.' + self.relative_module)

@_preserve_class('SearchContracts', 'fashion_recommendation_v2.search.contracts')
@dataclass(frozen=True)
class SearchContracts:
    version: str
    requirements: RoleContract
    planning: RoleContract
    product_evaluation: RoleContract
    ranking_observation: RoleContract
    # Product prompts/audits keep v29; v30 candidate record isolation is code-only.
    item_normalization: RoleContract | None = RoleContract("item_normalization", "v24")
    relation_observation: RoleContract | None = None
    candidate_validation: str = 'evidence_context_reuse'
    planning_code_version: str | None = None

    @property
    def planning_code(self):
        """Code helpers can stay shared when only planning prompts change."""
        version = self.planning_code_version or self.planning.version
        return import_module(f'fashion_recommendation_v2.search.planning_{version}')
SEARCH_RELEASES = MappingProxyType({'v61': SearchContracts('v61', RoleContract('requirements', 'v58'), RoleContract('planning', 'v60'), RoleContract('product_evaluation', 'v59'), RoleContract('ranking_observation', 'v5'), item_normalization=None, candidate_validation='fresh_after_dedup', planning_code_version='v50'), 'v60': SearchContracts('v60', RoleContract('requirements', 'v58'), RoleContract('planning', 'v60'), RoleContract('product_evaluation', 'v59'), RoleContract('ranking_observation', 'v5'), item_normalization=None, candidate_validation='fresh_after_dedup', planning_code_version='v50'), 'v59': SearchContracts('v59', RoleContract('requirements', 'v58'), RoleContract('planning', 'v59'), RoleContract('product_evaluation', 'v59'), RoleContract('ranking_observation', 'v5'), item_normalization=None, candidate_validation='fresh_after_dedup', planning_code_version='v50'), 'v58': SearchContracts('v58', RoleContract('requirements', 'v58'), RoleContract('planning', 'v58'), RoleContract('product_evaluation', 'v57'), RoleContract('ranking_observation', 'v5'), item_normalization=None, candidate_validation='fresh_after_dedup', planning_code_version='v50'), 'v57': SearchContracts('v57', RoleContract('requirements', 'v57'), RoleContract('planning', 'v57'), RoleContract('product_evaluation', 'v57'), RoleContract('ranking_observation', 'v5'), item_normalization=None, candidate_validation='fresh_after_dedup', planning_code_version='v50'), 'v56': SearchContracts('v56', RoleContract('requirements', 'v54'), RoleContract('planning', 'v54'), RoleContract('product_evaluation', 'v45'), RoleContract('ranking_observation', 'v5'), item_normalization=None, candidate_validation='fresh_after_dedup', planning_code_version='v50'), 'v55': SearchContracts('v55', RoleContract('requirements', 'v54'), RoleContract('planning', 'v54'), RoleContract('product_evaluation', 'v45'), RoleContract('ranking_observation', 'v5'), item_normalization=None, candidate_validation='fresh_after_dedup', planning_code_version='v50'), 'v54': SearchContracts('v54', RoleContract('requirements', 'v54'), RoleContract('planning', 'v54'), RoleContract('product_evaluation', 'v45'), RoleContract('ranking_observation', 'v5'), item_normalization=None, candidate_validation='fresh_after_dedup', planning_code_version='v50'), 'v53': SearchContracts('v53', RoleContract('requirements', 'v50'), RoleContract('planning', 'v52'), RoleContract('product_evaluation', 'v45'), RoleContract('ranking_observation', 'v5'), item_normalization=None, candidate_validation='fresh_after_dedup', planning_code_version='v50'), 'v52': SearchContracts('v52', RoleContract('requirements', 'v50'), RoleContract('planning', 'v52'), RoleContract('product_evaluation', 'v45'), RoleContract('ranking_observation', 'v5'), item_normalization=None, candidate_validation='fresh_after_dedup', planning_code_version='v50'), 'v51': SearchContracts('v51', RoleContract('requirements', 'v50'), RoleContract('planning', 'v51'), RoleContract('product_evaluation', 'v45'), RoleContract('ranking_observation', 'v5'), item_normalization=None, candidate_validation='fresh_after_dedup', planning_code_version='v50'), 'v50': SearchContracts('v50', RoleContract('requirements', 'v50'), RoleContract('planning', 'v50'), RoleContract('product_evaluation', 'v45'), RoleContract('ranking_observation', 'v5'), item_normalization=None, candidate_validation='fresh_after_dedup'), 'v49': SearchContracts('v49', RoleContract('requirements', 'v49'), RoleContract('planning', 'v49'), RoleContract('product_evaluation', 'v45'), RoleContract('ranking_observation', 'v5'), item_normalization=None, candidate_validation='fresh_after_dedup'), 'v48': SearchContracts('v48', RoleContract('requirements', 'v48'), RoleContract('planning', 'v47'), RoleContract('product_evaluation', 'v45'), RoleContract('ranking_observation', 'v5'), item_normalization=None, candidate_validation='fresh_after_dedup'), 'v47': SearchContracts('v47', RoleContract('requirements', 'v47'), RoleContract('planning', 'v47'), RoleContract('product_evaluation', 'v45'), RoleContract('ranking_observation', 'v5'), item_normalization=None, candidate_validation='fresh_after_dedup'), 'v46': SearchContracts('v46', RoleContract('requirements', 'v46'), RoleContract('planning', 'v32'), RoleContract('product_evaluation', 'v45'), RoleContract('ranking_observation', 'v5'), item_normalization=None, candidate_validation='fresh_after_dedup'), 'v45': SearchContracts('v45', RoleContract('requirements', 'v45'), RoleContract('planning', 'v32'), RoleContract('product_evaluation', 'v45'), RoleContract('ranking_observation', 'v5'), item_normalization=None, candidate_validation='fresh_after_dedup'), 'v44': SearchContracts('v44', RoleContract('requirements', 'v40'), RoleContract('planning', 'v32'), RoleContract('product_evaluation', 'v44'), RoleContract('ranking_observation', 'v5'), item_normalization=None, candidate_validation='fresh_after_dedup'), 'v43': SearchContracts('v43', RoleContract('requirements', 'v40'), RoleContract('planning', 'v32'), RoleContract('product_evaluation', 'v43'), RoleContract('ranking_observation', 'v5'), item_normalization=None, candidate_validation='fresh_after_dedup'), 'v42': SearchContracts('v42', RoleContract('requirements', 'v40'), RoleContract('planning', 'v32'), RoleContract('product_evaluation', 'v42'), RoleContract('ranking_observation', 'v5'), item_normalization=None, candidate_validation='fresh_after_dedup'), 'v41': SearchContracts('v41', RoleContract('requirements', 'v40'), RoleContract('planning', 'v32'), RoleContract('product_evaluation', 'v41'), RoleContract('ranking_observation', 'v5'), item_normalization=None, candidate_validation='fresh_after_dedup'), 'v40': SearchContracts('v40', RoleContract('requirements', 'v40'), RoleContract('planning', 'v32'), RoleContract('product_evaluation', 'v40'), RoleContract('ranking_observation', 'v5'), item_normalization=None, candidate_validation='fresh_after_dedup'), 'v37': SearchContracts('v37', RoleContract('requirements', 'v37'), RoleContract('planning', 'v32'), RoleContract('product_evaluation', 'v36'), RoleContract('ranking_observation', 'v5'), item_normalization=None, candidate_validation='fresh_after_dedup'), 'v36': SearchContracts('v36', RoleContract('requirements', 'v35'), RoleContract('planning', 'v32'), RoleContract('product_evaluation', 'v36'), RoleContract('ranking_observation', 'v5'), item_normalization=None, candidate_validation='fresh_after_dedup'), 'v35': SearchContracts('v35', RoleContract('requirements', 'v35'), RoleContract('planning', 'v32'), RoleContract('product_evaluation', 'v32'), RoleContract('ranking_observation', 'v5'), item_normalization=None), 'v34': SearchContracts('v34', RoleContract('requirements', 'v31'), RoleContract('planning', 'v32'), RoleContract('product_evaluation', 'v32'), RoleContract('ranking_observation', 'v5'), item_normalization=None), "v24": SearchContracts("v24", RoleContract('requirements', "v24"), RoleContract('planning', "v24"), RoleContract('product_evaluation', "v24"), RoleContract('ranking_observation', 'v5')), 'v25': SearchContracts('v25', RoleContract('requirements', 'v25'), RoleContract('planning', 'v25'), RoleContract('product_evaluation', 'v25'), RoleContract('ranking_observation', 'v5')), 'v26': SearchContracts('v26', RoleContract('requirements', 'v26'), RoleContract('planning', 'v25'), RoleContract('product_evaluation', 'v26'), RoleContract('ranking_observation', 'v5'), item_normalization=None), 'v29': SearchContracts('v29', RoleContract('requirements', 'v26'), RoleContract('planning', 'v29'), RoleContract('product_evaluation', 'v29'), RoleContract('ranking_observation', 'v5'), item_normalization=None), 'v30': SearchContracts('v30', RoleContract('requirements', 'v30'), RoleContract('planning', 'v29'), RoleContract('product_evaluation', 'v29'), RoleContract('ranking_observation', 'v5'), item_normalization=None), 'v33': SearchContracts('v33', RoleContract('requirements', 'v31'), RoleContract('planning', 'v32'), RoleContract('product_evaluation', 'v33'), RoleContract('ranking_observation', 'v5'), item_normalization=None), 'v32': SearchContracts('v32', RoleContract('requirements', 'v31'), RoleContract('planning', 'v32'), RoleContract('product_evaluation', 'v32'), RoleContract('ranking_observation', 'v5'), item_normalization=None), 'v31': SearchContracts('v31', RoleContract('requirements', 'v31'), RoleContract('planning', 'v31'), RoleContract('product_evaluation', 'v29'), RoleContract('ranking_observation', 'v5'), item_normalization=None)})
SEARCH_EVAL_CONTRACTS = MappingProxyType({'v61': SEARCH_RELEASES['v61'], 'v60': SEARCH_RELEASES['v60'], 'v59': SEARCH_RELEASES['v59'], 'v58': SEARCH_RELEASES['v58'], 'v57': SEARCH_RELEASES['v57'], 'v54': SEARCH_RELEASES['v54'], 'v56': SEARCH_RELEASES['v56'], 'v55': SEARCH_RELEASES['v55'], 'v53': SEARCH_RELEASES['v53'], 'v52': SEARCH_RELEASES['v52'], 'v51': SEARCH_RELEASES['v51'], 'v50': SEARCH_RELEASES['v50'], 'v49': SEARCH_RELEASES['v49'], 'v48': SEARCH_RELEASES['v48'], 'v47': SEARCH_RELEASES['v47'], 'v46': SEARCH_RELEASES['v46'], 'v40': SEARCH_RELEASES['v40'], 'v41': SEARCH_RELEASES['v41'], 'v45': SEARCH_RELEASES['v45'], 'v44': SEARCH_RELEASES['v44'], 'v43': SEARCH_RELEASES['v43'], 'v42': SEARCH_RELEASES['v42'], 'v37': SEARCH_RELEASES['v37'], 'v36': SEARCH_RELEASES['v36'], 'v35': SEARCH_RELEASES['v35'], 'v27': SEARCH_RELEASES['v26'], 'v28': SEARCH_RELEASES['v26'], 'v29': SEARCH_RELEASES['v29'], 'v30': SEARCH_RELEASES['v30'], 'v31': SEARCH_RELEASES['v31'], 'v32': SEARCH_RELEASES['v32'], 'v33': SEARCH_RELEASES['v33'], 'v34': SEARCH_RELEASES['v34']})
# Evaluation-only workload experiment: reuse exactly the v26 semantic contracts.
# Explicit eval-only A/B connection. Both arms use the same role contracts,
# This does not register v27 as a production Search policy or change its defaults.
# prompts, response schemas and model/budget policy; only selected code gates differ.
SEARCH_CODE_VALIDATION_TEST_CONTRACTS = MappingProxyType({'A': SEARCH_RELEASES['v30'], 'B': SEARCH_RELEASES['v30']})

@_preserve_function('get_search_contracts', 'fashion_recommendation_v2.search.contracts')
def get_search_contracts(version, *, relation_observation_version=None):
    try:
        selected = SEARCH_RELEASES[version]
    except KeyError:
        raise ValueError(f'No role contract bundle registered for Search {version}.') from None
    if relation_observation_version is None:
        return selected
    if relation_observation_version != 'v0':
        raise ValueError(f'Unknown Relation observation contract: {relation_observation_version}')
    from dataclasses import replace
    return replace(selected, relation_observation=RoleContract('relation_observation', relation_observation_version))

@_preserve_function('search_schemas', 'fashion_recommendation_v2.search.contracts')
# v34 changes image-call execution limits only; v32's role contracts stay frozen.
def search_schemas(version, *, purpose='requirements'):
    role = 'requirements' if purpose == 'extraction' else purpose
    if role not in {'requirements', 'planning', 'product_evaluation', 'ranking_observation', "item_normalization"}:
        raise ValueError(f'Unknown schema purpose: {purpose}; select Relation observations explicitly.')
    contract = getattr(get_search_contracts(version), role)
    if contract is None:
        raise ValueError(f'Search {version} does not use {role}.')
    return contract.schemas
_PLANNING = {'v16': 'v16', 'v18': 'v18', 'v19': 'v19', 'v20': 'v20'}
_EXTRACTION = {'v15': 'v15', 'v16': 'v16', 'v18': 'v18', 'v19': 'v18', 'v20': 'v18', 'v21': 'v18', 'v22': 'v18', 'v23': 'v18'}

@_preserve_function('search_prompts', 'fashion_recommendation_v2.search.contracts')
def search_prompts(version, *, purpose='planning'):
    if version in SEARCH_RELEASES:
        role = 'requirements' if purpose == 'extraction' else purpose
        if role not in {'requirements', 'planning', 'product_evaluation', 'ranking_observation', "item_normalization"}:
            raise ValueError(f'Unknown prompt purpose: {purpose}; select Relation observations explicitly.')
        contract = getattr(get_search_contracts(version), role)
        if contract is None:
            raise ValueError(f'Search {version} does not use {role}.')
        return contract.prompts
    if purpose not in {'planning', 'extraction'}:
        raise ValueError(f'Unknown prompt purpose: {purpose}')
    if version in {'v21', 'v22', 'v23'} and purpose == 'planning':
        return V21Prompts
    table = _EXTRACTION if purpose == 'extraction' else _PLANNING
    role = 'requirements' if purpose == 'extraction' else 'planning'
    return import_module(f'fashion_recommendation_v2.prompts.search.{role}.search_{role}_' + table[version])

@_preserve_class('V24Prompts', 'fashion_recommendation_v2.search.contracts')
class V24Prompts(_V24Planning):
    from fashion_recommendation_v2.prompts.search.requirements import EXTRACTION_CONTRACT
    from fashion_recommendation_v2.prompts.search.requirements import audit_prompt as _audit_prompt
    audit_prompt = staticmethod(_audit_prompt)

@_preserve_function('thumbnail_quality_contract', 'fashion_recommendation_v2.search.contracts')
def thumbnail_quality_contract(version='v2'):
    if version == 'v3':
        from fashion_recommendation_v2.prompts.search.ranking_observation import THUMBNAIL_QUALITY_V3_CONTRACT
        return THUMBNAIL_QUALITY_V3_CONTRACT
    if version == 'v2':
        from fashion_recommendation_v2.prompts.search.ranking_observation import THUMBNAIL_QUALITY_V2_CONTRACT
        return THUMBNAIL_QUALITY_V2_CONTRACT
    if version == 'v1':
        from fashion_recommendation_v2.prompts.search.ranking_observation import THUMBNAIL_QUALITY_V1_CONTRACT
        return THUMBNAIL_QUALITY_V1_CONTRACT
    raise ValueError(f'Unsupported thumbnail rubric version: {version}')

@_preserve_function('build_visual_batch_prompt', 'fashion_recommendation_v2.search.contracts')
def build_visual_batch_prompt(context):
    version = context.get('search_policy_version')
    if version in SEARCH_RELEASES:
        return get_search_contracts(version).product_evaluation.prompts.build_visual_batch_prompt(context)
    selected = version if version in SUPPORTED_PRODUCT_PROMPTS else 'v2'
    module = import_module(f'fashion_recommendation_v2.prompts.search.product_evaluation.search_product_evaluation_{selected}')
    return module.build_visual_batch_prompt(context)
SUPPORTED_PRODUCT_PROMPTS = frozenset(['v2', 'v3', 'v4', 'v5', 'v6', 'v7', 'v8', 'v9', 'v10', 'v11', 'v12', 'v13', 'v14', 'v15', 'v16', 'v18', 'v19', 'v20', 'v21', 'v22', 'v23', "v24", 'v25'])

@_preserve_function('product_evaluation_schema', 'fashion_recommendation_v2.search.contracts')
def product_evaluation_schema(version, count, context):
    # All Search request deadlines disabled.
    # Full Search; image calls have no timeout/retry.
    # Same execution budget; recoverable requirements.
    if version in SEARCH_RELEASES:
        return get_search_contracts(version).product_evaluation.schemas.output_schema(count, context)
    # Preserve the historical default branch for unversioned legacy callers.
    selected = version if version in SUPPORTED_PRODUCT_PROMPTS else 'v2'
    module = import_module(f'fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation_{selected}')
    return module.output_schema(count, context)

@_preserve_function('requirements_schema', 'fashion_recommendation_v2.search.contracts')
def requirements_schema(version, source):
    from fashion_recommendation_v2.search.policy import search_policy
    from fashion_recommendation_v2.schemas.search.requirements.search_requirements import RequirementsExtractionV7
    from fashion_recommendation_v2.schemas.search.requirements.search_requirements import RequirementsExtractionV8_legacy as RequirementsExtractionV8
    policy = search_policy(version)
    if version in {"v24", 'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
        return search_schemas(version, purpose='requirements').extraction_schema(source)
    if policy.enabled('compact_strategy_context'):
        from fashion_recommendation_v2.schemas.search.requirements.search_requirements import RequirementsExtractionV15_v15 as RequirementsExtractionV15
        return RequirementsExtractionV15
    if policy.enabled('keyed_condition_contract'):
        from fashion_recommendation_v2.schemas.search.requirements.search_requirements import RequirementsExtractionV14_v14 as RequirementsExtractionV14
        return RequirementsExtractionV14
    return RequirementsExtractionV8 if policy.enabled('scoped_requirements') else RequirementsExtractionV7

@_preserve_function('proposal_schemas', 'fashion_recommendation_v2.search.contracts')
def proposal_schemas(version, schema):
    """Return canonical runtime schema and model proposal schema; retain operation names."""
    from fashion_recommendation_v2.search.policy import search_policy
    if version in {'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'} and schema.__name__ in {'RequirementsStructureV37', 'RequirementsClassificationV37'}:
        return (schema, schema)
    if version in {'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
        from fashion_recommendation_v2.schemas.search.requirements.search_requirements import RequirementsStructureV31
        from fashion_recommendation_v2.schemas.search.requirements.search_requirements import RequirementsClassificationV31
        if issubclass(schema, (RequirementsStructureV31, RequirementsClassificationV31)):
            return (schema, schema)
    if version == 'v30':
        from fashion_recommendation_v2.schemas.search.requirements.search_requirements import RequirementsStructureV30_v30 as RequirementsStructureV30
        from fashion_recommendation_v2.schemas.search.requirements.search_requirements import RequirementsClassificationV30_v30 as RequirementsClassificationV30
        if issubclass(schema, (RequirementsStructureV30, RequirementsClassificationV30)):
            return (schema, schema)
    if version in {'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
        from fashion_recommendation_v2.schemas.search.requirements.search_requirements import RequirementsStructureV26
        from fashion_recommendation_v2.schemas.search.requirements.search_requirements import RequirementsClassificationV26
        if issubclass(schema, (RequirementsStructureV26, RequirementsClassificationV26)):
            return (schema, schema)
    if search_policy(version).enabled('canonical_proposal_filters'):
        from fashion_recommendation_v2.schemas.search.planning.search_planning import canonical_filter_schema_v21 as canonical_filter_schema
        schema = canonical_filter_schema(schema)
    if version in {"v24", 'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
        evidence_proposal_schema = search_schemas(version, purpose='planning').evidence_proposal_schema
        return (schema, evidence_proposal_schema(schema))
    # Requirement inventories are not marketplace proposals.
    return (schema, schema)

@_preserve_function('strategy_output_schema', 'fashion_recommendation_v2.search.contracts')
def strategy_output_schema(context, *, recovery):
    from fashion_recommendation_v2.search.policy import search_policy
    policy = search_policy(context.get('search_policy_version'))
    if policy.enabled('concise_query_contract'):
        if policy.version in SEARCH_RELEASES:
            build = search_schemas(policy.version, purpose='planning').strategy_schema_v16
        else:
            from fashion_recommendation_v2.schemas.search.planning.search_planning import strategy_schema_v16_v16 as build
    elif policy.enabled('code_revision_fields'):
        from fashion_recommendation_v2.schemas.search.planning.search_planning import strategy_schema_v13 as build
    elif policy.enabled('separate_plan_review'):
        from fashion_recommendation_v2.schemas.search.planning.search_planning import strategy_schema_v12_v12 as build
    else:
        from fashion_recommendation_v2.schemas.search.planning.search_planning import strategy_schema_v11 as build
    return proposal_schemas(policy.version, build(context, recovery=recovery))[1]

@_preserve_function('build_strategy_decision_prompt', 'fashion_recommendation_v2.search.contracts')
def build_strategy_decision_prompt(data, *, recovery):
    version = data.get('search_policy_version')
    if version in {'v16', 'v18', 'v19', 'v20', 'v21', 'v22', 'v23', "v24", 'v25', 'v26', 'v29', 'v30', 'v31', 'v32', 'v33', 'v34', 'v35', 'v36', 'v37', 'v40', 'v41', 'v42', 'v43', 'v44', 'v45', 'v46', 'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56', 'v57', 'v58', 'v59', 'v60', 'v61'}:
        return search_prompts(version).strategy_prompt(data, recovery=recovery)
    selected = version if version in {'v12', 'v13', 'v14', 'v15'} else 'v11'
    module = import_module(f'fashion_recommendation_v2.prompts.search.planning.search_planning_{selected}')
    return module.strategy_prompt(data, recovery=recovery)
