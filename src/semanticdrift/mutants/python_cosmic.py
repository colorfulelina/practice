"""Seed Python protocol mutants using Cosmic Ray operators (methodology §7.2.1).

Cosmic Ray is used as the mutation engine. Mutants are written out as files so
they can sit in the benchmark next to the original reference, then classified
by running the reference's ``run()`` in a subprocess.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from cosmic_ray.mutating import mutate_code
from cosmic_ray.plugins import get_operator

from semanticdrift.protocols import Protocol, list_protocols

# Operators that stay close to the paper's "plausible bug" idea on the C side:
# comparison swaps, boundary flips, boolean flips, and off-by-one-ish arithmetic.
OPERATORS: Tuple[str, ...] = (
    "core/ReplaceComparisonOperator_Eq_NotEq",
    "core/ReplaceComparisonOperator_NotEq_Eq",
    "core/ReplaceComparisonOperator_Lt_LtE",
    "core/ReplaceComparisonOperator_LtE_Lt",
    "core/ReplaceComparisonOperator_Gt_GtE",
    "core/ReplaceComparisonOperator_GtE_Gt",
    "core/ReplaceAndWithOr",
    "core/ReplaceOrWithAnd",
    "core/ReplaceTrueWithFalse",
    "core/ReplaceFalseWithTrue",
    "core/ReplaceBinaryOperator_Add_Sub",
    "core/ReplaceBinaryOperator_Sub_Add",
    "core/NumberReplacer",
)

# Default-argument / timeout edits are not protocol bugs.
SKIP_DIFF_NEEDLES = (
    "timeout=",
    "rounds:",
    "n_items:",
    "meals:",
    "n_participants:",
)

RUN_CALL = {
    "peterson": "mod.run(rounds=3)",
    "producer_consumer": "mod.run(n_items=4)",
    "dining_philosophers": "mod.run(meals=2)",
    "two_phase_commit": "mod.run()",
    "tcp_handshake": "mod.run()",
}

MAX_KILLED = 4
MAX_SURVIVED = 2
CLASSIFY_TIMEOUT_S = 8


def _operator_short_name(name: str) -> str:
    return name.split("/", 1)[-1].replace("Replace", "").replace("Operator_", "_")


def _is_noise_diff(original: str, mutated: str) -> bool:
    orig_lines = original.splitlines()
    mut_lines = mutated.splitlines()
    changed = [
        new
        for old, new in zip(orig_lines, mut_lines)
        if old != new
    ]
    if len(orig_lines) != len(mut_lines):
        return False
    if not changed:
        return True
    return all(any(needle in line for needle in SKIP_DIFF_NEEDLES) for line in changed)


def generate_candidates(source: str) -> List[Dict[str, Any]]:
    found: List[Dict[str, Any]] = []
    seen = set()
    for op_name in OPERATORS:
        operator = get_operator(op_name)()
        occurrence = 0
        while True:
            mutated = mutate_code(source, operator, occurrence)
            if mutated is None:
                break
            if mutated != source and mutated not in seen and not _is_noise_diff(source, mutated):
                seen.add(mutated)
                found.append(
                    {
                        "operator": op_name,
                        "occurrence": occurrence,
                        "source": mutated,
                    }
                )
            occurrence += 1
            if occurrence > 40:
                break
    return found


def classify_mutant(path: Path, protocol: str, timeout: int = CLASSIFY_TIMEOUT_S) -> str:
    call = RUN_CALL.get(protocol, "mod.run()")
    script = (
        "import importlib.util\n"
        f"spec = importlib.util.spec_from_file_location('mutant', {str(path)!r})\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(mod)\n"
        f"{call}\n"
    )
    try:
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "killed"
    if result.returncode == 0:
        return "survived"
    return "killed"


def _pick(classified: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    killed = [m for m in classified if m["test_outcome"] == "killed"]
    survived = [m for m in classified if m["test_outcome"] == "survived"]

    def rank(item: Dict[str, Any]) -> Tuple[int, str]:
        op = item["operator"]
        if "Comparison" in op or "And" in op or "Or" in op:
            return (0, op)
        if "True" in op or "False" in op:
            return (1, op)
        if "Add" in op or "Sub" in op:
            return (2, op)
        return (3, op)

    killed.sort(key=rank)
    survived.sort(key=rank)
    return killed[:MAX_KILLED] + survived[:MAX_SURVIVED]


def seed_protocol(proto: Protocol, timeout: int = CLASSIFY_TIMEOUT_S) -> Dict[str, Any]:
    original = proto.python_path.read_text(encoding="utf-8")
    out_dir = proto.python_path.parent / "mutants"
    if out_dir.exists():
        for old in out_dir.glob("cosmic_*.py"):
            old.unlink()
    out_dir.mkdir(parents=True, exist_ok=True)

    classified: List[Dict[str, Any]] = []
    for index, candidate in enumerate(generate_candidates(original)):
        temp = out_dir / f"_tmp_{index}.py"
        temp.write_text(candidate["source"], encoding="utf-8")
        outcome = classify_mutant(temp, proto.name, timeout=timeout)
        temp.unlink()
        classified.append({**candidate, "test_outcome": outcome})

    kept = _pick(classified)
    records = []
    for index, item in enumerate(kept):
        stem = f"cosmic_{index:02d}_{_operator_short_name(item['operator'])}_{item['occurrence']}"
        dest = out_dir / f"{stem}.py"
        dest.write_text(item["source"], encoding="utf-8")
        records.append(
            {
                "file": dest.name,
                "operator": item["operator"],
                "occurrence": item["occurrence"],
                "test_outcome": item["test_outcome"],
                "engine": "cosmic-ray",
            }
        )

    manifest = {
        "protocol": proto.name,
        "source": proto.python_path.name,
        "n_candidates": len(classified),
        "n_kept": len(records),
        "n_killed_candidates": sum(1 for m in classified if m["test_outcome"] == "killed"),
        "n_survived_candidates": sum(1 for m in classified if m["test_outcome"] == "survived"),
        "mutants": records,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def seed_python_protocols(
    protocols: Optional[Sequence[Protocol]] = None,
    timeout: int = CLASSIFY_TIMEOUT_S,
) -> List[Dict[str, Any]]:
    return [seed_protocol(proto, timeout=timeout) for proto in (protocols or list_protocols())]
