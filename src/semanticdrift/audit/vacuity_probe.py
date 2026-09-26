"""Run the four LTL mutations through unmodified SPIN (methodology §4.1 / §8.6.1)."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from semanticdrift.vacuity import extract_promela_ltl, generate_vacuity_mutants
from semanticdrift.verifiers.spin import verify_text

_LTL_BLOCK = re.compile(r"(ltl\s+)(\w+)(\s*\{)([^}]*)(\})", re.S)

# Mutations that are tautologies by construction. A prove here is not a signal.
_ALWAYS_TRUE = {"consequent_trivial", "eventually_to_true", "guard_false"}


def replace_ltl(promela: str, name: str, formula: str) -> str:
    def _swap(match: re.Match[str]) -> str:
        if match.group(2) != name:
            return match.group(0)
        return f"{match.group(1)}{name}{match.group(3)} {formula} {match.group(5)}"

    patched, n = _LTL_BLOCK.subn(_swap, promela, count=0)
    if n:
        return patched
    return promela.rstrip() + f"\nltl {name} {{ {formula} }}\n"


def claim_proved(promela: str, name: str, timeout: int = 45) -> Tuple[Optional[bool], str]:
    result = verify_text(promela, timeout=timeout)
    if result.skipped_pan:
        return None, result.syntax_detail
    for claim in result.claims:
        if claim.name == name:
            return claim.proved, claim.detail
    return False, "named claim not in pan output"


def audit_vacuity(
    promela: str,
    extra_properties: Optional[List[Tuple[str, str]]] = None,
    timeout: int = 45,
) -> Dict[str, object]:
    """Flag the original property if a non-tautology probe still proves."""
    claims = list(extract_promela_ltl(promela))
    if extra_properties:
        have = {name for name, _formula in claims}
        for name, formula in extra_properties:
            if name not in have:
                claims.append((name, formula))
                promela = replace_ltl(promela, name, formula)

    mutant_results: Dict[str, Dict[str, object]] = {}
    vacuous = False
    if not claims:
        return {"vacuous": False, "reason": "no ltl claims", "mutants": mutant_results}

    for name, formula in claims:
        probes = generate_vacuity_mutants(formula)
        row: Dict[str, object] = {"original": formula, "probes": {}}
        forced_proved = False
        for kind, mutant in probes.items():
            patched = replace_ltl(promela, name, mutant)
            proved, detail = claim_proved(patched, name, timeout=timeout)
            row["probes"][kind] = {
                "formula": mutant,
                "proved": proved,
                "detail": detail,
            }
            if kind == "antecedent_forced" and proved is True:
                forced_proved = True
                vacuous = True
            if kind not in _ALWAYS_TRUE and proved is True and kind != "antecedent_forced":
                vacuous = True
        if forced_proved:
            row["vacuous"] = True
        else:
            row["vacuous"] = False
        mutant_results[name] = row

    return {"vacuous": vacuous, "mutants": mutant_results}
