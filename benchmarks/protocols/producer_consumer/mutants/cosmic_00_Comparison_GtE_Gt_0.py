"""Bounded producer-consumer. A producer waits when the buffer is full."""

from __future__ import annotations

import threading
from typing import Callable, List, Optional

EVENT_SINK: Optional[Callable[[str], None]] = None
CAPACITY = 4


def _emit(event: str) -> None:
    if EVENT_SINK is not None:
        EVENT_SINK(event)


class BoundedBuffer:
    def __init__(self, capacity: int = CAPACITY) -> None:
        self.capacity = capacity
        self.items: List[int] = []
        self.cv = threading.Condition()

    def put(self, item: int) -> None:
        with self.cv:
            while len(self.items) > self.capacity:
                self.cv.wait()
            self.items.append(item)
            if len(self.items) > self.capacity:
                raise AssertionError("buffer overflow")
            _emit(f"produce:{item}:size={len(self.items)}")
            self.cv.notify_all()

    def get(self) -> int:
        with self.cv:
            while not self.items:
                self.cv.wait()
            item = self.items.pop(0)
            _emit(f"consume:{item}:size={len(self.items)}")
            self.cv.notify_all()
            return item


def run(n_items: int = 16) -> List[str]:
    events: List[str] = []
    buf = BoundedBuffer()
    global EVENT_SINK
    EVENT_SINK = events.append

    def producer() -> None:
        for i in range(n_items):
            buf.put(i)

    def consumer() -> None:
        for _ in range(n_items):
            buf.get()

    threads = [threading.Thread(target=producer), threading.Thread(target=consumer)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        if thread.is_alive():
            raise RuntimeError("producer-consumer run timed out (possible deadlock)")
    EVENT_SINK = None
    return events
