"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- condition_semantics ----

"""v26 observation meanings shared by extraction, image instructions and code checks.

Unknown dimensions retain the existing conditional semantic-review path. Aliases
resolve a definition without changing a frozen requirement's attribute/value/text.
"""
# Historical marketplaces/mapper used broad keys. Interpret registered VALUES
# without declaring every possible feature/accent visual or rewriting the source.
from types import MappingProxyType
from copy import deepcopy
import hashlib
import json
from fashion_recommendation_v2.schemas.product_evidence import ConditionDefinitionV26
_VISUAL = {'product_type': ('Garment type and construction', ['outline', 'garment components']), 'avoid_product_type': ('Observable garment type, independently of whether it is disliked', ['outline', 'garment components']), 'color': ('Visible color, separate from lighting and metadata conflicts', ['visible surface']), 'pattern': ('Visible pattern or graphic', ['surface pattern', 'legibility']), 'fit': ('Visible fit/silhouette, not inferred body measurements', ['outline', 'waist', 'drape']), 'sleeve_length': ('Sleeve extent', ['shoulder', 'sleeve end']), 'detail.length': ('Actual garment length; a fold edge is not the true hem', ['garment start', 'true hem']), 'detail.dress_length': ('Dress length; inspect the real dress hem and full vertical extent', ['upper dress', 'true hem', 'lower body']), 'detail.skirt_length': ('Skirt length from waist to actual hem', ['waistline', 'true hem', 'lower body']), 'detail.neckline': ('Shape of the garment neckline', ['neck opening']), 'detail.closure': ('Closure construction and placement', ['fastener', 'front opening']), 'detail.hem': ('Actual hem construction or shape', ['true hem']), 'detail.pockets': ('Pocket construction and placement', ['pocket opening', 'requested detail']), 'detail.silhouette': ('Actual garment outline', ['upper body', 'lower body', 'outline']), 'detail.waistband': ('Waistband construction', ['waistline', 'requested detail']), 'detail.fit': ('Garment fit/silhouette', ['outline', 'drape']), 'detail.sleeve_length': ('Sleeve extent', ['shoulder', 'sleeve end']), 'detail.sleeve_style': ('Sleeve construction and shape', ['sleeves']), 'detail.strap': ('Strap construction', ['shoulder', 'requested detail']), 'detail.slit': ('Visible slit construction', ['true hem', 'requested detail']), 'detail.pleats': ('Visible folds constructed as pleats, not accidental wrinkles', ['surface', 'outline']), 'detail.waistline': ('Garment waistline position and construction', ['waistline', 'upper body']), 'detail.embellishment': ('Visible garment embellishment', ['requested detail']), 'detail.shoulder_exposure': ('Shoulder openings/coverage of the garment, not a wearer identity or exposure-safety verdict', ['shoulder', 'neck opening']), 'detail.cutout': ('Visible openings constructed in the garment', ['requested detail', 'opening edges'])}
_NONVISUAL = ('price', 'brand', 'size', 'material', 'season', 'occasion', 'theme', 'gender', 'strength', 'garment_care', 'detail.size', 'detail.size_type', 'detail.material', 'detail.fabric_composition', 'detail.care', 'detail.country_of_origin', 'detail.brand', 'detail.season', 'detail.occasion', 'detail.theme')
DEFINITIONS = MappingProxyType({**{key: dict(visually_applicable=True, meaning=value[0], observation_cues=value[1]) for key, value in _VISUAL.items()}, **{key: dict(visually_applicable=False, meaning='Metadata/context property; not a visual-confirmability gate', observation_cues=[]) for key in _NONVISUAL}})
ALIASES = MappingProxyType({'detail.garment_length': 'detail.length', 'detail.front_closure': 'detail.closure', 'detail.pocket': 'detail.pockets', 'detail.garment_care': 'detail.care', 'detail.sleeve_type': 'detail.sleeve_style', 'detail.straps': 'detail.strap', 'detail.slits': 'detail.slit'})
METADATA_ONLY_FACTS = frozenset({'brand', 'size', 'material', 'garment_care', 'season', 'strength', 'gender', 'detail.size', 'detail.size_type', 'detail.material', 'detail.fabric_composition', 'detail.care', 'detail.garment_care', 'detail.brand', 'detail.country_of_origin'})
DETAIL_VALUE_ALIASES = MappingProxyType({'double front slit': 'detail.slit', 'front slit': 'detail.slit', 'side slit': 'detail.slit', 'back slit': 'detail.slit', 'slit': 'detail.slit', 'slits': 'detail.slit', 'partial shoulder exposure': 'detail.shoulder_exposure', 'cold shoulder': 'detail.shoulder_exposure', 'off shoulder': 'detail.shoulder_exposure', 'shoulder cutout': 'detail.shoulder_exposure', 'cutout': 'detail.cutout', 'cutouts': 'detail.cutout', 'pockets': 'detail.pockets', 'pleats': 'detail.pleats', 'pleated': 'detail.pleats'})
GENERIC_DETAIL_KEYS = frozenset({'detail.features', 'detail.accents'})
# Intake-only identities. Effective v30 conditions use the existing observation
# definitions; historical catalogs and frozen condition hashes stay unchanged.
ATTRIBUTE_ALIASES_V30 = MappingProxyType({'category': 'product_type', 'garment_type': 'product_type', 'neckline_detail': 'neckline'})

@_preserve_function('provenance_dimension_v30', 'fashion_recommendation_v2.search.condition_semantics')
def provenance_dimension_v30(attribute, value):
    """Match source facts using registered meanings, never a title/fuzzy match."""
    key = value.key if attribute == 'detail' and hasattr(value, 'key') else attribute
    key = ATTRIBUTE_ALIASES_V30.get(key, key)
    visual_key = ALIASES.get('detail.' + key, 'detail.' + key)
    if visual_key in GENERIC_DETAIL_KEYS:
        values = value.values if hasattr(value, 'values') else value if isinstance(value, list) else [value]
        targets = {DETAIL_VALUE_ALIASES.get(' '.join(v.casefold().replace('-', ' ').split())) for v in values}
        if len(targets) == 1 and None not in targets:
            visual_key = targets.pop()
    return visual_key.removeprefix('detail.')

@_preserve_function('catalog', 'fashion_recommendation_v2.search.condition_semantics')
def catalog():
    return dict(definitions=deepcopy(dict(DEFINITIONS)), aliases=dict(ALIASES), metadata_only_product_facts=sorted(METADATA_ONLY_FACTS), generic_detail_value_aliases=dict(keys=sorted(GENERIC_DETAIL_KEYS), values=dict(DETAIL_VALUE_ALIASES)), unknown='Preserve unsupported detail keys; explicitly route applicability to semantic review, never guess.', visibility='Can the property be inspected? A clearly visible mismatch still has met visibility.')

@_preserve_function('requirement_hash', 'fashion_recommendation_v2.search.condition_semantics')
def requirement_hash(requirement):
    return hashlib.sha256(json.dumps(requirement.model_dump(mode='json'), sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()

@_preserve_function('definition', 'fashion_recommendation_v2.search.condition_semantics')
def definition(requirement):
    key = requirement.attribute
    if key == 'detail' and hasattr(requirement.value, 'key'):
        key += '.' + requirement.value.key.casefold().replace('-', '_').replace(' ', '_')
    key = ALIASES.get(key, key)
    rule = DEFINITIONS.get(key, dict(visually_applicable=None, meaning='Unregistered detail; preserve original meaning', observation_cues=[]))
    if key in GENERIC_DETAIL_KEYS and hasattr(requirement.value, 'values'):
        targets = [DETAIL_VALUE_ALIASES.get(' '.join(v.casefold().replace('-', ' ').split())) for v in requirement.value.values]
        if targets and all(targets):
            targets = list(dict.fromkeys(targets))
            rules = [DEFINITIONS[target] for target in targets]
            rule = dict(visually_applicable=True, meaning='; '.join((r['meaning'] for r in rules)), observation_cues=list(dict.fromkeys((cue for r in rules for cue in r['observation_cues']))))
            if len(targets) == 1:
                key = targets[0]
    if requirement.unrestricted:
        rule = dict(rule, visually_applicable=False)
    return ConditionDefinitionV26(key=key, requirement_sha256=requirement_hash(requirement), **rule)

@_preserve_function('bind_condition_contract', 'fashion_recommendation_v2.search.condition_semantics')
def bind_condition_contract(requirements):
    return {r.requirement_id: definition(r) for r in requirements.requirements}

@_preserve_function('validate_condition_contract', 'fashion_recommendation_v2.search.condition_semantics')
def validate_condition_contract(requirements):
    stored = requirements.condition_contract_v26
    if stored is None or stored != bind_condition_contract(requirements):
        raise ValueError('v26 condition definitions must cover the exact frozen requirements and code registry.')
    return stored

@_preserve_function('applicability', 'fashion_recommendation_v2.search.condition_semantics')
def applicability(requirement, contract):
    bound = contract.get(requirement.requirement_id)
    if bound is None or bound.requirement_sha256 != requirement_hash(requirement):
        raise ValueError('Condition observation binding does not match the frozen requirement.')
    return bound.visually_applicable

@_preserve_function('observation_key', 'fashion_recommendation_v2.search.condition_semantics')
def observation_key(row):
    attribute = row['attribute']
    value = row.get('value')
    name = 'detail.' + value['key'].casefold().replace('-', '_').replace(' ', '_') if attribute == 'detail' and isinstance(value, dict) else 'category' if attribute == 'product_type' else attribute
    return ALIASES.get(name, name)
