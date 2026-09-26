"""Week 4: formalization agent JSON shape. Does not call Ollama."""

from semanticdrift.agents.formalize import (
    FORMALIZE_SYSTEM_PROMPT,
    formalize,
    formalize_protocol,
    parse_formalization,
    user_message,
)
from semanticdrift.protocols import get_protocol


SAMPLE = """
{
  "model": "bool flag0; ltl mutex { [] !(inCS0 && inCS1) }",
  "properties": [{"name": "mutex", "formula": "[] !(inCS0 && inCS1)"}],
  "assumptions": ["two processes"],
  "traceability": [{"element": "mutex", "source": "requirement sentence 1"}]
}
"""


def test_prompt_asks_for_the_four_json_keys():
    for key in ("model", "properties", "assumptions", "traceability"):
        assert key in FORMALIZE_SYSTEM_PROMPT


def test_user_message_is_source_and_requirement_not_gold_promela():
    proto = get_protocol("peterson")
    source = proto.python_path.read_text(encoding="utf-8")
    message = user_message(source, proto.requirement_precise)
    assert "SOURCE:" in message
    assert "REQUIREMENT:" in message
    assert "PetersonMutex" in message
    gold = proto.promela_path.read_text(encoding="utf-8")
    assert gold.strip() not in message
    assert "Gold Promela" not in message


def test_parse_accepts_fenced_json():
    result = parse_formalization("```json\n" + SAMPLE + "\n```")
    assert "bool flag0" in result.model
    assert result.properties[0].name == "mutex"
    assert "[] !(inCS0 && inCS1)" in result.properties[0].formula
    assert result.assumptions == ["two processes"]


def test_as_promela_appends_ltl_when_missing():
    result = parse_formalization(
        """
        {
          "model": "bool flag0 = 0;",
          "properties": [{"name": "mutex", "formula": "[] !(inCS0 && inCS1)"}],
          "assumptions": [],
          "traceability": []
        }
        """
    )
    text = result.as_promela()
    assert "ltl mutex" in text
    assert "[] !(inCS0 && inCS1)" in text


def test_formalize_uses_injected_chat_and_does_not_self_check():
    calls = []

    def fake_chat(*, model, messages, timeout):
        calls.append((model, messages, timeout))
        return SAMPLE

    result = formalize("code", "must be mutex", chat_fn=fake_chat, model="qwen2.5-coder:7b")
    assert result.properties[0].name == "mutex"
    assert calls[0][0] == "qwen2.5-coder:7b"
    assert "must be mutex" in calls[0][1][1]["content"]
    # The formalizer must not be asked to validate or prove.
    blob = FORMALIZE_SYSTEM_PROMPT.lower() + calls[0][1][0]["content"].lower()
    assert "spin -a" not in blob
    assert "deepseek" not in blob


def test_formalize_protocol_reads_python_not_gold_pml():
    seen = {}

    def fake_chat(*, model, messages, timeout):
        seen["user"] = messages[1]["content"]
        return SAMPLE

    formalize_protocol("peterson", requirement="precise", chat_fn=fake_chat)
    user = seen["user"]
    assert "class PetersonMutex" in user
    assert "ltl mutex { [] !(inCS0 && inCS1) }" not in user
