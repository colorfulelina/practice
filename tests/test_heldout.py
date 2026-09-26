"""Component D: post-cutoff GitHub tasks with pinned commits."""

import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "benchmarks" / "heldout" / "manifest.json"
CUTOFF = datetime.fromisoformat("2025-06-01")


def test_heldout_manifest_has_about_40_pinned_tasks():
    assert MANIFEST.is_file(), "run the held-out GitHub collector"
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    tasks = data["tasks"]
    assert data["cutoff"] == "2025-06-01"
    assert 35 <= len(tasks) <= 45
    repos = {t["repo"] for t in tasks}
    assert len(repos) >= 15
    for task in tasks:
        assert task["commit"] and len(task["commit"]) == 40
        assert task["path"]
        assert task.get("license") in {None, "MIT"}
        created = datetime.fromisoformat(task["created_at"].replace("Z", "+00:00")).replace(tzinfo=None)
        assert created >= CUTOFF, task["repo"]
