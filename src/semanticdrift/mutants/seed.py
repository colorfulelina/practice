"""Build Component B mutant sets for Python protocols and the SV C sample."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from semanticdrift.mutants.c_mutator import seed_c_tasks, write_spot_check
from semanticdrift.mutants.python_cosmic import seed_python_protocols
from semanticdrift.protocols import ROOT
from semanticdrift.sv_sample import build_sample


def seed_all(
    repo_root: Optional[Path] = None,
    sv_manifest: Optional[Path] = None,
    c_out: Optional[Path] = None,
    python: bool = True,
    c_sources: bool = True,
) -> Dict[str, Any]:
    report: Dict[str, Any] = {}
    if python:
        report["python"] = seed_python_protocols()
    if c_sources:
        root = repo_root or (ROOT / "sv-benchmarks")
        manifest_path = sv_manifest or (ROOT / "benchmarks" / "sv-sample" / "manifest.json")
        if not manifest_path.is_file():
            build_sample(repo_root=root, manifest_path=manifest_path, clone=True)
        tasks = json.loads(manifest_path.read_text(encoding="utf-8"))["tasks"]
        out_dir = c_out or (ROOT / "benchmarks" / "sv-sample" / "mutants")
        c_manifest = seed_c_tasks(root, tasks, out_dir)
        spot = write_spot_check(c_manifest, out_dir / "spot_check.json", n=30)
        report["c"] = {
            "n_mutants": c_manifest["n_mutants"],
            "n_skipped": c_manifest["n_skipped"],
            "n_spot_check": spot["n_reviewed"],
            "manifest": str(out_dir / "manifest.json"),
            "spot_check": str(out_dir / "spot_check.json"),
        }
    return report
