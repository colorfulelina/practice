"""Week 6: SVR / VSR / TAR / FAR / ATS. FAR must not count vacuity twice."""

from semanticdrift.metrics import compute_metrics, far_flag, task_row_from_audit
from semanticdrift.pipeline import run_pipeline


def _audit(*, syntax_ok, proved, skipped=False, score=1.0, vacuous=False, claims=None, category="no_failure"):
    if claims is None:
        claims = [{"name": "mutex", "proved": proved, "errors": 0 if syntax_ok and not skipped else None}]
        if syntax_ok and not skipped and not proved:
            claims[0]["errors"] = 1
    return {
        "category": category,
        "spin": {
            "syntax_ok": syntax_ok,
            "skipped_pan": skipped,
            "proved": proved,
            "claims": claims,
        },
        "traces": {"score": score},
        "vacuity": {"vacuous": vacuous},
    }


def test_far_ignores_vacuity_and_flags_low_trace():
    vacuous_ok_traces = task_row_from_audit(
        "p", "precise", _audit(syntax_ok=True, proved=True, score=1.0, vacuous=True)
    )
    assert far_flag(vacuous_ok_traces) is False
    low_trace = task_row_from_audit(
        "p", "precise", _audit(syntax_ok=True, proved=True, score=0.2, vacuous=False)
    )
    assert far_flag(low_trace) is True


def test_aggregate_matches_section_9_1():
    rows = [
        task_row_from_audit("a", "precise", _audit(syntax_ok=False, proved=False, skipped=True, claims=[])),
        task_row_from_audit("b", "precise", _audit(syntax_ok=True, proved=True, score=1.0, vacuous=False)),
        task_row_from_audit("c", "precise", _audit(syntax_ok=True, proved=True, score=0.1, vacuous=False)),
        task_row_from_audit("d", "precise", _audit(syntax_ok=True, proved=True, score=1.0, vacuous=True)),
        task_row_from_audit(
            "e",
            "precise",
            _audit(
                syntax_ok=True,
                proved=False,
                score=0.5,
                vacuous=False,
                claims=[{"name": "mutex", "proved": False, "errors": None}],
            ),
        ),
    ]
    metrics = compute_metrics(rows)
    assert metrics["n_tasks"] == 5
    assert metrics["SVR"] == 0.8
    # four parsed; three have a definite verdict (2 proved + 1 refuted)
    assert metrics["VSR"] == 0.75
    assert metrics["n_proved"] == 3
    assert metrics["vacuity_rate"] == 1 / 3
    # FAR: of 3 proved, only the score=0.1 row is flagged (vacuous+good traces is not FAR)
    assert metrics["FAR"] == 1 / 3
    assert abs(metrics["ATS"] - (0.75 * (2 / 3) * (2 / 3))) < 1e-9


def test_pipeline_uses_injected_chat(tmp_path):
    sample = """
    {
      "model": "bool flag0 = 0; bool inCS0 = 0; bool inCS1 = 0;\\nltl mutex { [] !(inCS0 && inCS1) }",
      "properties": [{"name": "mutex", "formula": "[] !(inCS0 && inCS1)"}],
      "assumptions": [],
      "traceability": []
    }
    """
    scores = (
        '{"code_model_correspondence": 2,'
        ' "requirement_property_correspondence": 2, "concerns": ["test"]}'
    )

    def fake_chat(*, model, messages, timeout):
        blob = messages[0]["content"].lower()
        if "independent reviewer" in blob:
            return scores
        return sample

    result = run_pipeline(
        "peterson",
        requirement="precise",
        chat_fn=fake_chat,
        validator_chat_fn=fake_chat,
        cap=1,
        out_dir=tmp_path,
    )
    assert result.error is None
    assert result.task["name"] == "peterson"
    assert "syntax_ok" in result.task
    assert (tmp_path / "peterson_precise.json").is_file()
    assert "formalize" in result.stages
    assert "validate" in result.stages
    assert "audit" in result.stages
