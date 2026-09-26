"""Five-way failure attribution (methodology §8.6.3)."""

from __future__ import annotations

from typing import Any, Dict, Optional

FAILURE_CATEGORIES = (
    "no_failure",
    "property_error",
    "modeling_error",
    "program_bug",
    "tool_limitation",
    "missing_invariant",
)

TRACE_THRESHOLD = 0.9


def classify_failure(
    spin_result: Dict[str, Any],
    vacuity_result: Dict[str, Any],
    trace_score: float,
    trace_only_in_model: bool,
    trace_only_in_reference: bool,
) -> str:
    if (
        spin_result.get("proved")
        and not vacuity_result.get("vacuous")
        and trace_score > TRACE_THRESHOLD
    ):
        return "no_failure"
    if vacuity_result.get("vacuous"):
        return "property_error"
    if spin_result.get("syntax_ok") is False:
        return "modeling_error"
    if trace_score <= TRACE_THRESHOLD and trace_only_in_model and not trace_only_in_reference:
        return "modeling_error"
    if trace_score <= TRACE_THRESHOLD and trace_only_in_reference:
        return "program_bug"
    if spin_result.get("n_errors") is None:
        return "tool_limitation"
    return "missing_invariant"


def spin_for_classifier(syntax_ok: bool, skipped_pan: bool, proved: bool, claims: list) -> Dict[str, Any]:
    if not syntax_ok:
        return {"proved": False, "n_errors": None, "syntax_ok": False}
    if skipped_pan:
        return {"proved": False, "n_errors": None, "syntax_ok": True}
    errors: Optional[int] = 0
    for claim in claims:
        n = claim.get("errors") if isinstance(claim, dict) else getattr(claim, "errors", None)
        if n is None:
            errors = None
            break
        errors = max(errors or 0, n)
    return {"proved": proved, "n_errors": errors, "syntax_ok": True}
