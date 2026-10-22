"""Offline current-source baselines; generated from the original tree independently."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from current_prompt_capture import dynamic_prompts

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"


def test_current_dynamic_prompts():
    expected = json.loads((FIXTURES / "current_dynamic_fingerprints.json").read_text())
    actual = {k: hashlib.sha256(v.encode()).hexdigest() for k, v in dynamic_prompts().items()}
    assert len(expected) == 29
    assert actual == expected


def test_current_synthetic_behavior(tmp_path):
    output = tmp_path / "actual.json"
    result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("current_behavior_capture.py")), str(ROOT), str(output)],
        cwd=tmp_path, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    expected = json.loads(gzip.decompress((FIXTURES / "current_behavior_expected.json.gz").read_bytes()))
    actual = json.loads(output.read_text())
    assert len(expected) == 15
    assert actual == expected
    assert actual["ranking/warm/none/available"]["calls"] > 0
    assert actual["ranking/warm/none/failed"]["calls"] > 0
    assert actual["ranking/warm/similarity/available"]["calls"] == 0
    assert set(actual["relation/success"]["calls"].values()) == {1}
    assert set(actual["relation/repair"]["calls"].values()) == {2}
    assert set(actual["relation/fail"]["calls"].values()) == {2}
