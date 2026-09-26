"""Build the Component E vacuity battery from protocols and the SV sample."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from semanticdrift.protocols import ROOT, list_protocols
from semanticdrift.vacuity import (
    extract_promela_ltl,
    extract_svcomp_ltl,
    generate_vacuity_mutants,
)

OUT_DIR = ROOT / "benchmarks" / "vacuity"
CONSTRUCTED = (
    (
        "constructed_false_implies_mutex",
        "[] (false -> !(inCS0 && inCS1))",
        "classic vacuous implication: antecedent never holds",
    ),
    (
        "constructed_overflow_implies_mutex",
        "[] (crit_overflow -> !(inCS0 && inCS1))",
        "implication whose guard is never set in gold Peterson",
    ),
    (
        "constructed_always_true",
        "[] true",
        "tautology",
    ),
    (
        "constructed_eventually_true",
        "<> true",
        "liveness that cannot fail on an infinite run",
    ),
    (
        "constructed_false_implies_overflow",
        "[] (false -> (count <= N))",
        "vacuous buffer-safety implication",
    ),
    (
        "constructed_full_implies_can_produce",
        "[] ((count == N) -> (count < N))",
        "self-contradicting guard; still a real (unsatisfiable) claim if forced",
    ),
    (
        "constructed_abort_implies_all_commit",
        "[] ((decision == d_abort) -> (outcome[0] == d_commit))",
        "meaningful but likely false on gold 2PC",
    ),
    (
        "constructed_listen_implies_accept",
        "[] ((sstate == LISTEN) -> server_accepted)",
        "meaningful and false on gold TCP",
    ),
    (
        "constructed_want_implies_eat",
        "[] (hungry0 -> <> eating[0])",
        "dining-philosophers liveness",
    ),
    (
        "constructed_neighbor_pair",
        "[] !(eating[0] && eating[1])",
        "single-pair neighbor mutex",
    ),
)


def _add(
    rows: List[Dict[str, Any]],
    *,
    source: str,
    property_id: str,
    kind: str,
    formula: str,
    original: str,
    note: str = "",
) -> None:
    rows.append(
        {
            "id": f"{property_id}__{kind}",
            "source": source,
            "property_id": property_id,
            "kind": kind,
            "formula": formula,
            "original": original,
            "note": note,
        }
    )


def build_battery() -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []

    for proto in list_protocols():
        text = proto.promela_path.read_text(encoding="utf-8")
        for name, formula in extract_promela_ltl(text):
            pid = f"{proto.name}.{name}"
            _add(
                rows,
                source="component_c",
                property_id=pid,
                kind="original",
                formula=formula,
                original=formula,
                note="gold Promela LTL",
            )
            for kind, mutant in generate_vacuity_mutants(formula).items():
                _add(
                    rows,
                    source="component_c",
                    property_id=pid,
                    kind=kind,
                    formula=mutant,
                    original=formula,
                )

    sv_root = ROOT / "sv-benchmarks"
    manifest = ROOT / "benchmarks" / "sv-sample" / "manifest.json"
    seen_prp = set()
    if manifest.is_file() and sv_root.is_dir():
        tasks = json.loads(manifest.read_text(encoding="utf-8"))["tasks"]
        for task in tasks:
            rel = task.get("property_file")
            if not rel:
                continue
            # property_file is relative to the task yaml directory
            yml = sv_root / task["task_yaml"]
            prp = (yml.parent / rel).resolve()
            if not prp.is_file():
                continue
            key = str(prp.relative_to(sv_root))
            if key in seen_prp:
                continue
            seen_prp.add(key)
            for index, formula in enumerate(extract_svcomp_ltl(prp.read_text(encoding="utf-8"))):
                pid = f"sv:{key}:{index}"
                _add(
                    rows,
                    source="component_a",
                    property_id=pid,
                    kind="original",
                    formula=formula,
                    original=formula,
                    note="SV-COMP property used in the 300-task sample",
                )
                for kind, mutant in generate_vacuity_mutants(formula).items():
                    _add(
                        rows,
                        source="component_a",
                        property_id=pid,
                        kind=kind,
                        formula=mutant,
                        original=formula,
                    )

    for pid, formula, note in CONSTRUCTED:
        _add(
            rows,
            source="component_e_constructed",
            property_id=pid,
            kind="original",
            formula=formula,
            original=formula,
            note=note,
        )
        for kind, mutant in generate_vacuity_mutants(formula).items():
            _add(
                rows,
                source="component_e_constructed",
                property_id=pid,
                kind=kind,
                formula=mutant,
                original=formula,
            )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"n": len(rows), "properties": rows}
    path = OUT_DIR / "battery.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload
