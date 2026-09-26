"""Worked Promela examples translated from well-known TLA+ Examples.

These are not the five gold protocol models. Few-shot uses the first three.
Retrieval searches the whole list.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class WorkedExample:
    example_id: str
    title: str
    requirement: str
    model: str


# TLA+ Examples: DieHard, OneBitClock, AlternatingBit (short Promela).
CORPUS: List[WorkedExample] = [
    WorkedExample(
        example_id="diehard",
        title="DieHard water jugs",
        requirement=(
            "A 3-gallon jug and a 5-gallon jug start empty. You may fill a jug "
            "from the lake, empty a jug, or pour from one jug into the other "
            "until the source is empty or the destination is full. Reach a "
            "state where the 5-gallon jug holds exactly 4 gallons."
        ),
        model="""byte small = 0;
byte big = 0;
inline fill_small() { small = 3 }
inline fill_big() { big = 5 }
inline empty_small() { small = 0 }
inline empty_big() { big = 0 }
proctype pour() {
  do
  :: small < 3 -> fill_small()
  :: big < 5 -> fill_big()
  :: small > 0 -> empty_small()
  :: big > 0 -> empty_big()
  :: small > 0 && big < 5 ->
       if
       :: small + big <= 5 -> big = small + big; small = 0
       :: else -> small = small - (5 - big); big = 5
       fi
  od
}
init { run pour() }
ltl reach4 { <> (big == 4) }
""",
    ),
    WorkedExample(
        example_id="onebitclock",
        title="One-bit clock",
        requirement=(
            "A clock bit flips between 0 and 1. From 0 it must eventually become 1, "
            "and from 1 it must eventually become 0. The bit is never both 0 and 1."
        ),
        model="""bool bit = 0;
active proctype clock() {
  do
  :: bit == 0 -> bit = 1
  :: bit == 1 -> bit = 0
  od
}
ltl tick { [] ((bit == 0) -> <> (bit == 1)) }
ltl tock { [] ((bit == 1) -> <> (bit == 0)) }
""",
    ),
    WorkedExample(
        example_id="alternating_bit",
        title="Alternating-bit channel",
        requirement=(
            "A sender transmits a bit over an unreliable channel and waits for an "
            "acknowledgement with the same bit. After an ack, the sender flips the "
            "bit. The receiver delivers a message only when the incoming bit is new."
        ),
        model="""chan data = [1] of { bit };
chan ack = [1] of { bit };
bit sbit = 0;
bit rbit = 1;
active proctype sender() {
  do
  :: data!sbit -> ack?eval(sbit); sbit = 1 - sbit
  od
}
active proctype receiver() {
  bit b;
  do
  :: data?b ->
       if
       :: b != rbit -> rbit = b
       :: else -> skip
       fi;
       ack!b
  od
}
ltl flip { [] <> (sbit == 0) && [] <> (sbit == 1) }
""",
    ),
    WorkedExample(
        example_id="traffic",
        title="Two-light traffic controller",
        requirement=(
            "Two traffic lights share an intersection. At most one light is green. "
            "If a light is red, it eventually becomes green under a fair scheduler."
        ),
        model="""mtype = { red, green };
mtype ns = red;
mtype ew = red;
active proctype controller() {
  do
  :: ns == red && ew == red -> ns = green
  :: ns == green -> ns = red; ew = green
  :: ew == green -> ew = red
  od
}
ltl mutex { [] !(ns == green && ew == green) }
""",
    ),
    WorkedExample(
        example_id="bounded_counter",
        title="Bounded counter",
        requirement=(
            "A counter starts at 0 and may increment or decrement by one. It must "
            "never go below 0 or above a fixed bound N."
        ),
        model="""#define N 3
byte count = 0;
active proctype ctr() {
  do
  :: count < N -> count++
  :: count > 0 -> count--
  od
}
ltl bounds { [] (count >= 0 && count <= N) }
""",
    ),
]


FEW_SHOT = CORPUS[:3]


def render_example(example: WorkedExample) -> str:
    return (
        f"Example — {example.title}:\n"
        f"Requirement: {example.requirement}\n"
        f"Promela:\n{example.model.strip()}\n"
    )


def few_shot_prefix() -> str:
    blocks = [render_example(item) for item in FEW_SHOT]
    return (
        "WORKED EXAMPLES (from TLA+ Examples, translated to Promela; "
        "not the task below):\n\n" + "\n".join(blocks)
    )
