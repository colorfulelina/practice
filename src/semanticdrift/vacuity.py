"""Adversarial vacuity mutants (methodology §4.1 / §8.6.1).

The same four LTL text mutations apply to SPIN formulas (`[]`, `<>`, `->`)
and SV-COMP `LTL(...)`.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

SPIN_LTL = re.compile(r"ltl\s+(\w+)\s*\{([^}]+)\}", re.S)


def _inner_ltl(prp_text: str) -> List[str]:
    found: List[str] = []
    key = "LTL("
    start = 0
    while True:
        i = prp_text.find(key, start)
        if i < 0:
            break
        j = i + len(key)
        depth = 1
        k = j
        while k < len(prp_text) and depth:
            if prp_text[k] == "(":
                depth += 1
            elif prp_text[k] == ")":
                depth -= 1
            k += 1
        found.append(prp_text[j : k - 1].strip())
        start = k
    return found


def extract_promela_ltl(source: str) -> List[Tuple[str, str]]:
    return [(name, " ".join(body.split())) for name, body in SPIN_LTL.findall(source)]


def extract_svcomp_ltl(prp_text: str) -> List[str]:
    return [" ".join(item.split()) for item in _inner_ltl(prp_text)]


_ANTECEDENT = re.compile(r"((?:\([^()]*\))|(?:\b[\w.\[\]]+))\s*->")
_CONSEQUENT = re.compile(
    r"->\s*((?:!?\([^()]*\))|(?:<>\s+[\w.\[\]]+)|(?:F\s+[\w.\[\]]+)|(?:[\w.\[\]]+))"
)


def _replace_first_eventually(formula: str) -> str | None:
    match = re.search(r"(<>|F)\s+([\w.\[\]]+)", formula)
    if not match:
        return None
    return formula[: match.start()] + f"{match.group(1)} true" + formula[match.end() :]


def _guard_false(formula: str) -> str | None:
    """Turn a simple safety 'never A and B' / 'G ! atom' into an unfalsifiable claim."""
    if "||" in formula:
        return None
    simple = re.search(r"\[\]\s*!\s*\([^()]*&&[^()]*\)\s*$", formula)
    if simple:
        return "[] ! (false && true)"
    g_not_call = re.search(r"G\s*!\s*call\(.+\)", formula)
    if g_not_call:
        return formula[: g_not_call.start()] + "G ! false"
    g_not_atom = re.search(r"G\s*!\s*[A-Za-z][\w\-]*", formula)
    if g_not_atom:
        return formula[: g_not_atom.start()] + "G ! false" + formula[g_not_atom.end() :]
    return None


def generate_vacuity_mutants(ltl_formula: str) -> Dict[str, str]:
    formula = " ".join(ltl_formula.split())
    mutants: Dict[str, str] = {}

    ant = _ANTECEDENT.search(formula)
    if ant:
        forced = formula[: ant.start()] + "true ->" + formula[ant.end() :]
        if forced != formula:
            mutants["antecedent_forced"] = forced

    cons = _CONSEQUENT.search(formula)
    if cons:
        trivial = formula[: cons.start()] + "-> true" + formula[cons.end() :]
        if trivial != formula:
            mutants["consequent_trivial"] = trivial

    eventually = _replace_first_eventually(formula)
    if eventually and eventually != formula:
        mutants["eventually_to_true"] = eventually

    guard = _guard_false(formula)
    if guard and guard != formula:
        mutants["guard_false"] = guard

    return mutants
