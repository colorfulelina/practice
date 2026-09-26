"""Dafny as an unmodified subprocess (methodology §8.5)."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from semanticdrift.verifiers.common import (
    ToolVerifyResult,
    combined_output,
    run_cmd,
    which_tool,
)

_FINISHED = re.compile(
    r"Dafny program verifier finished with\s+(\d+)\s+verified,\s+(\d+)\s+error",
    re.I,
)


def verify_dfy(path: Path, timeout: int = 120) -> ToolVerifyResult:
    dafny = which_tool("dafny")
    if not dafny:
        return ToolVerifyResult("dafny", False, True, None, "dafny is not on PATH")
    src = str(path.resolve())
    try:
        resolved = run_cmd([dafny, "resolve", src], timeout=timeout)
    except subprocess.TimeoutExpired:
        return ToolVerifyResult("dafny", False, True, None, f"dafny resolve timed out after {timeout}s")
    resolve_out = combined_output(resolved)
    if resolved.returncode != 0 or _resolve_failed(resolve_out):
        return ToolVerifyResult(
            "dafny", False, True, None, _last_line(resolve_out) or "dafny resolve failed", resolve_out
        )
    try:
        checked = run_cmd([dafny, "verify", src], timeout=timeout)
    except subprocess.TimeoutExpired:
        return ToolVerifyResult("dafny", True, False, None, f"dafny verify timed out after {timeout}s")
    out = combined_output(checked)
    match = _FINISHED.search(out)
    if match:
        errors = int(match.group(2))
        return ToolVerifyResult("dafny", True, False, errors == 0, match.group(0), out)
    if checked.returncode == 0:
        return ToolVerifyResult("dafny", True, False, True, _last_line(out) or "dafny verify ok", out)
    return ToolVerifyResult("dafny", True, False, False, _last_line(out) or "dafny verify failed", out)


def _resolve_failed(output: str) -> bool:
    lowered = output.lower()
    return "parse error" in lowered or "resolution error" in lowered or "error:" in lowered


def _last_line(output: str) -> str:
    lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
    return lines[-1] if lines else ""
