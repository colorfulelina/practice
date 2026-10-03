"""Collect pipeline and baseline JSON into results/paper_runs.json."""

from __future__ import annotations

import json
from pathlib import Path

from semanticdrift.agents.formalize import parse_formalization
from semanticdrift.promela import check_syntax_text
from semanticdrift.protocols import ROOT

PIPELINE = ROOT / "results" / "pipeline"
BASELINES = ROOT / "results" / "baselines"
OUT = ROOT / "results" / "paper_runs.json"

PROTOCOLS = (
    "peterson",
    "producer_consumer",
    "dining_philosophers",
    "two_phase_commit",
    "tcp_handshake",
)


def _spin_from_pml(path: Path) -> tuple[bool | None, bool | None]:
    if not path.is_file():
        return None, None
    ok, _ = check_syntax_text(path.read_text(encoding="utf-8"))
    return ok, None


def _pipeline_rows() -> list[dict]:
    rows = []
    suite = PIPELINE / "suite.json"
    if suite.is_file():
        tasks = json.loads(suite.read_text(encoding="utf-8")).get("tasks") or []
        for task in tasks:
            rows.append(
                {
                    "condition": "pipeline_zero_shot",
                    "protocol": task.get("name"),
                    "requirement": task.get("requirement"),
                    "syntax_ok": task.get("syntax_ok"),
                    "proved": task.get("verifier_proved"),
                    "n_calls": None,
                    "category": task.get("category"),
                    "source": str(suite.relative_to(ROOT)),
                }
            )
        return rows
    for path in sorted(PIPELINE.glob("*_*.json")):
        if path.name == "suite.json":
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        task = data.get("task") or {}
        rows.append(
            {
                "condition": "pipeline_zero_shot",
                "protocol": data.get("name") or task.get("name"),
                "requirement": data.get("requirement") or task.get("requirement"),
                "syntax_ok": task.get("syntax_ok"),
                "proved": task.get("verifier_proved"),
                "n_calls": None,
                "category": task.get("category"),
                "source": str(path.relative_to(ROOT)),
            }
        )
    return rows


def _baseline_rows() -> list[dict]:
    rows = []
    for path in sorted(BASELINES.glob("*.json")):
        if "before_keep" in path.name:
            stem = path.name.replace(".json", "")
            cond = "few_shot_verifier_feedback_before_keep"
            proto = "tcp_handshake"
            req = "precise"
        else:
            data = json.loads(path.read_text(encoding="utf-8"))
            cond = data.get("baseline")
            proto = data.get("name")
            req = data.get("requirement")
            n_calls = data.get("n_calls")
            verified = data.get("verified")
            pml = path.with_suffix(".pml")
            syntax = None
            if pml.is_file():
                syntax, _ = _spin_from_pml(pml)
            elif data.get("artifact"):
                try:
                    art = parse_formalization(json.dumps(data["artifact"]))
                    syntax, _ = check_syntax_text(art.as_promela())
                except Exception:
                    syntax = None
            hist = data.get("history") or []
            any_parse = any(h.get("syntax_ok") for h in hist) if hist else syntax
            rows.append(
                {
                    "condition": cond,
                    "protocol": proto,
                    "requirement": req,
                    "syntax_ok": syntax,
                    "proved": verified,
                    "n_calls": n_calls,
                    "any_attempt_parsed": any_parse,
                    "source": str(path.relative_to(ROOT)),
                }
            )
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        pml = path.with_suffix(".pml")
        syntax, _ = _spin_from_pml(pml)
        rows.append(
            {
                "condition": cond,
                "protocol": proto,
                "requirement": req,
                "syntax_ok": syntax,
                "proved": data.get("verified"),
                "n_calls": data.get("n_calls"),
                "any_attempt_parsed": any(h.get("syntax_ok") for h in data.get("history") or []),
                "source": str(path.relative_to(ROOT)),
            }
        )
    return rows


def main() -> None:
    rows = _pipeline_rows() + _baseline_rows()
    payload = {"n_rows": len(rows), "rows": rows}
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
