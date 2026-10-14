"""Read-only quick-start presets; no profile generation or live product lookup."""
from fashion_recommendation_v2.module_compat import import_module as _role_module
import hashlib
import json
from pathlib import Path

from fashion_recommendation_v2.preference.profile_lookup import FileProfileLookup
from fashion_recommendation_v2.schemas.quick_start import QuickStartSnapshot
from fashion_recommendation_v2.schemas.relation import ReferenceItem
from fashion_recommendation_v2.schemas.search.retrieval.search_retrieval import RetrievedProductV26
from fashion_recommendation_v2.schemas.search.product_evaluation.search_product_evaluation import SearchItemAnalysisV36_v36 as SearchItemAnalysisV36
from fashion_recommendation_v2.schemas.search.requirements.search_requirements import ResolvedRequirements_legacy as ResolvedRequirements
from fashion_recommendation_v2.search.product_validation import validate_analysis

ROOT = Path(__file__).resolve().parents[3]
PROFILE_ROOT = Path('eval_results/preference/v4_new_profile_20261009_r1/profiles')
ANCHOR_ID = 'v1|398447142632|0'
PRESETS = {
    'complex': ('페스티벌에 입고 가기 좋은 꽃무늬 드레스 추천해줘. 투피스로 된 것도 괜찮은데 바지는 별로야. 잔꽃무늬였으면 좋겠고, 스커트 길이는 길었으면 좋겠어', 'cold'),
    'similar': ('이전 추천 1번과 비슷한 원피스 찾아줘', 'cold'),
    'profile_a': ('주말에 편하게 입을 티셔츠 찾아줘', 'warm'),
    'profile_b': ('주말에 편하게 입을 티셔츠 찾아줘', 'warm'),
}


class QuickStartUnavailable(ValueError):
    pass


def resolve(quick_start, query, mode, previous_request_id, new_request):
    if quick_start is None:
        return query, mode, previous_request_id, new_request
    if quick_start not in PRESETS or previous_request_id:
        raise ValueError('Quick start must begin a new conversation')
    query, mode = PRESETS[quick_start]
    return query, mode, None, True


def snapshot(quick_start, root=None):
    root = root or ROOT
    try:
        if quick_start in ('profile_a', 'profile_b'):
            path = PROFILE_ROOT / ('A' if quick_start == 'profile_a' else 'B')
            bundle = FileProfileLookup(root/path)()
            if bundle['profile']['interpretation_version'] != 'preference-interpretation-v4':
                raise ValueError('Expected Preference v4')
            return QuickStartSnapshot(profile_bundle=bundle, source=str(path))
        if quick_start == 'similar':
            path = Path('evals/relation/case_plan_v3.json')
            plan = json.loads((root/path).read_text())
            case = next(c for c in plan['cases'] if c['case_id'] == 'RS001')
            if case['anchor_item_id'] != ANCHOR_ID or case['anchor_rank'] != 1:
                raise ValueError('Unexpected quick-start anchor')
            provenance = case['anchor_observation_provenance']
            for name, expected in provenance['file_sha256'].items():
                if hashlib.sha256((root/name).read_bytes()).hexdigest() != expected:
                    raise ValueError('Frozen anchor changed')
            item = RetrievedProductV26.model_validate_json((root/case['anchor_evaluation_item_path']).read_bytes())
            analysis = SearchItemAnalysisV36.model_validate_json((root/case['anchor_search_analysis_path']).read_bytes())
            requirements = ResolvedRequirements.model_validate_json((root/case['anchor_requirements_path']).read_bytes())
            validate_analysis(analysis, item, requirements, None)
            if item.item_id != ANCHOR_ID or item.raw_metadata.model_dump(mode='json') != case['anchor_item']['raw_metadata']:
                raise ValueError('Anchor identity mismatch')
            reference = ReferenceItem(request_id=provenance['run_id'], rank=1, item=item, search_analysis=analysis)
            return QuickStartSnapshot(reference_items=[reference], source=str(path))
        return QuickStartSnapshot()
    except (OSError, ValueError, KeyError, TypeError, StopIteration) as exc:
        raise QuickStartUnavailable('quick_start_data_unavailable') from exc
