"""Current original-source fingerprints, captured separately before public comparison."""
import hashlib,json
from pathlib import Path
import pydantic
from fashion_recommendation_v2.module_compat import import_module

def test_current_source_contracts():
    fixture=json.loads((Path(__file__).parent/'fixtures/current_contract_fingerprints.json').read_text())
    assert pydantic.__version__==fixture['pydantic_version'], 'Install the pinned service dependencies for schema comparison'
    for key,expected in fixture['values'].items():
        parts=key.split(':');value=getattr(import_module(parts[0]),parts[1])
        if len(parts)==3:
            raw=json.dumps(value.model_json_schema(mode=parts[2]),sort_keys=True,ensure_ascii=False)
        else:raw=value
        assert hashlib.sha256(raw.encode()).hexdigest()==expected,key
