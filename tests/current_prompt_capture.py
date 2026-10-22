"""Synthetic offline prompt captures, shared by before/after and regression checks."""
from datetime import date
try:
    from fashion_recommendation_v2.module_compat import import_module
except ImportError:
    from importlib import import_module


def resolve(name):
    try:
        from fashion_recommendation_v2.prompts._compat import resolve_prompt_module
    except ImportError:
        return import_module(name)
    return resolve_prompt_module(name)


def dynamic_prompts():
    from fashion_recommendation_v2.search.contracts import get_search_contracts
    SearchAgentInput = resolve('fashion_recommendation_v2.schemas.search.requirements.search_requirements_legacy').SearchAgentInput
    ResolvedRequirements = resolve('fashion_recommendation_v2.schemas.search.requirements.search_requirements_legacy').ResolvedRequirements
    SearchAgentInputV49 = resolve('fashion_recommendation_v2.schemas.search.requirements.search_requirements_v58').SearchAgentInputV58
    from fashion_recommendation_v2.schemas.relation_intent import RelationIntent
    RequirementsStructureV37 = resolve('fashion_recommendation_v2.schemas.search.requirements.search_requirements_v37').RequirementsStructureV37
    out = {}
    contract = get_search_contracts('v61')
    source = SearchAgentInputV49(request_id='public-prompt-check', user_query='검정 또는 흰색 셔츠 추천해줘',
        goal='셔츠 추천', original_user_query='검정 또는 흰색 셔츠 추천해줘', current_date=date(2026, 10, 14), requested_count=5)
    requirements = ResolvedRequirements(requirements_id='public-requirements', requirements=[
        dict(requirement_id='type', attribute='product_type', value='shirt', kind='hard', source='user', source_text='셔츠'),
        dict(requirement_id='color', attribute='color', value=['black', 'white'], kind='soft', source='user', source_text='검정 또는 흰색'),
    ])
    planning = contract.planning.prompts
    for empty in (False, True):
        req = requirements if not empty else ResolvedRequirements(requirements_id='empty', requirements=[])
        for name, kwargs in [('initial', {}), ('single', {'requested_query_count':1}),
            ('repair', {'failed_plan':{'query':'shirt'}, 'generation_error':'synthetic error',
                        'validation_error':'missing color', 'valid_plans':[{'query':'black shirt'}]})]:
            out[f'planning/{empty}/{name}'] = planning.initial_plan_prompt(req, source=source, **kwargs)
    for recovery in (False, True):
        for context in [{}, {'search_policy_version':'v61', 'unused_requirements_after_current':['color'],
                'validation_feedback':[{'field':'query','rejected_value':'셔츠','required_changes':'English keywords'}],
                'user_text':'한글 "quoted" \\ newline\n', 'budget':0}]:
            key=f'planning/strategy/{recovery}/{len(context)}'
            out[key] = planning.strategy_prompt(context, recovery=recovery)
    for relation in (None, 'similarity', 'compatibility'):
        current=source.model_copy(deep=True)
        if relation:
            current.relation_intent=RelationIntent(relation_type=relation, source_text='기준 상품', anchor_item_id='public-anchor')
        for stage in ('structure','classification'):
            out[f'requirements/{relation}/{stage}']=contract.requirements.prompts.requirements_prompt(
                current, RequirementsStructureV37, stage=stage,
                conditions=None if stage=='structure' else [r.model_copy(update={'role':'target'}) for r in requirements.requirements])
    product=contract.product_evaluation.prompts
    out['product/common']=product.build_visual_batch_prompt({})
    out['product/review']=product.build_review_prompt()
    for idx, context in enumerate([{}, {'items':[], 'search_policy_version':'v61'},
            {'items':[{'item_id':'public-item','title':'셔츠 "quoted" \\ \n'}], 'correction_issues':['check evidence']} ]):
        out[f'product/visual/{idx}']=product.build_visual_batch_prompt(context)
    shared = resolve('fashion_recommendation_v2.prompts.search.planning.search_planning_base')
    common = dict(user_query=source.user_query, goal=source.goal)
    plan = dict(query='black shirt', category_ids=['public-category'], aspect_filters={'Color':['Black']})
    out['lookup/query'] = shared.build_query_planning_prompt(**common, requested_count=5,
        stylist_resolution=None, preference_profile=None, resolved_requirements=requirements.model_dump(mode='json'))
    out['lookup/usage'] = shared.build_requirement_usage_prompt(requirements=requirements.model_dump(mode='json'),
        final_plan=plan, observed_categories=[], locations={'query':'black shirt', 'filter':'"Color": ["Black"]', 'category':'public-category'})
    out['lookup/category'] = shared.build_category_selection_prompt(**common, query_plan=plan,
        categories=[{'category_id':'public-category','category_name':'Shirts'}])
    for retry in (False, True):
        out[f'lookup/filter/{retry}'] = shared.build_filter_option_selection_prompt(**common, query_plan=plan,
            filter_name='Color', requested_values=['Black'], available_options=['Black','White'], can_retry=retry)
    out['lookup/results'] = shared.build_result_inspection_prompt(**common, query_plan=plan,
        inspected_items=[], candidate_count=0, target_candidate_count=15, completed_search_attempts=1, minimum_search_attempts=1)
    out['lookup/inspection'] = shared.build_inspection_decision_prompt(context={'query_plan':plan,'candidate_count':0})
    out['lookup/revision'] = shared.build_strategy_revision_prompt(**common, current_query_plan=plan,
        inspection={'status':'empty'}, inspected_items=[], previous_attempts=[],
        resolved_requirements=requirements.model_dump(mode='json'), unused_requirement_ids=['color'])
    return out
