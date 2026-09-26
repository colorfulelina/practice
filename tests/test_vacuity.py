"""Week 3: vacuity mutants and gold labels (Component E)."""

import json

from semanticdrift.vacuity import extract_promela_ltl, generate_vacuity_mutants
from semanticdrift.protocols import ROOT, list_protocols

BATTERY = ROOT / "benchmarks" / "vacuity" / "battery.json"
LABELS = ROOT / "benchmarks" / "vacuity" / "labels.json"


def test_peterson_starve_mutants():
    mutants = generate_vacuity_mutants("[] (flag0 -> <> inCS0)")
    assert mutants["antecedent_forced"] == "[] (true -> <> inCS0)"
    assert mutants["consequent_trivial"] == "[] (flag0 -> true)"
    assert mutants["eventually_to_true"] == "[] (flag0 -> <> true)"


def test_mutex_guard_mutant():
    mutants = generate_vacuity_mutants("[] !(inCS0 && inCS1)")
    assert mutants["guard_false"] == "[] ! (false && true)"


def test_svcomp_unreach_and_termination():
    assert generate_vacuity_mutants("G ! call(reach_error())")["guard_false"] == "G ! false"
    assert generate_vacuity_mutants("F end")["eventually_to_true"] == "F true"


def test_each_protocol_ltl_is_in_the_battery():
    data = json.loads(BATTERY.read_text(encoding="utf-8"))
    ids = {row["property_id"] for row in data["properties"]}
    for proto in list_protocols():
        for name, _formula in extract_promela_ltl(proto.promela_path.read_text(encoding="utf-8")):
            assert f"{proto.name}.{name}" in ids, proto.name


def test_about_sixty_vacuity_labels():
    battery = json.loads(BATTERY.read_text(encoding="utf-8"))
    labels = json.loads(LABELS.read_text(encoding="utf-8"))
    assert 60 <= labels["n_reviewed"] <= 70
    assert labels["n_vacuous"] + labels["n_not_vacuous"] == labels["n_reviewed"]
    labeled_ids = {row["id"] for row in labels["reviews"]}
    battery_ids = {row["id"] for row in battery["properties"]}
    assert labeled_ids == battery_ids
    for row in labels["reviews"]:
        assert row["vacuous"] in {"yes", "no"}
        assert row["note"].strip()
