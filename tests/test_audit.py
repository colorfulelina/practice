"""Week 5: vacuity probes, traces, five-way classifier. No Ollama."""

from semanticdrift.audit.classify import classify_failure
from semanticdrift.audit.traces import (
    kind_agreement,
    model_events_from_promela,
    only_in_a,
    trace_agreement,
)
from semanticdrift.audit.vacuity_probe import replace_ltl
from semanticdrift.protocols import get_protocol


def test_classify_no_failure():
    assert (
        classify_failure(
            {"proved": True, "n_errors": 0},
            {"vacuous": False},
            0.95,
            False,
            False,
        )
        == "no_failure"
    )


def test_classify_property_error_beats_high_trace():
    assert (
        classify_failure(
            {"proved": True, "n_errors": 0},
            {"vacuous": True},
            0.99,
            False,
            False,
        )
        == "property_error"
    )


def test_classify_modeling_vs_program_bug():
    spin = {"proved": False, "n_errors": 1}
    vacuity = {"vacuous": False}
    assert (
        classify_failure(spin, vacuity, 0.4, True, False) == "modeling_error"
    )
    assert (
        classify_failure(spin, vacuity, 0.4, False, True) == "program_bug"
    )


def test_classify_tool_limitation_when_pan_never_ran():
    assert (
        classify_failure(
            {"proved": False, "n_errors": None, "syntax_ok": True},
            {"vacuous": False},
            1.0,
            False,
            False,
        )
        == "tool_limitation"
    )


def test_classify_parse_failure_is_modeling_error():
    assert (
        classify_failure(
            {"proved": False, "n_errors": None, "syntax_ok": False},
            {"vacuous": False},
            1.0,
            False,
            False,
        )
        == "modeling_error"
    )


def test_trace_agreement_and_kinds():
    ref = ["flag_set:0", "turn:1", "enter:0", "leave:0"]
    assert trace_agreement(ref, ref) == 1.0
    assert kind_agreement(ref, ["flag_set", "turn", "enter", "leave"]) == 1.0
    assert only_in_a(["enter:0"], ["flag_set:0"]) is True
    pml = "proctype P() { flag_set = 1; turn = 1; }"
    assert model_events_from_promela(pml, ref) == ["flag_set", "turn"]


def test_replace_ltl_swaps_named_claim():
    src = "bool x;\nltl mutex { [] !(a && b) }\n"
    out = replace_ltl(src, "mutex", "[] ! (false && true)")
    assert "[] ! (false && true)" in out
    assert "[] !(a && b)" not in out


def test_audit_gold_peterson_category_is_logged():
    """Gold should parse and prove; traces may not hit 0.9 (Promela abstracts)."""
    import shutil

    import pytest

    from semanticdrift.audit.run import audit_protocol

    if not shutil.which("spin") or not (shutil.which("cc") or shutil.which("gcc")):
        pytest.skip("spin/cc required")
    proto = get_protocol("peterson")
    result = audit_protocol("peterson", from_pml=proto.promela_path)
    assert result.spin["syntax_ok"] is True
    assert result.spin["proved"] is True
    assert result.category in {
        "no_failure",
        "property_error",
        "modeling_error",
        "program_bug",
        "tool_limitation",
        "missing_invariant",
    }
