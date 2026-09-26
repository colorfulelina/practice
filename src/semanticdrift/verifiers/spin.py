"""SPIN as an unmodified subprocess (methodology §8.5).

`spin -a` is the parser. `pan` is compiled and run only if that succeeds.
This wrapper does not edit Promela or LTL.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from semanticdrift.agents.formalize import load_formalization
from semanticdrift.promela import ClaimProof, check_syntax, prove_file
from semanticdrift.protocols import ROOT

_TMP_ROOT = ROOT / "tmp"


@dataclass
class SpinVerifyResult:
    syntax_ok: bool
    syntax_detail: str
    skipped_pan: bool
    proved: bool
    claims: List[ClaimProof] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "syntax_ok": self.syntax_ok,
            "syntax_detail": self.syntax_detail,
            "skipped_pan": self.skipped_pan,
            "proved": self.proved,
            "claims": [claim.to_dict() for claim in self.claims],
        }


def verify_path(pml: Path, timeout: int = 120) -> SpinVerifyResult:
    ok, detail = check_syntax(pml)
    if not ok:
        return SpinVerifyResult(
            syntax_ok=False,
            syntax_detail=detail,
            skipped_pan=True,
            proved=False,
            claims=[],
        )
    claims = prove_file(pml, timeout=timeout)
    proved = bool(claims) and all(claim.proved for claim in claims)
    return SpinVerifyResult(
        syntax_ok=True,
        syntax_detail=detail,
        skipped_pan=False,
        proved=proved,
        claims=claims,
    )


def verify_text(promela_text: str, timeout: int = 120) -> SpinVerifyResult:
    _TMP_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="verify_", dir=str(_TMP_ROOT)) as tmp:
        path = Path(tmp) / "candidate.pml"
        path.write_text(promela_text, encoding="utf-8")
        return verify_path(path, timeout=timeout)


def verify_protocol(
    name: str,
    requirement: str = "precise",
    from_json: Optional[Path] = None,
    from_pml: Optional[Path] = None,
    timeout: int = 120,
) -> SpinVerifyResult:
    if from_pml is not None:
        return verify_path(from_pml, timeout=timeout)
    path = from_json or (ROOT / "results" / "formalize" / f"{name}_{requirement}.json")
    if not path.is_file():
        raise FileNotFoundError(
            f"No formalization at {path}. Run: python -m semanticdrift formalize "
            f"--name {name} --requirement {requirement}"
        )
    artifact = load_formalization(path)
    return verify_text(artifact.as_promela(), timeout=timeout)
