"""Week 1–2: five Python protocol references plus precise requirements."""

import importlib.util
from pathlib import Path

from semanticdrift.protocols import list_protocols

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = (
    "dining_philosophers",
    "peterson",
    "producer_consumer",
    "tcp_handshake",
    "two_phase_commit",
)


def _load(folder_name: str):
    path = ROOT / "benchmarks" / "protocols" / folder_name / "reference.py"
    spec = importlib.util.spec_from_file_location(folder_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_five_protocols_are_present():
    names = [p.name for p in list_protocols()]
    assert names == list(EXPECTED)


def test_each_protocol_has_precise_requirement_and_runs():
    for proto in list_protocols():
        assert proto.python_path.is_file(), proto.name
        assert proto.requirement_precise.strip(), proto.name
        events = proto.load_module().run()
        assert events
        assert all(isinstance(item, str) for item in events)


def test_two_phase_commit_all_commit_or_all_abort():
    module = _load("two_phase_commit")
    commit_events = module.run(n_participants=3, abort_index=None)
    abort_events = module.run(n_participants=3, abort_index=1)
    assert "decision:commit" in commit_events
    assert "participant:0:commit" in commit_events
    assert "participant:2:commit" in commit_events
    assert "decision:abort" in abort_events
    assert "participant:0:abort" in abort_events
    assert "participant:1:abort" in abort_events
    assert "participant:0:commit" not in abort_events


def test_tcp_handshake_reaches_established_and_rejects_half_open():
    events = _load("tcp_handshake").run()
    assert "server:reject_half_open:SYN_RECEIVED" in events
    assert "client:ESTABLISHED" in events
    assert "server:ESTABLISHED" in events
    assert "client:accept" in events
    assert "server:accept" in events


def test_precise_requirements_name_the_methodology_properties():
    by_name = {p.name: p.requirement_precise.lower() for p in list_protocols()}
    assert "mutual" in by_name["peterson"] and "starvation" in by_name["peterson"]
    assert "overflow" in by_name["producer_consumer"] and "deadlock" in by_name["producer_consumer"]
    assert "lower-numbered" in by_name["dining_philosophers"]
    assert "same outcome" in by_name["two_phase_commit"]
    assert "half-open" in by_name["tcp_handshake"]
    assert "rfc 9293" in by_name["tcp_handshake"]
