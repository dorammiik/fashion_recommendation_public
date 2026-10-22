"""Role-consolidated service implementation, refreshed from the v61/v13 release."""

from __future__ import annotations

from fashion_recommendation_v2.module_compat import import_module as _role_module, preserve_class as _preserve_class, preserve_function as _preserve_function


# ---- observations ----

"""Stored product observation paths shared by extraction and persistence validation."""
from fashion_recommendation_v2.schemas.preference_agent import Observation

@_preserve_function('observations', 'fashion_recommendation_v2.preference.observations')
def observations(snapshot):
    entries = []
    item = snapshot.item.model_dump(mode='json')
    analysis = snapshot.search_analysis
    if analysis is not None:
        from fashion_recommendation_v2.search.evidence_projection import semantic_entries
        item = {'title': snapshot.item.title, 'category_path': snapshot.item.category_path}
        for path, fact in semantic_entries(analysis):
            # Preserve the attribute/detail name in the observed atom and its
            # reference into the saved analysis, without rewriting that analysis.
            key = fact.attribute + ('.' + fact.value.key if hasattr(fact.value, 'key') else '')
            values = fact.value.values if hasattr(fact.value, 'key') else fact.value if isinstance(fact.value, list) else [fact.value]
            item[path + '.value'] = [key + ': ' + value for value in values]
            for index, evidence in enumerate(fact.image_evidence):
                item[path + f'.image_evidence.{index}.observation'] = evidence.observation
    # Identity/link/price fields are not semantic preference evidence.
    for field in item if analysis is not None else ['title', 'category_path', 'color', 'size', 'fit', 'material', 'pattern', 'brand', 'strength', 'garment_care', 'theme', 'season', 'occasion', 'detail']:
        value = item.get(field)
        if not value:
            continue
        parts = [(field, value)]
        if isinstance(value, dict):
            parts = [(field + '.' + k, v) for k, v in value.items()]
        for name, values in parts:
            for text in values if isinstance(values, list) else [values]:
                text = str(text)
                while text:
                    end = min(1200, len(text))
                    if end < len(text):
                        boundary = text.rfind(' ', 0, end)
                        if boundary > 600:
                            end = boundary + 1
                    entries.append((name, text[:end]))
                    text = text[end:]
    for i, image in enumerate(snapshot.image_observations if analysis is None else []):
        text = image.observation
        # Bound individual atoms without losing characters; split at word boundaries when possible.
        while text:
            end = min(1200, len(text))
            if end < len(text):
                boundary = text.rfind(' ', 0, end)
                if boundary > 600:
                    end = boundary + 1
            entries.append((f'image:{i}', text[:end]))
            text = text[end:]
    # Split text retains the source index; evidence expands back to the exact original observation.
    unique = list(dict.fromkeys(entries))
    return [Observation(observation_id=f'o{i}', field=f, text=t) for i, (f, t) in enumerate(unique)]
