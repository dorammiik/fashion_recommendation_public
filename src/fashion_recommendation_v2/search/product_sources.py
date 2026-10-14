"""Product metadata source paths shared by observation generation and code checks."""

def evidence_fields(item, conversion):
    """Enumerate real, nonempty paths in the exact item representation sent to LLM."""
    paths = []
    def visit(value, prefix=''):
        for key, child in value.items():
            path = f'{prefix}.{key}' if prefix else key
            if child is None or child == [] or child == {} or child == '':
                continue
            paths.append(path)
            if isinstance(child, dict):
                visit(child, path)
    visit(item.model_dump(mode='json'))
    if conversion:
        paths.append('price_conversion')
    return paths

def present_field(item, path: str, conversion) -> bool:
    return path in evidence_fields(item, conversion)

