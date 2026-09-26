"""One repair step. Each category may touch only its allowed artifact."""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any, Optional, Tuple

from semanticdrift.agents.formalize import (
    ChatFn,
    Formalization,
    parse_formalization,
    parse_json_object,
    _properties,
)
from semanticdrift.ollama import GENERATOR_MODEL, chat
from semanticdrift.repair.policy import allowed_targets, may_call_model
from semanticdrift.repair.weaken import weakening_reasons

PROPERTY_REPAIR_PROMPT = """You repair LTL properties only. Do not change the Promela
model. Do not weaken any claim: do not drop a property, do not replace a
formula with true, [] true, <> true, or X -> true, and do not remove
conjunctions or negations that made the claim stricter.
Return JSON with key properties: a list of {"name": "...", "formula": "..."}.
No other keys.
"""

MODEL_REPAIR_PROMPT = """You repair the Promela model only. Keep every existing
LTL property name and formula unchanged. The model string must be legal
Promela that SPIN can parse: proctype, bool, byte, chan, init, and
`ltl name { ... }` with operators [] <> ->. Do not write Python, C, or
made-up assignments like `mutex_model = mtype {`.
If SPIN reported a syntax error, rewrite the whole model so that error
goes away. Do not show or copy a gold reference.
Return JSON with keys: model, properties, assumptions, traceability.
The properties list must be the same claims as before.
"""


def apply_repair(
    category: str,
    artifact: Formalization,
    source_code: str,
    requirement_text: str,
    audit: Any,
    *,
    timeout_s: int,
    chat_fn: Optional[ChatFn] = None,
) -> Tuple[Formalization, int, str]:
    """Return (artifact, new_timeout, note). May raise ValueError on forbidden weaken."""
    targets = allowed_targets(category)
    if category == "program_bug":
        return artifact, timeout_s, "escalated: agent must not patch the code under test"
    if category == "tool_limitation":
        bumped = min(timeout_s * 2, 180)
        return artifact, bumped, f"raised SPIN timeout {timeout_s}s -> {bumped}s"
    if not may_call_model(category):
        return artifact, timeout_s, f"no repair agent for {category}"

    runner = chat_fn or chat
    if "model" in targets:
        extra = _model_note(audit)
        messages = [
            {"role": "system", "content": MODEL_REPAIR_PROMPT},
            {
                "role": "user",
                "content": (
                    f"SOURCE:\n{source_code}\n\nREQUIREMENT:\n{requirement_text}\n\n"
                    f"CURRENT MODEL:\n{artifact.model}\n\n"
                    f"KEEP PROPERTIES:\n{_props_blob(artifact)}\n\n{extra}"
                ),
            },
        ]
        content = runner(model=GENERATOR_MODEL, messages=messages, timeout=180)
        rewritten = parse_formalization(content, generator_model=GENERATOR_MODEL)
        if not (rewritten.model or "").strip():
            raise ValueError("rejected modeling repair: empty Promela")
        # modeling_error may touch the model only. If the LLM also rewrote
        # LTL, keep the old claims and drop any ltl blocks it added.
        merged = replace(
            rewritten,
            model=_strip_ltl_blocks(rewritten.model),
            properties=list(artifact.properties),
            assumptions=rewritten.assumptions or artifact.assumptions,
            traceability=rewritten.traceability or artifact.traceability,
        )
        return merged, timeout_s, "rewrote Promela only; properties kept"

    extra = _property_note(audit)
    messages = [
        {"role": "system", "content": PROPERTY_REPAIR_PROMPT},
        {
            "role": "user",
            "content": (
                f"REQUIREMENT:\n{requirement_text}\n\nCURRENT PROPERTIES:\n"
                f"{_props_blob(artifact)}\n\nMODEL (do not edit):\n{artifact.model}\n\n{extra}"
            ),
        },
    ]
    content = runner(model=GENERATOR_MODEL, messages=messages, timeout=180)
    data = parse_json_object(content)
    new_props = _properties(data.get("properties"))
    if category == "missing_invariant":
        names = {p.name for p in artifact.properties}
        combined = list(artifact.properties) + [p for p in new_props if p.name not in names]
        new_props = combined
    weakened, why = weakening_reasons(artifact.properties, new_props)
    if weakened:
        raise ValueError(f"rejected property repair: {why}")
    return replace(artifact, properties=new_props), timeout_s, "rewrote LTL only; Promela kept"


_LTL_BLOCK = re.compile(r"\n?ltl\s+\w+\s*\{.*?\}\s*", re.S)


def _strip_ltl_blocks(model: str) -> str:
    return _LTL_BLOCK.sub("\n", model or "").rstrip() + "\n"


def _props_blob(artifact: Formalization) -> str:
    if not artifact.properties:
        return "(none)"
    return "\n".join(f"{p.name}: {p.formula}" for p in artifact.properties)


def _model_note(audit: Any) -> str:
    traces = getattr(audit, "traces", {}) or {}
    spin = getattr(audit, "spin", {}) or {}
    syntax = spin.get("syntax_detail", "")
    ok = spin.get("syntax_ok")
    return (
        "SPIN PARSER:\n"
        f"syntax_ok={ok}\n{syntax}\n\n"
        "TRACE DISAGREEMENT:\n"
        f"score={traces.get('score')} only_in_model={traces.get('only_in_model')} "
        f"only_in_reference={traces.get('only_in_reference')}\n"
        f"reference_kinds={traces.get('reference_kinds')}\n"
        f"model_kinds={traces.get('model_kinds')}\n"
        "Rewrite model as legal Promela. Do not copy gold Promela."
    )


def _property_note(audit: Any) -> str:
    vacuity = getattr(audit, "vacuity", {}) or {}
    return f"VACUITY:\n{vacuity}\nDo not weaken. Fix structure only."
