"""Gold Promela models parse and prove with SPIN (week 3)."""

import shutil

import pytest

from semanticdrift.promela import check_syntax, prove_file
from semanticdrift.protocols import list_protocols


def test_each_protocol_has_promela():
    for proto in list_protocols():
        assert proto.promela_path.is_file(), proto.name
        text = proto.promela_path.read_text(encoding="utf-8")
        assert "ltl " in text, proto.name


def test_spin_accepts_each_reference_model():
    for proto in list_protocols():
        ok, detail = check_syntax(proto.promela_path)
        assert ok, f"{proto.name}: {detail}"


def test_pan_proves_each_gold_claim():
    if not shutil.which("spin") or not (shutil.which("cc") or shutil.which("gcc")):
        pytest.skip("spin and a C compiler are required to prove Promela")
    for proto in list_protocols():
        results = prove_file(proto.promela_path)
        assert results, proto.name
        failed = [r for r in results if not r.proved]
        assert not failed, (
            f"{proto.name}: "
            + "; ".join(f"{r.name} ({r.detail})" for r in failed)
        )
