"""Shared default exclusion of identifiable childrenswear, before ranking."""
from fashion_recommendation_v2.module_compat import import_module as _role_module
import re

_CHILD_VALUES = {'child', 'children', 'kids', 'baby', 'infant', 'toddler', 'youth',
                 'boys', 'girls', 'boy', 'girl', 'newborn'}
_CHILD_TERMS = re.compile(r"\b(?:kids?|children(?:'s|s)?|boys?(?:'s)?|girls?(?:'s)?|babies|baby(?!\s+(?:blue|pink|doll)\b)|youth|toddlers?|infants?|newborns?)\b|아동|유아|유아동|어린이|키즈|주니어", re.I)


def children_requested(requirements):
    """Only positive, explicit user audience requirements authorize children."""
    if requirements is None:
        return False
    for req in requirements.requirements:
        if req.source != 'user' or req.kind != 'hard' or req.attribute not in {'age_group', 'gender', 'department'}:
            continue
        values = req.value if isinstance(req.value, list) else [req.value]
        if any(isinstance(v, str) and v.strip().casefold() in _CHILD_VALUES for v in values):
            return True
    return False


def is_childrenswear(item):
    # Size XS/XL and words like "baby blue", "boyfriend" or "babydoll" do
    # not establish age. Prefer explicit category/title/department evidence.
    texts = [item.title or '', item.category_path or '']
    detail = getattr(item, 'detail', None) or {}
    for key in ('department', 'age_group', 'gender'):
        value = detail.get(key, [])
        texts.extend(value if isinstance(value, list) else [str(value)])
    raw = getattr(item, 'raw_metadata', None) if getattr(item, 'record_version', None) == 'search_product_v26' else None
    for aspect in (getattr(item, 'localized_aspects', None) or getattr(raw, 'localized_aspects', None) or []):
        if aspect.name.casefold() in {'department', 'age group', 'age_group'}:
            texts.append(aspect.value)
    return any(_CHILD_TERMS.search(text) or text.strip().casefold() in _CHILD_VALUES for text in texts)


def excluded_childrenswear(item, requirements):
    return not children_requested(requirements) and is_childrenswear(item)
