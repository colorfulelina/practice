"""NuSMV as an unmodified subprocess (methodology §8.5)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from semanticdrift.verifiers.common import (
    ToolVerifyResult,
    combined_output,
    run_cmd,
    which_tool,
)


def verify_smv(path: Path, timeout: int = 120) -> ToolVerifyResult:
    nusmv = which_tool("NuSMV", "nusmv")
    if not nusmv:
        return ToolVerifyResult("nusmv", False, True, None, "NuSMV is not on PATH")
    src = str(path.resolve())
    try:
        result = run_cmd([nusmv, src], timeout=timeout)
    except subprocess.TimeoutExpired:
        return ToolVerifyResult("nusmv", False, True, None, f"NuSMV timed out after {timeout}s")
    out = combined_output(result)
    if _parse_failed(out) or result.returncode != 0 and "is true" not in out and "is false" not in out:
        return ToolVerifyResult(
            "nusmv", False, True, None, _last_line(out) or "NuSMV parse/typecheck failed", out
        )
    if "is false" in out:
        return ToolVerifyResult("nusmv", True, False, False, _spec_line(out, "is false"), out)
    if "is true" in out:
        return ToolVerifyResult("nusmv", True, False, True, _spec_line(out, "is true"), out)
    return ToolVerifyResult("nusmv", True, False, None, _last_line(out) or "NuSMV finished without a spec verdict", out)


def _parse_failed(output: str) -> bool:
    lowered = output.lower()
    return "parse error" in lowered or "syntax error" in lowered or "undefined" in lowered


def _spec_line(output: str, needle: str) -> str:
    for line in output.splitlines():
        if needle in line:
            return line.strip()
    return needle


def _last_line(output: str) -> str:
    lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
    return lines[-1] if lines else ""
