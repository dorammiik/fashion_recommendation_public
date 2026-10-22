"""Compare consolidated code with immutable pre-refactor contracts and outputs."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pydantic
import pytest

from fashion_recommendation_v2.module_compat import MODULES, import_module

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"


def test_schema_contracts_match_before_consolidation():
    versions = json.loads((FIXTURES / "role_schema_fingerprints.json").read_text())
    if pydantic.__version__ not in versions:
        pytest.skip(f"Schema snapshot requires Pydantic {list(versions)}; installed {pydantic.__version__}")
    fingerprints = versions[pydantic.__version__]
    assert len(fingerprints) == 1878
    for key, expected in fingerprints.items():
        module, name, mode = key.split(":")
        schema = getattr(import_module(module), name).model_json_schema(mode=mode)
        actual = hashlib.sha256(json.dumps(schema, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        assert actual == expected, key


def test_role_modules_import_independently():
    # Importing modules one by one in fresh processes detects circular imports
    # that an already-initialized pytest process can conceal.
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    modules = sorted({value[0] for value in MODULES.values()})
    assert len(modules) >= 41  # Existing role coverage plus current release roles.
    for module in modules:
        result = subprocess.run(
            [sys.executable, "-c", f"import importlib; importlib.import_module({module!r})"],
            cwd=ROOT, env=env, capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, f"{module}\n{result.stderr}"


def test_synthetic_service_outputs_match_before_consolidation(tmp_path):
    # Separate process fixes UUID generation before imports and blocks sockets.
    output = tmp_path / "actual.json"
    result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("role_behavior_capture.py")), str(ROOT), str(output)],
        cwd=tmp_path, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    expected = json.loads(gzip.decompress((FIXTURES / "role_behavior_expected.json.gz").read_bytes()))
    actual = json.loads(output.read_text())
    assert len(expected) == 15
    assert actual == expected
    assert actual["ranking/warm/none/available"]["calls"] > 0
    assert actual["ranking/warm/none/failed"]["calls"] > 0
    assert actual["ranking/warm/similarity/available"]["calls"] == 0
    assert set(actual["relation/success"]["calls"].values()) == {1}
    assert set(actual["relation/repair"]["calls"].values()) == {2}
    assert set(actual["relation/fail"]["calls"].values()) == {2}
