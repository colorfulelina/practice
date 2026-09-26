"""SVR / VSR / TAR / FAR / ATS (methodology §9 and §9.1).

FAR is only trace disagreement (or a human flag) on verifier-proved
tasks. Vacuous proofs are counted in vacuity_rate, not in FAR, so ATS
does not penalize the same property twice.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from semanticdrift.audit.classify import TRACE_THRESHOLD

TASK_KEYS = (
    "name",
    "requirement",
    "syntax_ok",
    "verifier_proved",
    "verifier_refuted",
    "trace_agreement",
    "vacuous",
    "human_flag",
    "category",
)


def task_row_from_audit(
    name: str,
    requirement: str,
    audit: Dict[str, Any],
    human_flag: Optional[bool] = None,
) -> Dict[str, Any]:
    spin = audit.get("spin") or {}
    traces = audit.get("traces") or {}
    vacuity = audit.get("vacuity") or {}
    claims = spin.get("claims") or []
    syntax_ok = bool(spin.get("syntax_ok"))
    proved = bool(spin.get("proved"))
    skipped = bool(spin.get("skipped_pan"))
    definite = bool(claims) and all(claim.get("errors") is not None for claim in claims)
    refuted = syntax_ok and not skipped and not proved and definite
    return {
        "name": name,
        "requirement": requirement,
        "syntax_ok": syntax_ok,
        "verifier_proved": proved,
        "verifier_refuted": refuted,
        "trace_agreement": traces.get("score"),
        "vacuous": bool(vacuity.get("vacuous")),
        "human_flag": human_flag,
        "category": audit.get("category"),
    }


def far_flag(row: Dict[str, Any]) -> bool:
    """True when a proved task is a false proof for reasons other than vacuity."""
    score = row.get("trace_agreement")
    if score is None or float(score) < TRACE_THRESHOLD:
        return True
    return bool(row.get("human_flag"))


def compute_metrics(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    tasks = list(rows)
    n = len(tasks)
    parsed = [row for row in tasks if row.get("syntax_ok")]
    proved = [row for row in tasks if row.get("verifier_proved")]
    svr = _mean(row.get("syntax_ok") for row in tasks) if tasks else 0.0
    vsr = (
        _mean(row.get("verifier_proved") or row.get("verifier_refuted") for row in parsed)
        if parsed
        else 0.0
    )
    tar = _mean(row.get("trace_agreement") for row in proved) if proved else None
    vacuity_rate = _mean(row.get("vacuous") for row in proved) if proved else 0.0
    far = _mean(far_flag(row) for row in proved) if proved else 0.0
    ats = vsr * (1.0 - far) * (1.0 - vacuity_rate)
    return {
        "n_tasks": n,
        "n_syntax_ok": len(parsed),
        "n_proved": len(proved),
        "SVR": svr,
        "VSR": vsr,
        "TAR": tar,
        "vacuity_rate": vacuity_rate,
        "FAR": far,
        "ATS": ats,
    }


def load_task_rows(directory: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    suite = directory / "suite.json"
    if suite.is_file():
        payload = json.loads(suite.read_text(encoding="utf-8"))
        if isinstance(payload.get("tasks"), list):
            return [row for row in payload["tasks"] if "syntax_ok" in row]
    for path in sorted(directory.glob("*.json")):
        if path.name == "suite.json":
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if "syntax_ok" in data:
            rows.append(data)
        elif "task" in data and isinstance(data["task"], dict):
            rows.append(data["task"])
    return rows


def write_metrics(rows: List[Dict[str, Any]], directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    payload = {"tasks": rows, "metrics": compute_metrics(rows)}
    path = directory / "suite.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _mean(values: Iterable[Any]) -> float:
    numbers = [float(value) for value in values if value is not None]
    if not numbers:
        return 0.0
    return sum(numbers) / len(numbers)
