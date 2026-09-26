"""Week 4: SPIN verify wrapper. pan runs only after spin -a succeeds."""

import shutil

import pytest

from semanticdrift.promela import prove_file
from semanticdrift.protocols import get_protocol
from semanticdrift.verifiers.spin import verify_path, verify_text


GARBAGE = """
proctype Process(i) {
  mutex->lock(i);
}
"""


def test_syntax_error_skips_pan():
    result = verify_text(GARBAGE)
    assert result.syntax_ok is False
    assert result.skipped_pan is True
    assert result.proved is False
    assert result.claims == []


def test_gold_peterson_parses_and_pan_runs():
    if not shutil.which("spin") or not (shutil.which("cc") or shutil.which("gcc")):
        pytest.skip("spin and a C compiler are required")
    gold = get_protocol("peterson").promela_path
    result = verify_path(gold)
    assert result.syntax_ok is True
    assert result.skipped_pan is False
    assert result.proved is True
    names = {claim.name for claim in result.claims}
    assert names == {"mutex", "starve0", "starve1"}
    assert all(claim.proved for claim in result.claims)
    # Same backend as prove-promela.
    direct = prove_file(gold)
    assert [c.proved for c in direct] == [c.proved for c in result.claims]
