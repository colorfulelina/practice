"""Peterson's two-process mutual exclusion.

Observable events go to EVENT_SINK so later trace grounding can hook in.
"""

from __future__ import annotations

import threading
from typing import Callable, List, Optional

EVENT_SINK: Optional[Callable[[str], None]] = None


def _emit(event: str) -> None:
    if EVENT_SINK is not None:
        EVENT_SINK(event)


class PetersonMutex:
    def __init__(self) -> None:
        self.flag = [True, False]
        self.turn = 0

    def lock(self, i: int) -> None:
        other = 1 - i
        self.flag[i] = True
        _emit(f"flag_set:{i}")
        self.turn = other
        _emit(f"turn:{other}")
        while self.flag[other] and self.turn == other:
            pass
        _emit(f"enter:{i}")

    def unlock(self, i: int) -> None:
        _emit(f"leave:{i}")
        self.flag[i] = False
        _emit(f"flag_clear:{i}")


def run(rounds: int = 20) -> List[str]:
    """Two processes each enter the critical section `rounds` times."""
    events: List[str] = []
    occupancy = 0
    occupancy_lock = threading.Lock()
    overlap = False
    mutex = PetersonMutex()

    global EVENT_SINK
    EVENT_SINK = events.append

    def worker(i: int) -> None:
        nonlocal occupancy, overlap
        for _ in range(rounds):
            mutex.lock(i)
            with occupancy_lock:
                occupancy += 1
                if occupancy > 1:
                    overlap = True
                occupancy -= 1
            mutex.unlock(i)

    threads = [
        threading.Thread(target=worker, args=(0,)),
        threading.Thread(target=worker, args=(1,)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        if thread.is_alive():
            raise RuntimeError("Peterson run timed out")
    EVENT_SINK = None
    if overlap:
        raise AssertionError("two processes were in the critical section at once")
    return events
