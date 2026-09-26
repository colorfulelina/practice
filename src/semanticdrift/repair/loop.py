"""Repair loop: audit, route, cap 5, then escalate (methodology §8.7)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from semanticdrift.agents.formalize import ChatFn, Formalization, load_formalization, write_formalization
from semanticdrift.agents.formalize import _requirement_text
from semanticdrift.audit.run import AuditResult, audit_text
from semanticdrift.protocols import ROOT, get_protocol
from semanticdrift.repair.policy import allowed_targets
from semanticdrift.repair.steps import apply_repair

REPAIR_CAP = 5


@dataclass
class RepairRun:
    stopped: str
    iterations: int
    history: List[Dict[str, Any]] = field(default_factory=list)
    artifact: Optional[Dict[str, Any]] = None
    source_path_untouched: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stopped": self.stopped,
            "iterations": self.iterations,
            "source_path_untouched": self.source_path_untouched,
            "history": self.history,
            "artifact": self.artifact,
        }


def repair_protocol(
    name: str,
    requirement: str = "precise",
    from_json: Optional[Path] = None,
    cap: int = REPAIR_CAP,
    chat_fn: Optional[ChatFn] = None,
    timeout_s: int = 45,
) -> RepairRun:
    protocol = get_protocol(name)
    path = from_json or (ROOT / "results" / "formalize" / f"{name}_{requirement}.json")
    if not path.is_file():
        raise FileNotFoundError(
            f"No formalization at {path}. Run: python -m semanticdrift formalize "
            f"--name {name} --requirement {requirement}"
        )
    artifact = load_formalization(path)
    source = protocol.python_path.read_text(encoding="utf-8")
    requirement_text = _requirement_text(protocol, requirement)
    module = protocol.load_module()
    history: List[Dict[str, Any]] = []
    timeout = timeout_s
    last_audit: Optional[AuditResult] = None

    for step in range(1, cap + 1):
        extra = [(p.name, p.formula) for p in artifact.properties]
        audit = audit_text(
            artifact.as_promela(),
            module,
            extra_properties=extra,
            timeout=timeout,
        )
        last_audit = audit
        record: Dict[str, Any] = {
            "step": step,
            "category": audit.category,
            "trustworthy": audit.trustworthy,
            "allowed": sorted(allowed_targets(audit.category)),
        }
        if audit.category == "no_failure":
            record["action"] = "stop"
            history.append(record)
            _write(artifact, name, requirement)
            return RepairRun(
                stopped="no_failure",
                iterations=step,
                history=history,
                artifact=artifact.to_dict(),
            )
        if audit.category == "program_bug":
            record["action"] = "escalate"
            record["note"] = "agent must not patch the code under test"
            history.append(record)
            return RepairRun(
                stopped="escalated_program_bug",
                iterations=step,
                history=history,
                artifact=artifact.to_dict(),
            )
        if audit.category == "tool_limitation" and timeout >= 180:
            record["action"] = "escalate"
            record["note"] = "timeout ceiling reached"
            history.append(record)
            return RepairRun(
                stopped="escalated_tool_limitation",
                iterations=step,
                history=history,
                artifact=artifact.to_dict(),
            )
        try:
            artifact, timeout, note = apply_repair(
                audit.category,
                artifact,
                source,
                requirement_text,
                audit,
                timeout_s=timeout,
                chat_fn=chat_fn,
            )
            record["action"] = "repair"
            record["note"] = note
        except ValueError as exc:
            record["action"] = "rejected"
            record["note"] = str(exc)
            history.append(record)
            return RepairRun(
                stopped="rejected_weakening",
                iterations=step,
                history=history,
                artifact=artifact.to_dict(),
            )
        history.append(record)

    _write(artifact, name, requirement)
    stopped = "cap_reached"
    if last_audit and last_audit.category == "tool_limitation":
        stopped = "escalated_tool_limitation"
    return RepairRun(
        stopped=stopped,
        iterations=cap,
        history=history,
        artifact=artifact.to_dict(),
    )


def _write(artifact: Formalization, name: str, requirement: str) -> None:
    write_formalization(
        artifact,
        ROOT / "results" / "repair",
        f"{name}_{requirement}",
    )
