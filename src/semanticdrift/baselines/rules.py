"""Keyword-to-Promela templates for the five hand-authored protocols (§8.8)."""

from __future__ import annotations

from semanticdrift.agents.formalize import Formalization, LTLProperty

TEMPLATES = {
    "peterson": Formalization(
        model="""bool flag0 = 0;
bool flag1 = 0;
byte turn = 0;
bool inCS0 = 0;
bool inCS1 = 0;
active proctype P0() {
  flag0 = 1; turn = 1;
  (flag1 == 0 || turn == 0);
  inCS0 = 1; inCS0 = 0; flag0 = 0
}
active proctype P1() {
  flag1 = 1; turn = 0;
  (flag0 == 0 || turn == 1);
  inCS1 = 1; inCS1 = 0; flag1 = 0
}
""",
        properties=[
            LTLProperty("mutex", "[] !(inCS0 && inCS1)"),
            LTLProperty("starve0", "[] (flag0 -> <> inCS0)"),
            LTLProperty("starve1", "[] (flag1 -> <> inCS1)"),
        ],
        assumptions=["two processes", "weakly fair scheduler"],
        traceability=[{"element": "mutex", "source": "keyword: critical section / mutex"}],
        generator_model="rule_based",
    ),
    "producer_consumer": Formalization(
        model="""#define N 2
byte count = 0;
active proctype producer() {
  do
  :: count < N -> count++
  od
}
active proctype consumer() {
  do
  :: count > 0 -> count--
  od
}
""",
        properties=[
            LTLProperty("no_overflow", "[] (count <= N)"),
            LTLProperty("no_underflow", "[] (count >= 0)"),
        ],
        assumptions=["one buffer", "capacity N is constant"],
        traceability=[{"element": "no_overflow", "source": "keyword: buffer / overflow"}],
        generator_model="rule_based",
    ),
    "dining_philosophers": Formalization(
        model="""bool fork0 = 1;
bool fork1 = 1;
bool fork2 = 1;
bool eating0 = 0;
active proctype phil0() {
  do
  :: fork0 -> fork0 = 0; fork1 = 0; eating0 = 1; eating0 = 0; fork0 = 1; fork1 = 1
  od
}
""",
        properties=[
            LTLProperty("deadlock_free", "[] <> (fork0 || fork1 || fork2)"),
        ],
        assumptions=["ordered fork acquisition"],
        traceability=[{"element": "deadlock_free", "source": "keyword: fork / philosopher"}],
        generator_model="rule_based",
    ),
    "two_phase_commit": Formalization(
        model="""mtype = { none, commit, abort };
mtype decision = none;
mtype p0 = none;
mtype p1 = none;
active proctype coordinator() {
  decision = commit;
  p0 = decision;
  p1 = decision
}
""",
        properties=[
            LTLProperty("atomicity", "[] (p0 == p1)"),
        ],
        assumptions=["messages delivered"],
        traceability=[{"element": "atomicity", "source": "keyword: commit / abort"}],
        generator_model="rule_based",
    ),
    "tcp_handshake": Formalization(
        model="""mtype = { closed, listen, syn_sent, syn_rcvd, established };
mtype client = closed;
mtype server = listen;
active proctype handshake() {
  client = syn_sent;
  server = syn_rcvd;
  client = established;
  server = established
}
""",
        properties=[
            LTLProperty("both_established", "[] (server == established -> client == established)"),
        ],
        assumptions=["in-order handshake segments"],
        traceability=[{"element": "both_established", "source": "keyword: syn / ack"}],
        generator_model="rule_based",
    ),
}

_HINTS = (
    ("peterson", ("peterson", "flag[", "turn", "critical section")),
    ("producer_consumer", ("bounded buffer", "producer", "consumer", "overflow")),
    ("dining_philosophers", ("philosopher", "fork", "dining")),
    ("two_phase_commit", ("two-phase", "vote-commit", "coordinator")),
    ("tcp_handshake", ("syn-ack", "syn_sent", "three-way", "rfc 9293")),
)


def rule_based_model(name: str, requirement_text: str = "") -> Formalization:
    key = name.strip().lower()
    if key in TEMPLATES:
        return TEMPLATES[key]
    blob = f"{name}\n{requirement_text}".lower()
    for protocol, hints in _HINTS:
        if any(hint in blob for hint in hints):
            return TEMPLATES[protocol]
    known = ", ".join(TEMPLATES)
    raise ValueError(f"rule-based baseline is only defined for: {known}")
