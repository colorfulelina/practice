"""Six §8.8 baselines, plus few-shot + verifier-feedback.

None of these is the five-stage pipeline. The extra combined condition
keeps the TLA+ Promela examples on every retry and sends spin -a text
back. It does not show gold Promela.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Callable, Dict, List, Optional

from semanticdrift.agents.formalize import (
    ChatFn,
    Formalization,
    formalize,
    parse_json_object,
    _properties,
    _requirement_text,
)
from semanticdrift.baselines.examples import few_shot_prefix
from semanticdrift.baselines.retrieve import retrieval_prefix
from semanticdrift.baselines.rules import rule_based_model
from semanticdrift.ollama import GENERATOR_MODEL, chat
from semanticdrift.protocols import get_protocol
from semanticdrift.repair.steps import PROPERTY_REPAIR_PROMPT, _strip_ltl_blocks
from semanticdrift.verifiers.spin import SpinVerifyResult, verify_text

BASELINES = (
    "zero_shot",
    "few_shot",
    "chain_of_thought",
    "verifier_feedback",
    "retrieval",
    "rule_based",
    "few_shot_verifier_feedback",
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
    if key in ("few_shot", "few_shot_verifier_feedback"):
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

    if key in ("verifier_feedback", "few_shot_verifier_feedback"):
        keep_legal = key == "few_shot_verifier_feedback"
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
            prefix=prefix,
            kind=key,
            keep_last_legal=keep_legal,
            property_only_after_parse=keep_legal,
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
    prefix: str = "",
    kind: str = "verifier_feedback",
    keep_last_legal: bool = False,
    property_only_after_parse: bool = False,
) -> BaselineRun:
    extra = ""
    history: List[Dict[str, Any]] = []
    artifact: Optional[Formalization] = None
    last_legal: Optional[Formalization] = None
    last_legal_check: Optional[SpinVerifyResult] = None
    verified: Optional[bool] = None
    for attempt in range(1, cap + 1):
        phase = (
            "properties"
            if property_only_after_parse and last_legal is not None
            else "model"
        )
        if phase == "properties":
            assert last_legal is not None
            try:
                candidate = _rewrite_properties(
                    last_legal,
                    req,
                    extra,
                    model=model,
                    chat_fn=chat_fn,
                    timeout=timeout,
                )
            except (ValueError, KeyError) as exc:
                history.append(
                    {
                        "attempt": attempt,
                        "phase": phase,
                        "syntax_ok": last_legal_check.syntax_ok if last_legal_check else False,
                        "skipped_pan": last_legal_check.skipped_pan if last_legal_check else True,
                        "proved": False,
                        "kept": False,
                        "note": f"rejected property rewrite: {exc}",
                    }
                )
                verified = False
                extra = _feedback_note(last_legal_check) if last_legal_check else extra
                continue
        else:
            candidate = formalize(
                source,
                req,
                model=model,
                chat_fn=chat_fn,
                timeout=timeout,
                prefix=prefix,
                extra=extra,
                extra_heading="VERIFIER FEEDBACK",
            )
        if keep_last_legal:
            candidate = replace(candidate, model=_strip_ltl_blocks(candidate.model))
        check = verify_fn(candidate.as_promela())
        kept = True
        note = ""
        if keep_last_legal and not check.syntax_ok and last_legal is not None:
            kept = False
            note = "rejected illegal rewrite; kept last file spin -a accepted"
            candidate = last_legal
            check = last_legal_check or check
        elif check.syntax_ok:
            last_legal = candidate
            last_legal_check = check
        if kept:
            artifact = candidate
        record = {
            "attempt": attempt,
            "phase": phase,
            "syntax_ok": check.syntax_ok if kept else False,
            "skipped_pan": check.skipped_pan if kept else True,
            "proved": check.proved if kept else False,
            "kept": kept,
        }
        if note:
            record["note"] = note
        history.append(record)
        if kept and check.proved:
            verified = True
            break
        extra = _feedback_note(
            last_legal_check if (keep_last_legal and last_legal_check) else check
        )
        if keep_last_legal and not kept:
            extra = "Rewrite rejected: not legal Promela.\n" + extra
        if property_only_after_parse and last_legal is not None:
            extra = _property_feedback_note(
                last_legal_check if last_legal_check else check
            )
        verified = False
    if artifact is None:
        artifact = last_legal
    assert artifact is not None
    if last_legal is not None:
        artifact = last_legal
    detail = "formalize → verify → raw counterexample; no validator, no auditor"
    if prefix and keep_last_legal:
        detail = (
            "few-shot examples + spin -a keep-last-legal; after parse, LTL only; "
            "no validator, no auditor"
        )
    elif prefix:
        detail = (
            "few-shot examples + formalize → verify → raw counterexample; "
            "no validator, no auditor"
        )
    return BaselineRun(
        baseline=kind,
        name=name,
        requirement=requirement,
        n_calls=len(history),
        retries=max(0, len(history) - 1),
        verified=verified,
        detail=detail,
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


def _property_feedback_note(result: SpinVerifyResult) -> str:
    lines = [
        "The Promela parsed. Do not rewrite the model.",
        "Change only the LTL claims so they match the requirement.",
        f"syntax_ok={result.syntax_ok}",
        f"proved={result.proved}",
    ]
    for claim in result.claims:
        if not claim.proved:
            lines.append(f"failed claim {claim.name}: {claim.formula} — {claim.detail}")
        else:
            lines.append(f"proved claim {claim.name}: {claim.formula}")
    return "\n".join(part for part in lines if part)


def _rewrite_properties(
    artifact: Formalization,
    requirement_text: str,
    extra: str,
    *,
    model: str,
    chat_fn: Optional[ChatFn],
    timeout: int,
) -> Formalization:
    runner = chat_fn or chat
    props = "\n".join(f"{p.name}: {p.formula}" for p in artifact.properties) or "(none)"
    user = (
        f"REQUIREMENT:\n{requirement_text}\n\nCURRENT PROPERTIES:\n{props}\n\n"
        f"MODEL (do not edit):\n{artifact.model}\n"
    )
    if extra.strip():
        user += f"\nVERIFIER FEEDBACK:\n{extra.strip()}\n"
    content = runner(
        model=model,
        messages=[
            {"role": "system", "content": PROPERTY_REPAIR_PROMPT},
            {"role": "user", "content": user},
        ],
        timeout=timeout,
    )
    data = parse_json_object(content)
    new_props = _properties(data.get("properties"))
    if not new_props:
        raise ValueError("property rewrite returned no properties")
    return replace(
        artifact,
        model=_strip_ltl_blocks(artifact.model),
        properties=new_props,
    )
