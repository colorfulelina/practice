"""Run vacuity, traces, and the five-way classifier on one artifact."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from semanticdrift.agents.formalize import load_formalization
from semanticdrift.audit.classify import classify_failure, spin_for_classifier
from semanticdrift.audit.traces import (
    collect_reference_traces,
    model_events_from_promela,
    summarize_traces,
)
from semanticdrift.audit.vacuity_probe import audit_vacuity
from semanticdrift.protocols import ROOT, get_protocol
from semanticdrift.verifiers.spin import SpinVerifyResult, verify_text


@dataclass
class AuditResult:
    category: str
    spin: Dict[str, Any]
    vacuity: Dict[str, Any]
    traces: Dict[str, Any]
    trustworthy: bool
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "trustworthy": self.trustworthy,
            "spin": self.spin,
            "vacuity": self.vacuity,
            "traces": self.traces,
            "notes": self.notes,
        }


def audit_text(
    promela: str,
    reference_module: Any,
    extra_properties: Optional[List[tuple]] = None,
    timeout: int = 45,
) -> AuditResult:
    spin = verify_text(promela, timeout=timeout)
    notes: List[str] = []
    if spin.skipped_pan:
        vacuity: Dict[str, Any] = {
            "vacuous": False,
            "reason": "skipped: generated Promela did not parse",
            "mutants": {},
        }
        notes.append("vacuity probes skipped because spin -a failed")
    else:
        vacuity = audit_vacuity(promela, extra_properties=extra_properties, timeout=timeout)

    traces_raw = collect_reference_traces(reference_module)
    reference_events = traces_raw[0] if traces_raw else []
    model_events = model_events_from_promela(promela, reference_events)
    traces = summarize_traces(reference_events, model_events)
    traces["n_hypothesis_traces"] = len(traces_raw)

    spin_payload = spin.to_dict()
    spin_class = spin_for_classifier(
        spin.syntax_ok, spin.skipped_pan, spin.proved, spin.claims
    )
    category = classify_failure(
        spin_class,
        vacuity,
        traces["score"],
        traces["only_in_model"],
        traces["only_in_reference"],
    )
    trustworthy = category == "no_failure"
    return AuditResult(
        category=category,
        spin=spin_payload,
        vacuity=vacuity,
        traces=traces,
        trustworthy=trustworthy,
        notes=notes,
    )


def audit_protocol(
    name: str,
    requirement: str = "precise",
    from_json: Optional[Path] = None,
    from_pml: Optional[Path] = None,
    timeout: int = 45,
) -> AuditResult:
    protocol = get_protocol(name)
    extra = None
    if from_pml is not None:
        promela = from_pml.read_text(encoding="utf-8")
    else:
        path = from_json or (ROOT / "results" / "formalize" / f"{name}_{requirement}.json")
        if not path.is_file():
            raise FileNotFoundError(
                f"No formalization at {path}. Run: python -m semanticdrift formalize "
                f"--name {name} --requirement {requirement}"
            )
        artifact = load_formalization(path)
        promela = artifact.as_promela()
        extra = [(p.name, p.formula) for p in artifact.properties]
    module = protocol.load_module()
    return audit_text(promela, module, extra_properties=extra, timeout=timeout)
