"""SPIN syntax check and pan proofs for gold Promela models."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

_LTL = re.compile(r"ltl\s+(\w+)\s*\{([^}]+)\}", re.S)
_ERRORS = re.compile(r"errors:\s*(\d+)")
_TMP_ROOT = Path(__file__).resolve().parents[2] / "tmp"


@dataclass(frozen=True)
class ClaimProof:
    name: str
    formula: str
    proved: bool
    fairness: bool
    errors: Optional[int]
    detail: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "formula": self.formula,
            "proved": self.proved,
            "fairness": self.fairness,
            "errors": self.errors,
            "detail": self.detail,
        }


def list_claims(pml: Path) -> List[Tuple[str, str]]:
    text = pml.read_text(encoding="utf-8")
    return [(name, " ".join(body.split())) for name, body in _LTL.findall(text)]


def needs_weak_fairness(formula: str) -> bool:
    """Liveness (`<>`) needs SPIN's weak-fairness flag; safety does not."""
    return "<>" in formula


def check_syntax(pml: Path, spin_bin: Optional[str] = None) -> Tuple[bool, str]:
    spin = spin_bin or shutil.which("spin")
    if not spin:
        return False, "SPIN is not on PATH"
    with tempfile.TemporaryDirectory(dir=_ensure_tmp()) as tmp:
        result = subprocess.run(
            [spin, "-a", str(pml.resolve())],
            cwd=tmp,
            capture_output=True,
            text=True,
        )
    detail = (result.stderr or result.stdout).strip()
    if result.returncode == 0:
        return True, detail or "ok"
    return False, detail or "spin -a failed"


def check_syntax_text(promela_text: str, spin_bin: Optional[str] = None) -> Tuple[bool, str]:
    with tempfile.TemporaryDirectory(prefix="spin_", dir=_ensure_tmp()) as tmp:
        path = Path(tmp) / "candidate.pml"
        path.write_text(promela_text, encoding="utf-8")
        return check_syntax(path, spin_bin=spin_bin)


def prove_file(
    pml: Path,
    spin_bin: Optional[str] = None,
    cc_bin: Optional[str] = None,
    timeout: int = 60,
) -> List[ClaimProof]:
    """Compile pan once and check every inline `ltl` claim."""
    spin = spin_bin or shutil.which("spin")
    cc = cc_bin or shutil.which("cc") or shutil.which("gcc")
    claims = list_claims(pml)
    if not spin:
        return [
            ClaimProof(name, formula, False, needs_weak_fairness(formula), None, "SPIN is not on PATH")
            for name, formula in claims
        ]
    if not cc:
        return [
            ClaimProof(name, formula, False, needs_weak_fairness(formula), None, "cc/gcc is not on PATH")
            for name, formula in claims
        ]
    if not claims:
        return [
            ClaimProof("-", "", False, False, None, "no ltl claims in file")
        ]

    with tempfile.TemporaryDirectory(prefix="pan_", dir=_ensure_tmp()) as tmp:
        tmp_path = Path(tmp)
        generated = subprocess.run(
            [spin, "-a", str(pml.resolve())],
            cwd=tmp,
            capture_output=True,
            text=True,
        )
        if generated.returncode != 0:
            detail = (generated.stderr or generated.stdout).strip() or "spin -a failed"
            return [
                ClaimProof(name, formula, False, needs_weak_fairness(formula), None, detail)
                for name, formula in claims
            ]
        compiled = subprocess.run(
            [cc, "-o", "pan", "pan.c"],
            cwd=tmp,
            capture_output=True,
            text=True,
        )
        if compiled.returncode != 0:
            detail = (compiled.stderr or compiled.stdout).strip() or "cc pan.c failed"
            return [
                ClaimProof(name, formula, False, needs_weak_fairness(formula), None, detail)
                for name, formula in claims
            ]
        pan = tmp_path / "pan"
        return [
            _run_claim(pan, name, formula, timeout=timeout, cwd=tmp)
            for name, formula in claims
        ]


def _run_claim(
    pan: Path,
    name: str,
    formula: str,
    timeout: int,
    cwd: str,
) -> ClaimProof:
    fairness = needs_weak_fairness(formula)
    cmd: List[str] = [str(pan), "-a", "-N", name, "-m100000", "-n"]
    if fairness:
        cmd.append("-f")
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return ClaimProof(name, formula, False, fairness, None, f"pan timed out after {timeout}s")
    output = (result.stdout or "") + (result.stderr or "")
    match = _ERRORS.search(output)
    errors = int(match.group(1)) if match else None
    summary = _summary_line(output)
    proved = errors == 0
    return ClaimProof(name, formula, proved, fairness, errors, summary)


def _summary_line(output: str) -> str:
    for line in output.splitlines():
        if "errors:" in line:
            return line.strip()
    return output.strip().splitlines()[-1] if output.strip() else "no pan output"


def _ensure_tmp() -> str:
    _TMP_ROOT.mkdir(parents=True, exist_ok=True)
    return str(_TMP_ROOT)
