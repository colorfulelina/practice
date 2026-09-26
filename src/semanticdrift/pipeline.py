"""Formalize → validate → verify → audit → repair, then score the final artifact."""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from semanticdrift.agents.formalize import (
    ChatFn,
    Formalization,
    _properties,
    formalize_protocol,
    write_formalization,
)
from semanticdrift.agents.validate import validate_protocol
from semanticdrift.audit.run import audit_protocol, audit_text
from semanticdrift.metrics import compute_metrics, task_row_from_audit, write_metrics
from semanticdrift.protocols import ROOT, get_protocol, list_protocols
from semanticdrift.repair.loop import REPAIR_CAP, repair_protocol
from semanticdrift.verifiers.spin import verify_protocol

PIPELINE_OUT = ROOT / "results" / "pipeline"


@dataclass
class PipelineRun:
    name: str
    requirement: str
    task: Dict[str, Any]
    stages: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    wall_time_s: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "requirement": self.requirement,
            "wall_time_s": self.wall_time_s,
            "error": self.error,
            "task": self.task,
            "stages": self.stages,
        }


def run_pipeline(
    name: str,
    requirement: str = "precise",
    chat_fn: Optional[ChatFn] = None,
    validator_chat_fn: Optional[ChatFn] = None,
    cap: int = REPAIR_CAP,
    timeout: int = 180,
    out_dir: Path = PIPELINE_OUT,
) -> PipelineRun:
    started = time.time()
    stages: Dict[str, Any] = {}
    try:
        artifact = formalize_protocol(
            name,
            requirement=requirement,
            chat_fn=chat_fn,
            timeout=timeout,
        )
        paths = write_formalization(
            artifact,
            ROOT / "results" / "formalize",
            f"{name}_{requirement}",
        )
        stages["formalize"] = artifact.to_dict()

        validation = validate_protocol(
            name,
            requirement=requirement,
            from_json=paths["json"],
            chat_fn=validator_chat_fn or chat_fn,
            timeout=timeout,
        )
        stages["validate"] = validation.to_dict()

        verify = verify_protocol(
            name,
            requirement=requirement,
            from_json=paths["json"],
            timeout=min(timeout, 120),
        )
        stages["verify"] = verify.to_dict()

        audit = audit_protocol(
            name,
            requirement=requirement,
            from_json=paths["json"],
        )
        stages["audit"] = audit.to_dict()

        repair = repair_protocol(
            name,
            requirement=requirement,
            from_json=paths["json"],
            cap=cap,
            chat_fn=chat_fn,
        )
        stages["repair"] = repair.to_dict()

        protocol = get_protocol(name)
        final = artifact
        if repair.artifact and repair.artifact.get("model"):
            final = Formalization(
                model=str(repair.artifact["model"]),
                properties=_properties(repair.artifact.get("properties")),
                assumptions=list(repair.artifact.get("assumptions") or []),
                traceability=list(repair.artifact.get("traceability") or []),
                generator_model=str(
                    repair.artifact.get("generator_model") or artifact.generator_model
                ),
            )
        extra = [(prop.name, prop.formula) for prop in final.properties]
        final_audit = audit_text(
            final.as_promela(),
            protocol.load_module(),
            extra_properties=extra,
        )
        stages["final_audit"] = final_audit.to_dict()
        task = task_row_from_audit(name, requirement, final_audit.to_dict())
        error = None
    except Exception as exc:  # noqa: BLE001 — one failed task must not abort the suite
        task = {
            "name": name,
            "requirement": requirement,
            "syntax_ok": False,
            "verifier_proved": False,
            "verifier_refuted": False,
            "trace_agreement": None,
            "vacuous": False,
            "human_flag": None,
            "category": None,
        }
        error = str(exc)[:400]
    wall = time.time() - started
    task["wall_time_s"] = wall
    run = PipelineRun(
        name=name,
        requirement=requirement,
        task=task,
        stages=stages,
        error=error,
        wall_time_s=wall,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}_{requirement}.json"
    path.write_text(json.dumps(run.to_dict(), indent=2) + "\n", encoding="utf-8")
    return run


def run_suite(
    names: Optional[List[str]] = None,
    requirements: Optional[List[str]] = None,
    chat_fn: Optional[ChatFn] = None,
    validator_chat_fn: Optional[ChatFn] = None,
    cap: int = REPAIR_CAP,
    timeout: int = 180,
    out_dir: Path = PIPELINE_OUT,
) -> Dict[str, Any]:
    protocols = names or [proto.name for proto in list_protocols()]
    variants = requirements or ["precise", "ambiguous"]
    runs: List[PipelineRun] = []
    for name in protocols:
        for requirement in variants:
            print(f"pipeline {name} {requirement}", file=sys.stderr, flush=True)
            runs.append(
                run_pipeline(
                    name,
                    requirement,
                    chat_fn=chat_fn,
                    validator_chat_fn=validator_chat_fn,
                    cap=cap,
                    timeout=timeout,
                    out_dir=out_dir,
                )
            )
    rows = [run.task for run in runs]
    write_metrics(rows, out_dir)
    return {
        "n": len(runs),
        "metrics": compute_metrics(rows),
        "tasks": rows,
        "errors": [run.error for run in runs if run.error],
    }
