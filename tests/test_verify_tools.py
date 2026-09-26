"""Week 4: unmodified CBMC / NuSMV / Dafny wrappers."""

import shutil
from pathlib import Path

import pytest

from semanticdrift.verifiers.cbmc import verify_c
from semanticdrift.verifiers.dafny import verify_dfy
from semanticdrift.verifiers.dispatch import verify_file
from semanticdrift.verifiers.nusmv import verify_smv

CBMC_OK = """
int main(void) {
  int x = 0;
  __CPROVER_assert(x == 0, "zero");
  return 0;
}
"""

CBMC_BAD = """
int main(void) {
  int x = 0;
  __CPROVER_assert(x == 1, "should fail");
  return 0;
}
"""

CBMC_JUNK = "int main( { }\n"

SMV_OK = """
MODULE main
VAR x : boolean;
LTLSPEC G (x | !x)
"""

SMV_JUNK = "MODULE\nVAR\n"

DFY_OK = """
method M() {
  assert 1 == 1;
}
"""

DFY_JUNK = "method M() { assert\n"


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_cbmc_success_and_junk(tmp_path: Path):
    if not shutil.which("cbmc"):
        pytest.skip("cbmc not on PATH")
    ok = verify_c(_write(tmp_path, "ok.c", CBMC_OK))
    assert ok.syntax_ok is True
    assert ok.skipped_solver is False
    assert ok.proved is True
    bad = verify_c(_write(tmp_path, "bad.c", CBMC_BAD))
    assert bad.syntax_ok is True
    assert bad.proved is False
    junk = verify_c(_write(tmp_path, "junk.c", CBMC_JUNK))
    assert junk.syntax_ok is False
    assert junk.skipped_solver is True


def test_nusmv_success_and_junk(tmp_path: Path):
    if not shutil.which("NuSMV") and not shutil.which("nusmv"):
        pytest.skip("NuSMV not on PATH")
    ok = verify_smv(_write(tmp_path, "ok.smv", SMV_OK))
    assert ok.syntax_ok is True
    assert ok.proved is True
    junk = verify_smv(_write(tmp_path, "junk.smv", SMV_JUNK))
    assert junk.syntax_ok is False
    assert junk.skipped_solver is True


def test_dafny_success_and_junk(tmp_path: Path):
    if not shutil.which("dafny"):
        pytest.skip("dafny not on PATH")
    ok = verify_dfy(_write(tmp_path, "ok.dfy", DFY_OK))
    assert ok.syntax_ok is True
    assert ok.proved is True
    junk = verify_dfy(_write(tmp_path, "junk.dfy", DFY_JUNK))
    assert junk.syntax_ok is False
    assert junk.skipped_solver is True


def test_dispatch_picks_suffix(tmp_path: Path):
    path = _write(tmp_path, "ok.smv", SMV_OK)
    if not shutil.which("NuSMV") and not shutil.which("nusmv"):
        pytest.skip("NuSMV not on PATH")
    result = verify_file(path)
    assert result.to_dict()["tool"] == "nusmv"
