"""Six §8.8 baselines. None of them is the five-stage pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from semanticdrift.agents.formalize import (
    ChatFn,
    Formalization,
    formalize,
    _requirement_text,
)
from semanticdrift.baselines.examples import few_shot_prefix
from semanticdrift.baselines.retrieve import retrieval_prefix
from semanticdrift.baselines.rules import rule_based_model
from semanticdrift.ollama import GENERATOR_MODEL
from semanticdrift.protocols import get_protocol
from semanticdrift.verifiers.spin import SpinVerifyResult, verify_text

BASELINES = (
    "zero_shot",
    "few_shot",
    "chain_of_thought",
    "verifier_feedback",
    "retrieval",
    "rule_based",
)

COT_INSTRUCTION = (
    "Reason step by step about the processes, shared variables, and LTL claims "
    "the requirement needs. Then output only the JSON object."
)

FEEDBACK_CAP = 5
VerifyFn = Callable[[str], SpinVerifyResult]


@dataclass
class BaselineRun:
    baseline: str
    name: str
    requirement: str
    n_calls: int
    retries: int = 0
    verified: Optional[bool] = None
    retrieved: Optional[str] = None
    used_validator: bool = False
    used_auditor: bool = False
    detail: str = ""
    artifact: Optional[Dict[str, Any]] = None
    history: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "baseline": self.baseline,
            "name": self.name,
            "requirement": self.requirement,
            "n_calls": self.n_calls,
            "retries": self.retries,
            "verified": self.verified,
            "retrieved": self.retrieved,
            "used_validator": self.used_validator,
            "used_auditor": self.used_auditor,
            "detail": self.detail,
            "artifact": self.artifact,
            "history": self.history,
        }


def run_baseline(
    kind: str,
    name: str,
    requirement: str = "precise",
    model: str = GENERATOR_MODEL,
    chat_fn: Optional[ChatFn] = None,
    verify_fn: Optional[VerifyFn] = None,
    cap: int = FEEDBACK_CAP,
    timeout: int = 180,
    use_embeddings: bool = False,
) -> BaselineRun:
    key = kind.strip().lower().replace("-", "_")
    if key not in BASELINES:
        raise ValueError(f"Unknown baseline {kind!r}. Choose one of: {', '.join(BASELINES)}")
    protocol = get_protocol(name)
    source = protocol.python_path.read_text(encoding="utf-8")
    req = _requirement_text(protocol, requirement)
    gold = protocol.promela_path.read_text(encoding="utf-8")

    if key == "rule_based":
        artifact = rule_based_model(name, req)
        return BaselineRun(
            baseline=key,
            name=name,
            requirement=requirement,
            n_calls=0,
            detail="keyword template; no language model",
            artifact=artifact.to_dict(),
        )

    prefix = ""
    system_extra = ""
    retrieved = None
    if key == "few_shot":
        prefix = few_shot_prefix()
    elif key == "chain_of_thought":
        system_extra = COT_INSTRUCTION
    elif key == "retrieval":
        prefix, retrieved = retrieval_prefix(
            req + "\n" + source,
            use_embeddings=use_embeddings,
        )

    if prefix and gold.strip() and gold.strip() in prefix:
        raise RuntimeError("baseline prompt leaked gold Promela")

    if key == "verifier_feedback":
        return _verifier_feedback(
            name,
            requirement,
            source,
            req,
            model=model,
            chat_fn=chat_fn,
            verify_fn=verify_fn or verify_text,
            cap=cap,
            timeout=timeout,
        )

    artifact = formalize(
        source,
        req,
        model=model,
        chat_fn=chat_fn,
        timeout=timeout,
        prefix=prefix,
        system_extra=system_extra,
    )
    return BaselineRun(
        baseline=key,
        name=name,
        requirement=requirement,
        n_calls=1,
        retrieved=retrieved,
        detail="single formalize call",
        artifact=artifact.to_dict(),
    )


def _verifier_feedback(
    name: str,
    requirement: str,
    source: str,
    req: str,
    model: str,
    chat_fn: Optional[ChatFn],
    verify_fn: VerifyFn,
    cap: int,
    timeout: int,
) -> BaselineRun:
    extra = ""
    history: List[Dict[str, Any]] = []
    artifact: Optional[Formalization] = None
    verified: Optional[bool] = None
    for attempt in range(1, cap + 1):
        artifact = formalize(
            source,
            req,
            model=model,
            chat_fn=chat_fn,
            timeout=timeout,
            extra=extra,
            extra_heading="VERIFIER FEEDBACK",
        )
        check = verify_fn(artifact.as_promela())
        record = {
            "attempt": attempt,
            "syntax_ok": check.syntax_ok,
            "skipped_pan": check.skipped_pan,
            "proved": check.proved,
        }
        history.append(record)
        if check.proved:
            verified = True
            break
        extra = _feedback_note(check)
        verified = False
    assert artifact is not None
    return BaselineRun(
        baseline="verifier_feedback",
        name=name,
        requirement=requirement,
        n_calls=len(history),
        retries=max(0, len(history) - 1),
        verified=verified,
        detail="formalize → verify → raw counterexample; no validator, no auditor",
        artifact=artifact.to_dict(),
        history=history,
    )


def _feedback_note(result: SpinVerifyResult) -> str:
    lines = [
        "The previous Promela did not verify. Edit the model or properties.",
        f"syntax_ok={result.syntax_ok}",
        f"skipped_pan={result.skipped_pan}",
        f"proved={result.proved}",
        result.syntax_detail,
    ]
    for claim in result.claims:
        if not claim.proved:
            lines.append(f"failed claim {claim.name}: {claim.detail}")
    return "\n".join(part for part in lines if part)
