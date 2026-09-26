"""Week 4: independent validator. Parser is SPIN; scorer is not Qwen."""

from semanticdrift.agents.formalize import Formalization, LTLProperty
from semanticdrift.agents.validate import (
    VALIDATE_SYSTEM_PROMPT,
    parse_correspondence,
    validate_artifact,
    validate_correspondence,
)
from semanticdrift.ollama import GENERATOR_MODEL, VALIDATOR_MODEL
from semanticdrift.promela import check_syntax_text
from semanticdrift.protocols import get_protocol


def test_validator_default_is_deepseek_not_qwen():
    assert VALIDATOR_MODEL.startswith("deepseek")
    assert VALIDATOR_MODEL != GENERATOR_MODEL
    assert "independent reviewer" in VALIDATE_SYSTEM_PROMPT.lower()
    assert "qwen" not in VALIDATE_SYSTEM_PROMPT.lower()


def test_spin_rejects_generated_style_python_and_accepts_gold():
    garbage = "proctype Process(i) { mutex->lock(i); }\n"
    ok, _detail = check_syntax_text(garbage)
    assert ok is False
    gold = get_protocol("peterson").promela_path.read_text(encoding="utf-8")
    ok_gold, _ = check_syntax_text(gold)
    assert ok_gold is True


def test_parse_correspondence_scores():
    parsed = parse_correspondence(
        '{"code_model_correspondence": 1, "requirement_property_correspondence": 2, "concerns": ["not Promela"]}'
    )
    assert parsed["code_model_correspondence"] == 1
    assert parsed["requirement_property_correspondence"] == 2
    assert parsed["concerns"] == ["not Promela"]


def test_validate_artifact_uses_injected_chat_not_generator():
    calls = []

    def fake_chat(*, model, messages, timeout):
        calls.append(model)
        return '{"code_model_correspondence": 1, "requirement_property_correspondence": 0, "concerns": ["Python in Promela"]}'

    proto = get_protocol("peterson")
    artifact = Formalization(
        model="proctype P() { mutex->lock(i); }",
        properties=[LTLProperty("mutex", "[] !(inCS0 && inCS1)")],
        assumptions=[],
        traceability=[],
    )
    result = validate_artifact(
        proto.python_path.read_text(encoding="utf-8"),
        proto.requirement_precise,
        artifact,
        chat_fn=fake_chat,
    )
    assert calls == [VALIDATOR_MODEL]
    assert result.code_model_correspondence == 1
    assert result.requirement_property_correspondence == 0
    assert result.syntax_ok is False


def test_correspondence_prompt_includes_source_requirement_and_artifact():
    seen = {}

    def fake_chat(*, model, messages, timeout):
        seen["user"] = messages[1]["content"]
        return '{"code_model_correspondence": 0, "requirement_property_correspondence": 0, "concerns": []}'

    validate_correspondence("src", "req", "pml", "ltl mutex", chat_fn=fake_chat)
    user = seen["user"]
    assert "SOURCE:\nsrc" in user
    assert "REQUIREMENT:\nreq" in user
    assert "FORMAL MODEL:\npml" in user
    assert "PROPERTY:\nltl mutex" in user
