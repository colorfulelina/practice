"""What each audit category is allowed to touch."""

from __future__ import annotations

from typing import FrozenSet

# program_bug and exhausted tool_limitation never call an agent.
ALLOWED_TARGETS = {
    "no_failure": frozenset(),
    "modeling_error": frozenset({"model"}),
    "property_error": frozenset({"properties"}),
    "missing_invariant": frozenset({"properties"}),
    "program_bug": frozenset(),
    "tool_limitation": frozenset({"resource_bound"}),
}

FORBIDDEN = frozenset({"source_code", "requirement"})


def allowed_targets(category: str) -> FrozenSet[str]:
    return ALLOWED_TARGETS.get(category, frozenset())


def may_call_model(category: str) -> bool:
    return bool(allowed_targets(category) & {"model", "properties"})
