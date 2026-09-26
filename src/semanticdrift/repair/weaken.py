"""Reject property edits that weaken the claim (methodology §8.7)."""

from __future__ import annotations

from typing import Iterable, Sequence, Tuple

from semanticdrift.agents.formalize import LTLProperty

_TAUTOLOGY = (
    "true",
    "[] true",
    "<> true",
    "[] (true)",
    "<> (true)",
)


def is_property_weakened(
    before: Sequence[LTLProperty],
    after: Sequence[LTLProperty],
) -> bool:
    old = {p.name: " ".join(p.formula.split()) for p in before}
    new = {p.name: " ".join(p.formula.split()) for p in after}
    if set(old) - set(new):
        return True
    for name, old_f in old.items():
        if _weaker(old_f, new.get(name, "")):
            return True
    return False


def weakening_reasons(
    before: Sequence[LTLProperty],
    after: Sequence[LTLProperty],
) -> Tuple[bool, str]:
    if is_property_weakened(before, after):
        return True, "property edit dropped a claim or replaced it with a weaker formula"
    return False, ""


def _weaker(old: str, new: str) -> bool:
    if not new:
        return True
    lowered = new.lower()
    if lowered in _TAUTOLOGY or "-> true" in lowered:
        return True
    if "<>" in old and "<>" not in new:
        return True
    if old.count("&&") > new.count("&&"):
        return True
    if old.count("!") > new.count("!"):
        return True
    return False
