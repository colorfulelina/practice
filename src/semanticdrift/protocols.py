"""Load Component C protocol folders (Python + precise/ambiguous requirements)."""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

import yaml

ROOT = Path(__file__).resolve().parents[2]
PROTOCOLS_DIR = ROOT / "benchmarks" / "protocols"


@dataclass
class Protocol:
    name: str
    property_class: str
    python_path: Path
    promela_path: Path
    requirement_precise: str
    requirement_ambiguous: str
    task_yaml: Path

    def load_module(self) -> Any:
        spec = importlib.util.spec_from_file_location(
            f"semanticdrift_ref_{self.name}", self.python_path
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load {self.python_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


def list_protocols(base: Optional[Path] = None) -> List[Protocol]:
    root = base or PROTOCOLS_DIR
    found: List[Protocol] = []
    if not root.is_dir():
        return found
    for task_yaml in sorted(root.glob("*/task.yaml")):
        spec = yaml.safe_load(task_yaml.read_text(encoding="utf-8")) or {}
        folder = task_yaml.parent
        python_rel = spec.get("source", {}).get("python", "reference.py")
        promela_rel = spec.get("source", {}).get("promela") or spec.get(
            "reference_models", {}
        ).get("promela", "reference.pml")
        reqs = spec.get("requirements", {})
        req_rel = reqs.get("precise", "requirement_precise.txt")
        amb_rel = reqs.get("ambiguous", "requirement_ambiguous.txt")
        amb_path = folder / amb_rel
        found.append(
            Protocol(
                name=spec.get("protocol", folder.name),
                property_class=spec.get("property_class", ""),
                python_path=folder / python_rel,
                promela_path=folder / promela_rel,
                requirement_precise=(folder / req_rel).read_text(encoding="utf-8"),
                requirement_ambiguous=amb_path.read_text(encoding="utf-8")
                if amb_path.is_file()
                else "",
                task_yaml=task_yaml,
            )
        )
    return found


def get_protocol(name: str, base: Optional[Path] = None) -> Protocol:
    match = [p for p in list_protocols(base) if p.name == name]
    if not match:
        known = ", ".join(p.name for p in list_protocols(base)) or "(none)"
        raise KeyError(f"Unknown protocol {name!r}. Known: {known}")
    return match[0]
