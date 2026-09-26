"""Pick SPIN / NuSMV / CBMC / Dafny from the file suffix. Tools stay unmodified."""

from __future__ import annotations

from pathlib import Path

from semanticdrift.verifiers.cbmc import verify_c
from semanticdrift.verifiers.dafny import verify_dfy
from semanticdrift.verifiers.nusmv import verify_smv
from semanticdrift.verifiers.spin import verify_path


def verify_file(path: Path, timeout: int = 120):
    suffix = path.suffix.lower()
    if suffix == ".pml":
        return verify_path(path, timeout=timeout)
    if suffix == ".c":
        return verify_c(path, timeout=timeout)
    if suffix in {".smv", ".nusmv"}:
        return verify_smv(path, timeout=timeout)
    if suffix == ".dfy":
        return verify_dfy(path, timeout=timeout)
    raise ValueError(f"No unmodified wrapper for {suffix!r} ({path})")
