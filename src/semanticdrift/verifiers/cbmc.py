"""CBMC as an unmodified subprocess (methodology §8.5)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from semanticdrift.verifiers.common import (
    ToolVerifyResult,
    combined_output,
    run_cmd,
    which_tool,
)


def verify_c(path: Path, unwind: int = 10, timeout: int = 120) -> ToolVerifyResult:
    cbmc = which_tool("cbmc")
    if not cbmc:
        return ToolVerifyResult("cbmc", False, True, None, "cbmc is not on PATH")
    src = str(path.resolve())
    try:
        parsed = run_cmd([cbmc, src, "--show-parse-tree"], timeout=timeout)
    except subprocess.TimeoutExpired:
        return ToolVerifyResult("cbmc", False, True, None, f"cbmc parse timed out after {timeout}s")
    parse_out = combined_output(parsed)
    if parsed.returncode != 0 or _parse_failed(parse_out):
        return ToolVerifyResult(
            "cbmc", False, True, None, _last_line(parse_out) or "cbmc parse failed", parse_out
        )
    try:
        checked = run_cmd(
            [cbmc, src, "--unwind", str(unwind), "--no-unwinding-assertions"],
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return ToolVerifyResult("cbmc", True, False, None, f"cbmc timed out after {timeout}s")
    out = combined_output(checked)
    if "VERIFICATION SUCCESSFUL" in out:
        return ToolVerifyResult("cbmc", True, False, True, "VERIFICATION SUCCESSFUL", out)
    if "VERIFICATION FAILED" in out:
        return ToolVerifyResult("cbmc", True, False, False, "VERIFICATION FAILED", out)
    return ToolVerifyResult("cbmc", True, False, None, _last_line(out) or "cbmc finished without a verdict", out)


def _parse_failed(output: str) -> bool:
    lowered = output.lower()
    return "parsing error" in lowered or "conversion error" in lowered or "failed to parse" in lowered


def _last_line(output: str) -> str:
    lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
    return lines[-1] if lines else ""
