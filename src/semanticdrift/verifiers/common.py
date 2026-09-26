"""Shared result type for unmodified verifier wrappers."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ToolVerifyResult:
    tool: str
    syntax_ok: bool
    skipped_solver: bool
    proved: Optional[bool]
    detail: str
    raw: str = ""

    def to_dict(self) -> dict:
        return {
            "tool": self.tool,
            "syntax_ok": self.syntax_ok,
            "skipped_solver": self.skipped_solver,
            "proved": self.proved,
            "detail": self.detail,
        }


def which_tool(*names: str) -> Optional[str]:
    for name in names:
        path = shutil.which(name)
        if path:
            return path
    return None


def run_cmd(cmd: List[str], timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def combined_output(result: subprocess.CompletedProcess) -> str:
    return ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
