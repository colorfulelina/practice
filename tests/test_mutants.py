"""Week 3: Cosmic Ray protocol mutants and the pycparser C mutator."""

import json
from pathlib import Path

from semanticdrift.mutants.c_mutator import apply_site, collect_sites, seed_one_mutant
from semanticdrift.protocols import ROOT, list_protocols

PROTO_MUTANTS = ROOT / "benchmarks" / "protocols"
C_MUTANTS = ROOT / "benchmarks" / "sv-sample" / "mutants"


SNIPPET = """
int main() {
  int n = 8;
  int i;
  int sn = 0;
  for (i = 1; i <= n; i++) {
    if (i < 4)
      sn = sn + 1;
  }
  if (sn == n)
    return 0;
  return 1;
}
"""


def test_token_fallback_does_not_treat_arrow_as_greater_than():
    from semanticdrift.mutants.c_mutator import collect_token_sites

    sites = collect_token_sites("  q->element[q->tail] = x;\n")
    assert not any(site.old == ">" for site in sites)


def test_c_mutator_finds_boundary_comparison_and_off_by_one():
    kinds = {site.kind for site in collect_sites(SNIPPET)}
    assert "boundary" in kinds
    assert "comparison" in kinds
    assert "off_by_one" in kinds


def test_c_mutator_rewrites_exactly_one_token():
    import random

    mutated, site, engine = seed_one_mutant(SNIPPET, random.Random(7))
    assert engine in {"pycparser", "token-fallback"}
    assert mutated != SNIPPET
    assert site.old in SNIPPET
    assert site.new in mutated
    assert SNIPPET.count("\n") == mutated.count("\n")
    # Re-applying the recorded site reproduces the mutant.
    assert apply_site(SNIPPET, site) == mutated


def test_each_protocol_has_cosmic_ray_mutants():
    for proto in list_protocols():
        manifest_path = proto.python_path.parent / "mutants" / "manifest.json"
        assert manifest_path.is_file(), f"missing {manifest_path}; run python -m semanticdrift seed-mutants"
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert all(m.get("engine") == "cosmic-ray" for m in data["mutants"])
        assert data["mutants"], proto.name
        for item in data["mutants"]:
            path = proto.python_path.parent / "mutants" / item["file"]
            assert path.is_file(), path
            assert path.read_text(encoding="utf-8") != proto.python_path.read_text(encoding="utf-8")
            assert item["test_outcome"] in {"killed", "survived"}


def test_c_mutants_and_spot_check_exist():
    manifest_path = C_MUTANTS / "manifest.json"
    spot_path = C_MUTANTS / "spot_check.json"
    if not (ROOT / "sv-benchmarks").is_dir() and not manifest_path.is_file():
        return
    assert manifest_path.is_file(), "run: python -m semanticdrift seed-mutants"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["n_mutants"] >= 30
    assert data["seed"] == 7
    for item in data["mutants"][:10]:
        assert (C_MUTANTS / item["file"]).is_file()
        assert item["operator"] in {"boundary", "comparison", "off_by_one"}
        assert item["original_expected"] is True

    assert spot_path.is_file()
    spot = json.loads(spot_path.read_text(encoding="utf-8"))
    assert spot["n_reviewed"] == 30
    labeled = [r for r in spot["reviews"] if r.get("plausible") in {"yes", "no"}]
    assert len(labeled) == 30, "spot-check 30 C mutants before treating Component B as done"
