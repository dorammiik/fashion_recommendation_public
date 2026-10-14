"""Search detail-key provenance shared by input preparation and publication checks."""


def detail_keys(evidence):
    keys = set()
    for entry in evidence:
        obs = entry.observation
        if not entry.source_path.startswith('search_analysis.attributes.') or obs.get('attribute') != 'detail':
            continue
        for source in ('metadata', 'image_observation'):
            value = (obs.get(source) or {}).get('value')
            if isinstance(value, dict) and isinstance(value.get('key'), str) and value['key'].strip():
                keys.add(value['key'])
    return sorted(keys)


def validate_detail_keys(interpretations, evidence):
    allowed = set(detail_keys(evidence))
    for interpretation in interpretations:
        if not set(interpretation.detail_keys) <= allowed:
            raise ValueError('Unknown Search detail key: ' + ', '.join(sorted(set(interpretation.detail_keys) - allowed)))
