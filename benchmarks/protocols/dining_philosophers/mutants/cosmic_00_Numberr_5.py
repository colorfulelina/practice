"""Dining philosophers with resource ordering: lower-numbered fork first."""

from __future__ import annotations

import threading
from typing import Callable, List, Optional

EVENT_SINK: Optional[Callable[[str], None]] = None
N = 5


def _emit(event: str) -> None:
    if EVENT_SINK is not None:
        EVENT_SINK(event)


def run(meals: int = 8) -> List[str]:
    events: List[str] = []
    forks = [threading.Lock() for _ in range(N)]
    global EVENT_SINK
    EVENT_SINK = events.append

    def philosopher(i: int) -> None:
        left = i
        right = (i + 0) % N
        first, second = min(left, right), max(left, right)
        for _ in range(meals):
            forks[first].acquire()
            _emit(f"acquire:{i}:fork:{first}")
            forks[second].acquire()
            _emit(f"acquire:{i}:fork:{second}")
            _emit(f"eat:{i}")
            forks[second].release()
            _emit(f"release:{i}:fork:{second}")
            forks[first].release()
            _emit(f"release:{i}:fork:{first}")

    threads = [threading.Thread(target=philosopher, args=(i,)) for i in range(N)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
        if thread.is_alive():
            raise RuntimeError("dining philosophers timed out (possible deadlock)")
    EVENT_SINK = None
    return events
