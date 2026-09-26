"""Week 6: six §8.8 baselines. Does not call Ollama."""

from semanticdrift.agents.formalize import FORMALIZE_SYSTEM_PROMPT
from semanticdrift.baselines.examples import FEW_SHOT, few_shot_prefix
from semanticdrift.baselines.retrieve import retrieve_reference
from semanticdrift.baselines.rules import rule_based_model
from semanticdrift.baselines.run import run_baseline
from semanticdrift.protocols import get_protocol
from semanticdrift.verifiers.spin import SpinVerifyResult

SAMPLE = """
{
  "model": "bool flag0; ltl mutex { [] !(inCS0 && inCS1) }",
  "properties": [{"name": "mutex", "formula": "[] !(inCS0 && inCS1)"}],
  "assumptions": ["two processes"],
  "traceability": []
}
"""


def _fake_chat(bucket):
    def fake_chat(*, model, messages, timeout):
        bucket.append(messages)
        return SAMPLE

    return fake_chat


def test_few_shot_examples_are_not_gold_protocols():
    gold = get_protocol("peterson").promela_path.read_text(encoding="utf-8")
    prefix = few_shot_prefix()
    assert "DieHard" in prefix
    assert "One-bit clock" in prefix
    assert "Alternating-bit" in prefix
    assert gold.strip() not in prefix
    assert "PetersonMutex" not in prefix
    assert len(FEW_SHOT) == 3


def test_zero_shot_is_one_formalize_call_without_examples():
    seen = []
    result = run_baseline("zero_shot", "peterson", chat_fn=_fake_chat(seen))
    assert result.n_calls == 1
    assert result.used_validator is False
    assert result.used_auditor is False
    user = seen[0][1]["content"]
    assert "WORKED EXAMPLES" not in user
    assert "SOURCE:" in user
    assert "REQUIREMENT:" in user
    gold = get_protocol("peterson").promela_path.read_text(encoding="utf-8")
    assert gold.strip() not in user


def test_few_shot_prepends_three_examples():
    seen = []
    run_baseline("few_shot", "peterson", chat_fn=_fake_chat(seen))
    user = seen[0][1]["content"]
    assert user.count("Example —") == 3
    assert "DieHard" in user
    assert "SOURCE:" in user


def test_chain_of_thought_adds_step_by_step():
    seen = []
    run_baseline("chain_of_thought", "peterson", chat_fn=_fake_chat(seen))
    system = seen[0][0]["content"]
    assert "step by step" in system.lower()
    assert "model" in FORMALIZE_SYSTEM_PROMPT


def test_retrieval_picks_diehard_for_jugs():
    example, score = retrieve_reference(
        "3-gallon jug and 5-gallon jug four gallons of water",
        use_embeddings=False,
    )
    assert example.example_id == "diehard"
    assert score > 0


def test_retrieval_baseline_includes_nearest_example():
    seen = []
    result = run_baseline("retrieval", "peterson", chat_fn=_fake_chat(seen))
    assert result.retrieved
    user = seen[0][1]["content"]
    assert "RETRIEVED REFERENCE" in user
    gold = get_protocol("peterson").promela_path.read_text(encoding="utf-8")
    assert gold.strip() not in user


def test_rule_based_does_not_call_the_model():
    calls = []

    def boom(**kwargs):
        calls.append(kwargs)
        raise AssertionError("rule-based must not call a language model")

    result = run_baseline("rule_based", "peterson", chat_fn=boom)
    assert calls == []
    assert result.n_calls == 0
    assert result.artifact["generator_model"] == "rule_based"
    assert any(p["name"] == "mutex" for p in result.artifact["properties"])
    dining = rule_based_model("dining_philosophers")
    assert "fork" in dining.model


def test_verifier_feedback_retries_without_auditor():
    seen = []
    verdicts = [
        SpinVerifyResult(False, "parse error", True, False, []),
        SpinVerifyResult(True, "ok", False, True, []),
    ]

    def verify_fn(_text):
        return verdicts.pop(0)

    result = run_baseline(
        "verifier_feedback",
        "peterson",
        chat_fn=_fake_chat(seen),
        verify_fn=verify_fn,
        cap=5,
    )
    assert result.n_calls == 2
    assert result.retries == 1
    assert result.verified is True
    assert result.used_validator is False
    assert result.used_auditor is False
    second = seen[1][1]["content"]
    assert "VERIFIER FEEDBACK" in second
    assert "parse error" in second
    blob = " ".join(m[0]["content"] for m in seen).lower()
    assert "deepseek" not in blob
    assert "vacuity" not in blob
