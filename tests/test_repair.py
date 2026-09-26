"""Week 6: repair policy. Never patch source; never weaken properties."""

from semanticdrift.agents.formalize import Formalization, LTLProperty
from semanticdrift.repair.loop import repair_protocol
from semanticdrift.repair.policy import allowed_targets, may_call_model
from semanticdrift.repair.weaken import is_property_weakened


def test_program_bug_cannot_touch_source():
    assert allowed_targets("program_bug") == frozenset()
    assert may_call_model("program_bug") is False
    assert "source_code" not in allowed_targets("modeling_error")
    assert "source_code" not in allowed_targets("property_error")


def test_property_weakening_detected():
    before = [LTLProperty("mutex", "[] !(inCS0 && inCS1)")]
    assert is_property_weakened(before, [LTLProperty("mutex", "[] true")]) is True
    assert is_property_weakened(before, [LTLProperty("mutex", "[] !(inCS0 && inCS1)")]) is False
    assert is_property_weakened(before, []) is True
    starve = [LTLProperty("s", "[] (flag0 -> <> inCS0)")]
    assert is_property_weakened(starve, [LTLProperty("s", "[] (flag0 -> true)")]) is True


def test_repair_program_bug_escalates_without_llm():
    calls = []

    def fake_chat(**kwargs):
        calls.append(kwargs)
        raise AssertionError("LLM should not run for program_bug")

    # Force program_bug: kinds in Promela miss reference events (empty model).
    artifact = Formalization(
        model="bool x = 0;\ninit { x = 0 }\nltl stay { [] (x == 0) }\n",
        properties=[LTLProperty("stay", "[] (x == 0)")],
        assumptions=[],
        traceability=[],
    )
    from semanticdrift.protocols import ROOT

    out = ROOT / "results" / "formalize"
    out.mkdir(parents=True, exist_ok=True)
    path = out / "peterson_precise.json"
    # Keep the real Qwen file if present; write a temp sidecar instead.
    path = ROOT / "results" / "formalize" / "_repair_test.json"
    path.write_text(
        '{"model":"bool unused = 0;\\ninit { unused = 0 }\\nltl p { [] (unused == 0) }\\n",'
        '"properties":[{"name":"p","formula":"[] (unused == 0)"}],'
        '"assumptions":[],"traceability":[]}\n',
        encoding="utf-8",
    )
    # Parses, so this is not a syntax modeling_error. vs Peterson traces it
    # misses flag_set etc. → only_in_reference → program_bug.
    result = repair_protocol(
        "peterson",
        from_json=path,
        cap=2,
        chat_fn=fake_chat,
    )
    assert result.source_path_untouched is True
    assert calls == []
    assert result.stopped in {"escalated_program_bug", "rejected_weakening", "cap_reached"}
    assert all(step.get("action") != "patch_source" for step in result.history)


def test_weakening_repair_is_rejected():
    from semanticdrift.agents.formalize import Formalization
    from semanticdrift.repair.steps import apply_repair

    artifact = Formalization(
        model="bool x;",
        properties=[LTLProperty("mutex", "[] !(inCS0 && inCS1)")],
        assumptions=[],
        traceability=[],
    )

    def weaken(**kwargs):
        return '{"properties": [{"name": "mutex", "formula": "[] true"}]}'

    class Audit:
        vacuity = {"vacuous": True}
        traces = {}
        spin = {}

    try:
        apply_repair(
            "property_error",
            artifact,
            "src",
            "req",
            Audit(),
            timeout_s=45,
            chat_fn=weaken,
        )
        raised = False
    except ValueError as exc:
        raised = True
        assert "weaken" in str(exc).lower() or "rejected" in str(exc).lower()
    assert raised


def test_modeling_repair_keeps_old_ltl_when_llm_drifts():
    from semanticdrift.repair.steps import apply_repair

    artifact = Formalization(
        model="bool x = 0;\ninit { x = 0 }\n",
        properties=[LTLProperty("mutex", "[] !(inCS0 && inCS1)")],
        assumptions=["fair"],
        traceability=[],
    )

    def drift(**kwargs):
        return (
            '{"model":"bool y = 1;\\ninit { y = 1 }\\nltl mutex { [] true }\\n",'
            '"properties":[{"name":"mutex","formula":"[] true"}],'
            '"assumptions":[],"traceability":[]}'
        )

    class Audit:
        vacuity = {}
        traces = {"score": 0.1}
        spin = {"syntax_ok": False, "syntax_detail": "expected ;"}

    merged, timeout, note = apply_repair(
        "modeling_error",
        artifact,
        "src",
        "req",
        Audit(),
        timeout_s=45,
        chat_fn=drift,
    )
    assert timeout == 45
    assert "Promela only" in note
    assert merged.properties[0].formula == "[] !(inCS0 && inCS1)"
    assert "bool y = 1" in merged.model
    assert "[] true" not in merged.as_promela()
    assert "[] !(inCS0 && inCS1)" in merged.as_promela()
