"""Week 1–2: SV-Benchmarks 300-task manifest (Section 7.1)."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "benchmarks" / "sv-sample" / "manifest.json"
SV_ROOT = ROOT / "sv-benchmarks"


def test_manifest_is_balanced_300_with_seed_7():
    assert MANIFEST.is_file(), "Run: python -m semanticdrift sample-sv"
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    tasks = data["tasks"]
    assert data["seed"] == 7
    assert data["n_true"] == 150
    assert data["n_false"] == 150
    assert len(tasks) == 300
    true_n = sum(1 for t in tasks if t["expected"] is True)
    false_n = sum(1 for t in tasks if t["expected"] is False)
    assert true_n == 150
    assert false_n == 150


def test_sampled_task_files_exist_in_the_clone():
    if not SV_ROOT.is_dir():
        return
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    missing = []
    for task in data["tasks"][:20]:
        yml = SV_ROOT / task["task_yaml"]
        if not yml.is_file():
            missing.append(task["task_yaml"])
    assert not missing, missing
