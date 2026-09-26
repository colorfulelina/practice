"""Stratified Software Verification Benchmarks sample (methodology section 7.1)."""

from __future__ import annotations

import glob
import json
import os
import random
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml

SV_CLONE_URL = "https://gitlab.com/sosy-lab/benchmarking/sv-benchmarks.git"
DEFAULT_CATEGORIES = (
    "c/reducercommutativity",
    "c/pthread",
    "c/loops",
    "c/array-examples",
)
SEED = 7
N_TRUE = 150
N_FALSE = 150


def clone_sv_benchmarks(dest: Path) -> None:
    if (dest / ".git").is_dir() or (dest / "c").is_dir():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", "--depth", "1", SV_CLONE_URL, str(dest)],
        check=True,
    )


def _under_category(yml_path: str, repo_root: Path, categories: Iterable[str]) -> bool:
    rel = os.path.relpath(yml_path, repo_root).replace("\\", "/")
    return any(rel.startswith(cat.rstrip("/") + "/") or f"/{cat.strip('/')}/" in f"/{rel}" for cat in categories)


def collect_tasks(
    repo_root: Path,
    categories: Iterable[str] = DEFAULT_CATEGORIES,
) -> List[Dict[str, Any]]:
    """Parse every .yml task file and keep ReachSafety/Concurrency-style categories."""
    tasks: List[Dict[str, Any]] = []
    pattern = str(repo_root / "c" / "**" / "*.yml")
    for path in glob.glob(pattern, recursive=True):
        if not _under_category(path, repo_root, categories):
            continue
        with open(path, encoding="utf-8") as handle:
            spec = yaml.safe_load(handle)
        if not spec or "properties" not in spec:
            continue
        for prop in spec["properties"]:
            tasks.append(
                {
                    "task_yaml": os.path.relpath(path, repo_root),
                    "source_file": spec.get("input_files"),
                    "property_file": prop.get("property_file"),
                    "expected": prop.get("expected_verdict"),
                }
            )
    return tasks


def stratified_sample(
    tasks: List[Dict[str, Any]],
    n_true: int = N_TRUE,
    n_false: int = N_FALSE,
    seed: int = SEED,
) -> List[Dict[str, Any]]:
    true_tasks = [t for t in tasks if t["expected"] is True]
    false_tasks = [t for t in tasks if t["expected"] is False]
    if len(true_tasks) < n_true or len(false_tasks) < n_false:
        raise ValueError(
            f"Not enough labeled tasks: true={len(true_tasks)} false={len(false_tasks)}; "
            f"need {n_true}/{n_false}. Widen categories or lower the sample size."
        )
    rng = random.Random(seed)
    sample = rng.sample(true_tasks, n_true) + rng.sample(false_tasks, n_false)
    rng.shuffle(sample)
    return sample


def write_manifest(sample: List[Dict[str, Any]], out_path: Path, meta: Optional[Dict[str, Any]] = None) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "seed": SEED,
        "n_true": N_TRUE,
        "n_false": N_FALSE,
        "categories": list(DEFAULT_CATEGORIES),
        "tasks": sample,
    }
    if meta:
        payload.update(meta)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def build_sample(
    repo_root: Path,
    manifest_path: Path,
    clone: bool = True,
) -> Dict[str, Any]:
    if clone:
        clone_sv_benchmarks(repo_root)
    tasks = collect_tasks(repo_root)
    sample = stratified_sample(tasks)
    write_manifest(
        sample,
        manifest_path,
        meta={"n_parsed": len(tasks), "repo": str(repo_root)},
    )
    return {
        "n_parsed": len(tasks),
        "n_sampled": len(sample),
        "manifest": str(manifest_path),
    }
