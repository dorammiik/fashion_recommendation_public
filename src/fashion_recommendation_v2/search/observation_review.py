"""Shared conditional review routing and immutable evidence hashes."""
from fashion_recommendation_v2.module_compat import import_module as _role_module
import hashlib
import json
import re
from fashion_recommendation_v2.schemas.visual_confirmation import visual_applicability


def visual_review_questions(observation, requirements):
    """Route concrete unresolved meaning to the LLM, never infer grades from prose.

    These are suspicion signals, not natural-language truth checks. Code already
    validates enums, applicability for known attributes, and cross-field rules.
    Normal uncertainty/low grades and presentation wrinkles do not trigger review.
    """
    thumb, visual = observation.ranking_thumbnail_observation_v5, observation.visual_confirmation_v5
    questions = []
    evidence = (thumb.evidence + '\n' + visual.overall_form_evidence).casefold()
    # Do not flag an explicit "not a mannequin" description as mannequin evidence.
    evidence = re.sub(r'\b(?:no|not|without)\s+(?:a\s+)?(?:mannequin|dress form)\b', '', evidence)
    evidence = re.sub(r'마네킹(?:이|은)?\s*(?:아닌|아니|아님)', '', evidence)
    if thumb.photo_type == 'person' and re.search(r'\bmannequin\b|\bdress form\b|마네킹', evidence):
        questions.append('photo_type/display_subject: Evidence mentions a mannequin but classification says person. '
                         'Check whether the description actually denotes a mannequin; mannequins are product_only.')
    if thumb.photo_type != 'person' and re.search(
            r'\bworn by (?:a |the )?(?:real )?(?:person|woman|man|human|model)\b|\breal person wearing\b|사람이 착용|사람이 입고', evidence):
        questions.append('photo_type/display_subject: Evidence describes a human wearing the garment but classification is not person. '
                         'Check the actual referent in the description.')
    # Ignore ordinary wrinkles/draping: they affect Q independently of visibility.
    cleaned = re.sub(r'\bnot (?:hidden|obscured|cropped|cut off)\b', 'visible', evidence)
    regions = r'\bhem\b|\blower (?:body|half|portion|panel)\b|\bsilhouette\b|\boverall (?:form|shape|outline)\b|밑단|하단|전체 형태|전체 실루엣'
    hidden = r'\bhidden\b|\bnot visible\b|\bcropped (?:off|out)\b|\bcut off\b|\bobscured\b|\bcannot (?:be )?(?:seen|assess|confirm)|가려|보이지|확인.{0,15}(?:어렵|불가|없)'
    has_hidden_evidence = any(re.search(regions, sentence) and re.search(hidden, sentence)
                              for sentence in re.split(r'[.!?;\n]+', cleaned))
    folded_bundle = re.search(r'\bfolded (?:garment|shirt|bundle)\b|접힌 (?:상품|옷|셔츠)', cleaned)
    if (has_hidden_evidence or folded_bundle) and (thumb.product_focus == 'full' or visual.overall_form_status == 'met'):
        questions.append('product_focus/overall_form_status: Evidence may describe a concealed true hem/major garment portion '
                         'or folded bundle while full extent/met form is claimed. Distinguish photo cropping from a cropped style; '
                         'a fold edge is not the true hem. Do not infer reduced visibility merely from wrinkles or low thum_quality.')
    for check in visual.requirement_checks:
        if check.status == 'met' and re.search(r'\bnot visible\b|\bcannot (?:be )?(?:seen|assess|confirm)|확인.{0,15}(?:불가|없)', check.evidence.casefold()):
            questions.append(f'requirement_checks[{check.requirement_id}].status: Evidence may deny assessability despite met. '
                             'Check visibility only; a clearly visible mismatch with the request remains met.')
    for requirement in requirements.requirements:
        if visual_applicability(requirement, getattr(requirements, 'condition_contract_v26', None)) is None:
            questions.append(f'requirement_checks[{requirement.requirement_id}].applicable: Code cannot classify this detail. '
                             'Check whether it is a visually inspectable property, not whether the requested value is satisfied.')
    return questions


def observation_hash(item, requirements, observation):
    data = {'item': item.model_dump(mode='json'), 'requirements': requirements.model_dump(mode='json'),
            'observation': observation.model_dump(mode='json') if hasattr(observation, 'model_dump') else observation}
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


