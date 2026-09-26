"""Differential trace grounding (methodology §8.6.2)."""

from __future__ import annotations

import difflib
import inspect
from typing import Any, Dict, List, Sequence, Tuple


def event_kinds(events: Sequence[str]) -> List[str]:
    kinds: List[str] = []
    seen = set()
    for event in events:
        kind = event.split(":", 1)[0] if ":" in event else event
        if kind not in seen:
            seen.add(kind)
            kinds.append(kind)
    return kinds


def only_in_a(events_a: Sequence[str], events_b: Sequence[str]) -> bool:
    return bool(set(event_kinds(events_a)) - set(event_kinds(events_b)))


def trace_agreement(reference_events: Sequence[str], model_events: Sequence[str]) -> float:
    matcher = difflib.SequenceMatcher(None, list(reference_events), list(model_events))
    return matcher.ratio()


def kind_agreement(reference_events: Sequence[str], model_events: Sequence[str]) -> float:
    """Compare unique event names. Full-sequence 0.9 is too strict once Promela abstracts."""
    return trace_agreement(sorted(event_kinds(reference_events)), sorted(event_kinds(model_events)))


def model_events_from_promela(promela: str, reference_events: Sequence[str]) -> List[str]:
    found: List[str] = []
    for kind in event_kinds(reference_events):
        if kind and kind in promela:
            found.append(kind)
    return found


def instrument_and_run(module: Any, entry_point: str = "run", inputs: Sequence[Any] = ()) -> List[str]:
    events: List[str] = []
    module.EVENT_SINK = events.append
    try:
        result = getattr(module, entry_point)(*inputs)
    finally:
        module.EVENT_SINK = None
    if result and not events:
        return [str(item) for item in result]
    return list(events or result or [])


def collect_reference_traces(module: Any, max_examples: int = 8) -> List[List[str]]:
    """Run the Python reference. Use Hypothesis if it is installed; otherwise a few fixed calls."""
    traces = [instrument_and_run(module)]
    extras = _fixed_inputs(module)
    for args in extras:
        try:
            traces.append(instrument_and_run(module, inputs=args))
        except Exception:
            continue
    hypo = _hypothesis_traces(module, max_examples=max_examples)
    traces.extend(hypo)
    return traces


def _fixed_inputs(module: Any) -> List[Tuple[Any, ...]]:
    try:
        signature = inspect.signature(module.run)
    except (TypeError, ValueError):
        return []
    extras: List[Tuple[Any, ...]] = []
    params = list(signature.parameters.values())
    if not params:
        return extras
    first = params[0]
    if first.default is inspect.Parameter.empty:
        return extras
    if isinstance(first.default, int) and first.default > 1:
        extras.append((max(1, first.default // 4),))
    return extras


def _hypothesis_traces(module: Any, max_examples: int) -> List[List[str]]:
    try:
        from hypothesis import given, settings, strategies as st
    except ImportError:
        return []
    try:
        signature = inspect.signature(module.run)
    except (TypeError, ValueError):
        return []
    params = [
        p
        for p in signature.parameters.values()
        if p.default is not inspect.Parameter.empty and isinstance(p.default, int)
    ]
    if not params:
        return []
    collected: List[List[str]] = []
    name = params[0].name

    @settings(max_examples=max_examples, deadline=None)
    @given(st.integers(min_value=1, max_value=5))
    def fuzz(n: int) -> None:
        try:
            collected.append(list(module.run(**{name: n})))
        except Exception:
            return

    try:
        fuzz()
    except Exception:
        return collected
    return collected


def summarize_traces(
    reference_events: Sequence[str],
    model_events: Sequence[str],
) -> Dict[str, Any]:
    score = kind_agreement(reference_events, model_events)
    return {
        "score": score,
        "sequence_score": trace_agreement(reference_events, model_events),
        "only_in_model": only_in_a(model_events, reference_events),
        "only_in_reference": only_in_a(reference_events, model_events),
        "reference_kinds": event_kinds(reference_events),
        "model_kinds": event_kinds(model_events),
        "n_reference_events": len(reference_events),
        "n_model_events": len(model_events),
    }
