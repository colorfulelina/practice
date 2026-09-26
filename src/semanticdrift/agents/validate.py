"""Independent validator (methodology §8.4).

SPIN's parser checks syntax. A different model (DeepSeek, not Qwen) scores
whether the generated Promela and LTL match the source and the English.
This step does not prove LTL and does not reuse the generator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from semanticdrift.agents.formalize import (
    ChatFn,
    Formalization,
    _requirement_text,
    load_formalization,
    parse_json_object,
)
from semanticdrift.ollama import VALIDATOR_MODEL, chat
from semanticdrift.promela import check_syntax_text
from semanticdrift.protocols import ROOT, get_protocol

VALIDATE_SYSTEM_PROMPT = """You are an independent reviewer, not the author
of this artifact. Compare the source code, the requirement, and the
formal model and property below. Answer strictly as JSON:
{"code_model_correspondence": 0-5, "requirement_property_correspondence":
0-5, "concerns": ["..."]}. Be skeptical: a high score should only be given
if every branch and every stated obligation in the requirement is
represented."""


@dataclass
class Validation:
    syntax_ok: bool
    syntax_detail: str
    code_model_correspondence: int
    requirement_property_correspondence: int
    concerns: List[str]
    validator_model: str = VALIDATOR_MODEL
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "syntax_ok": self.syntax_ok,
            "syntax_detail": self.syntax_detail,
            "code_model_correspondence": self.code_model_correspondence,
            "requirement_property_correspondence": self.requirement_property_correspondence,
            "concerns": self.concerns,
            "validator_model": self.validator_model,
        }


def correspondence_user_message(
    source_code: str,
    requirement_text: str,
    model_text: str,
    property_text: str,
) -> str:
    return (
        f"SOURCE:\n{source_code}\n\nREQUIREMENT:\n{requirement_text}"
        f"\n\nFORMAL MODEL:\n{model_text}\n\nPROPERTY:\n{property_text}"
    )


def property_text(artifact: Formalization) -> str:
    if not artifact.properties:
        return "(no named LTL properties)"
    return "\n".join(f"{p.name}: {p.formula}" for p in artifact.properties)


def parse_correspondence(text: str) -> Dict[str, Any]:
    data = parse_json_object(text)
    return {
        "code_model_correspondence": _score(data.get("code_model_correspondence")),
        "requirement_property_correspondence": _score(
            data.get("requirement_property_correspondence")
        ),
        "concerns": _concerns(data.get("concerns")),
        "raw": data,
    }


def validate_correspondence(
    source_code: str,
    requirement_text: str,
    model_text: str,
    property_blob: str,
    model: str = VALIDATOR_MODEL,
    chat_fn: Optional[ChatFn] = None,
    timeout: int = 180,
) -> Dict[str, Any]:
    messages = [
        {"role": "system", "content": VALIDATE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": correspondence_user_message(
                source_code, requirement_text, model_text, property_blob
            ),
        },
    ]
    runner = chat_fn or chat
    content = runner(model=model, messages=messages, timeout=timeout)
    parsed = parse_correspondence(content)
    parsed["validator_model"] = model
    return parsed


def validate_artifact(
    source_code: str,
    requirement_text: str,
    artifact: Formalization,
    model: str = VALIDATOR_MODEL,
    chat_fn: Optional[ChatFn] = None,
    timeout: int = 180,
) -> Validation:
    syntax_ok, syntax_detail = check_syntax_text(artifact.as_promela())
    scores = validate_correspondence(
        source_code,
        requirement_text,
        artifact.model,
        property_text(artifact),
        model=model,
        chat_fn=chat_fn,
        timeout=timeout,
    )
    return Validation(
        syntax_ok=syntax_ok,
        syntax_detail=syntax_detail,
        code_model_correspondence=scores["code_model_correspondence"],
        requirement_property_correspondence=scores["requirement_property_correspondence"],
        concerns=scores["concerns"],
        validator_model=model,
        raw=scores["raw"],
    )


def validate_protocol(
    name: str,
    requirement: str = "precise",
    from_json: Optional[Path] = None,
    model: str = VALIDATOR_MODEL,
    chat_fn: Optional[ChatFn] = None,
    timeout: int = 180,
) -> Validation:
    protocol = get_protocol(name)
    path = from_json or (ROOT / "results" / "formalize" / f"{name}_{requirement}.json")
    if not path.is_file():
        raise FileNotFoundError(
            f"No formalization at {path}. Run: python -m semanticdrift formalize "
            f"--name {name} --requirement {requirement}"
        )
    artifact = load_formalization(path)
    source = protocol.python_path.read_text(encoding="utf-8")
    req = _requirement_text(protocol, requirement)
    return validate_artifact(
        source,
        req,
        artifact,
        model=model,
        chat_fn=chat_fn,
        timeout=timeout,
    )


def _score(value: Any) -> int:
    if value is None:
        raise ValueError("validator JSON is missing a 0-5 correspondence score")
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"correspondence score is not a number: {value!r}") from exc
    if number < 0 or number > 5:
        raise ValueError(f"correspondence score must be 0-5, got {number}")
    return number


def _concerns(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]
