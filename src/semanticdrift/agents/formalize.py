"""Formalization agent: Qwen writes Promela + LTL as JSON (methodology §8.3).

Input is source code and the English requirement only. Gold Promela is not
shown. This function does not parse, prove, or score its own output.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from semanticdrift.ollama import GENERATOR_MODEL, chat
from semanticdrift.protocols import Protocol, get_protocol

ChatFn = Callable[..., str]

FORMALIZE_SYSTEM_PROMPT = """You are a formalization assistant. Given source
code and a natural-language requirement, produce:
1. A Promela model capturing the relevant behavior.
2. One or more LTL properties capturing the requirement.
3. A short list of explicit assumptions you made.
4. A traceability line for each formal element, pointing at the source
line number or requirement sentence it came from.
Return your answer as JSON with keys: model, properties, assumptions,
traceability. Do not include any text outside the JSON object.
- model: Promela source as a string.
- properties: a list of objects {"name": "...", "formula": "..."} using
  SPIN LTL operators [] <> ->. Put the same claims in the Promela as
  `ltl name { formula }` blocks if you can.
- assumptions: a list of strings.
- traceability: a list of objects {"element": "...", "source": "..."}.
"""

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.I)


@dataclass
class LTLProperty:
    name: str
    formula: str


@dataclass
class Formalization:
    model: str
    properties: List[LTLProperty]
    assumptions: List[str]
    traceability: List[Any]
    raw: Dict[str, Any] = field(default_factory=dict)
    generator_model: str = GENERATOR_MODEL

    def as_promela(self) -> str:
        text = (self.model or "").rstrip()
        if "ltl " in text:
            return text + "\n"
        blocks = []
        for prop in self.properties:
            if not prop.name or not prop.formula:
                continue
            blocks.append(f"ltl {prop.name} {{ {prop.formula} }}")
        if not blocks:
            return text + "\n"
        return text + "\n\n" + "\n".join(blocks) + "\n"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "generator_model": self.generator_model,
            "model": self.model,
            "properties": [{"name": p.name, "formula": p.formula} for p in self.properties],
            "assumptions": self.assumptions,
            "traceability": self.traceability,
        }


def user_message(
    source_code: str,
    requirement_text: str,
    extra: str = "",
    prefix: str = "",
    extra_heading: str = "REPAIR NOTE",
) -> str:
    parts = []
    if prefix.strip():
        parts.append(prefix.strip())
    parts.append(f"SOURCE:\n{source_code}\n\nREQUIREMENT:\n{requirement_text}")
    if extra.strip():
        parts.append(f"{extra_heading}:\n{extra.strip()}")
    return "\n\n".join(parts)


def parse_json_object(text: str) -> Dict[str, Any]:
    cleaned = _FENCE.sub("", text.strip()).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            raise
        data = json.loads(cleaned[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("formalization JSON must be an object")
    return data


def parse_formalization(text: str, generator_model: str = GENERATOR_MODEL) -> Formalization:
    data = parse_json_object(text)
    model = data.get("model")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("JSON is missing a non-empty 'model' string")
    return Formalization(
        model=model,
        properties=_properties(data.get("properties")),
        assumptions=_string_list(data.get("assumptions")),
        traceability=_as_list(data.get("traceability")),
        raw=data,
        generator_model=generator_model,
    )


def formalize(
    source_code: str,
    requirement_text: str,
    model: str = GENERATOR_MODEL,
    chat_fn: Optional[ChatFn] = None,
    timeout: int = 180,
    extra: str = "",
    prefix: str = "",
    system_extra: str = "",
    extra_heading: str = "REPAIR NOTE",
) -> Formalization:
    system = FORMALIZE_SYSTEM_PROMPT
    if system_extra.strip():
        system = system.rstrip() + "\n" + system_extra.strip()
    messages = [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": user_message(
                source_code,
                requirement_text,
                extra,
                prefix=prefix,
                extra_heading=extra_heading,
            ),
        },
    ]
    runner = chat_fn or chat
    content = runner(model=model, messages=messages, timeout=timeout)
    return parse_formalization(content, generator_model=model)


def formalize_protocol(
    name: str,
    requirement: str = "precise",
    model: str = GENERATOR_MODEL,
    chat_fn: Optional[ChatFn] = None,
    timeout: int = 180,
    proto: Optional[Protocol] = None,
    extra: str = "",
    prefix: str = "",
    system_extra: str = "",
    extra_heading: str = "REPAIR NOTE",
) -> Formalization:
    protocol = proto or get_protocol(name)
    source = protocol.python_path.read_text(encoding="utf-8")
    text = _requirement_text(protocol, requirement)
    return formalize(
        source,
        text,
        model=model,
        chat_fn=chat_fn,
        timeout=timeout,
        extra=extra,
        prefix=prefix,
        system_extra=system_extra,
        extra_heading=extra_heading,
    )


def load_formalization(path: Path) -> Formalization:
    data = json.loads(path.read_text(encoding="utf-8"))
    model = data.get("model")
    if not isinstance(model, str) or not model.strip():
        raise ValueError(f"{path} is missing a non-empty 'model' string")
    return Formalization(
        model=model,
        properties=_properties(data.get("properties")),
        assumptions=_string_list(data.get("assumptions")),
        traceability=_as_list(data.get("traceability")),
        raw=data,
        generator_model=str(data.get("generator_model") or GENERATOR_MODEL),
    )


def write_formalization(result: Formalization, directory: Path, stem: str) -> Dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / f"{stem}.json"
    pml_path = directory / f"{stem}.pml"
    json_path.write_text(json.dumps(result.to_dict(), indent=2) + "\n", encoding="utf-8")
    pml_path.write_text(result.as_promela(), encoding="utf-8")
    return {"json": json_path, "pml": pml_path}


def _requirement_text(protocol: Protocol, variant: str) -> str:
    key = variant.strip().lower()
    if key == "precise":
        return protocol.requirement_precise
    if key == "ambiguous":
        if not protocol.requirement_ambiguous.strip():
            raise ValueError(f"{protocol.name} has no ambiguous requirement")
        return protocol.requirement_ambiguous
    raise ValueError("requirement must be 'precise' or 'ambiguous'")


def _properties(value: Any) -> List[LTLProperty]:
    if value is None:
        return []
    if isinstance(value, dict):
        return [
            LTLProperty(name=str(name), formula=str(formula).strip())
            for name, formula in value.items()
        ]
    if not isinstance(value, list):
        raise ValueError("'properties' must be a list or object")
    out: List[LTLProperty] = []
    for index, item in enumerate(value):
        if isinstance(item, str):
            out.append(LTLProperty(name=f"p{index}", formula=item.strip()))
        elif isinstance(item, dict):
            name = str(item.get("name") or item.get("id") or f"p{index}")
            formula = item.get("formula") or item.get("ltl") or item.get("property") or ""
            out.append(LTLProperty(name=name, formula=str(formula).strip()))
        else:
            raise ValueError(f"unusable property entry: {item!r}")
    return out


def _string_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]
