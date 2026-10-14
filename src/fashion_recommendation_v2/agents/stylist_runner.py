"""Check extraction against orchestrator-provided interpretations, without agent calls."""
from fashion_recommendation_v2.module_compat import import_module as _role_module
import json

from fashion_recommendation_v2.schemas.search.requirements.search_requirements import RequirementsExtraction
from fashion_recommendation_v2.schemas.search.requirements.search_requirements import SearchAgentInput_legacy as SearchAgentInput
from fashion_recommendation_v2.schemas.stylist import StylistDetailValue_base as StylistDetailValue


class StylistInterpretationMismatch(ValueError):
    """A Search extraction violated the supplied Stylist interpretation contract."""

    def __init__(self, reason: str, differences: list[dict]):
        self.differences = differences
        def display(value):
            return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        details = '; '.join(
            f"{d['field']}: 기대 {display(d['expected'])} → 실제 {display(d['actual'])}"
            for d in differences
        )
        super().__init__(f'{reason} {details}'.strip())


def interpretation_differences(expected, actual):
    """Compare one expected interpretation to a candidate requirement for diagnostics only."""
    attribute, value, source_text = expected
    fields = dict(attribute=attribute, value=value, source='stylist', kind='soft', source_text=source_text)
    label = f'detail.{value.key}' if isinstance(value, StylistDetailValue) else attribute
    def encode(value):
        return value.model_dump(mode='json') if isinstance(value, StylistDetailValue) else value
    return [dict(field=f'{label}.{name}', expected=encode(wanted), actual=encode(getattr(actual, name)))
            for name, wanted in fields.items() if wanted != getattr(actual, name)]


def validate_stylist_requirements(source: SearchAgentInput, extracted: RequirementsExtraction, *, semantic_key=None) -> None:
    routing = getattr(extracted, 'condition_routing_v37', None)
    if (routing is not None and routing.stylist_policy_v47 is not None) or getattr(source, 'requirements_source_version', None) in {'v47', 'v48', 'v49', 'v50', 'v51', 'v52', 'v53', 'v54', 'v55', 'v56'}:
        from fashion_recommendation_v2.search.stylist_policy import validate_resolved_stylist
        validate_resolved_stylist(source, extracted)
        return
    expected = []
    for entry in source.stylist_resolution.interpretations if source.stylist_resolution else []:
        candidate = (entry.attribute, entry.value, entry.source_text)
        if candidate not in expected:
            expected.append(candidate)
    users = [entry for entry in extracted.requirements if entry.source == 'user']
    stylist = [entry for entry in extracted.requirements if entry.source == 'stylist']
    for entry in stylist:
        if entry.kind != 'soft' or (entry.attribute, entry.value, entry.source_text) not in expected:
            # Select the closest interpretation for explanation, never to repair the response.
            closest = max(expected, key=lambda e: sum((e[0] == entry.attribute, e[1] == entry.value,
                                                       e[2] == entry.source_text)), default=None)
            differences = interpretation_differences(closest, entry) if closest else [
                dict(field=f'{entry.attribute}.count', expected=0, actual=1)]
            raise StylistInterpretationMismatch(
                'Stylist requirements must preserve original attribute, value, source_text and soft kind.', differences)
    for attribute, value, source_text in expected:
        # Explicit same-attribute constraints take priority over interpretations.
        def same_attribute(entry):
            if semantic_key is not None:
                return semantic_key(entry.attribute, entry.value) == semantic_key(attribute, value)
            if entry.attribute != attribute:
                return False
            if isinstance(value, StylistDetailValue):
                return isinstance(entry.value, StylistDetailValue) and entry.value.key == value.key
            return True

        hard_user = any(same_attribute(entry) and entry.kind == 'hard' for entry in users)
        matches = [entry for entry in stylist if
                   (entry.attribute, entry.value, entry.source_text) == (attribute, value, source_text)]
        if hard_user:
            if matches:
                raise StylistInterpretationMismatch(
                    'Explicit hard user conditions take priority over same-attribute interpretations.',
                    [dict(field=f'{attribute}.stylist_count', expected=0, actual=len(matches))])
            continue
        if len(matches) != 1:
            alternatives = [entry for entry in extracted.requirements if same_attribute(entry)]
            differences = [dict(field=f'{attribute}.exact_stylist_count', expected=1, actual=len(matches))]
            if alternatives and not matches:
                closest = max(alternatives, key=lambda e: sum((e.value == value, e.source_text == source_text,
                                                               e.source == 'stylist')))
                differences = interpretation_differences((attribute, value, source_text), closest) + differences
            raise StylistInterpretationMismatch(
                'Each Stylist interpretation must be preserved exactly once, including OR alternatives.', differences)
        if any(same_attribute(entry) and entry.source_text == source_text for entry in users):
            raise StylistInterpretationMismatch(
                'Do not duplicate an interpreted condition as both user and stylist.',
                [dict(field=f'{attribute}.duplicate_user_count', expected=0,
                      actual=sum(same_attribute(e) and e.source_text == source_text for e in users))])
