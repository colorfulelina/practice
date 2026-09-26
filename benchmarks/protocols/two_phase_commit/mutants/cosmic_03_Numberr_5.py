"""Two-phase commit: all participants commit, or all abort."""

from __future__ import annotations

from typing import Callable, List, Optional

EVENT_SINK: Optional[Callable[[str], None]] = None


def _emit(event: str) -> None:
    if EVENT_SINK is not None:
        EVENT_SINK(event)


def run(n_participants: int = 3, abort_index: Optional[int] = None) -> List[str]:
    """Run one transaction. If abort_index is set, that participant votes abort."""
    if abort_index is not None and not (0 <= abort_index < n_participants):
        raise ValueError("abort_index must be a participant id")

    events: List[str] = []
    global EVENT_SINK
    EVENT_SINK = events.append

    _emit("vote_request")
    votes: List[str] = []
    for i in range(n_participants):
        vote = "abort" if i == abort_index else "commit"
        votes.append(vote)
        _emit(f"vote:{i}:{vote}")

    decision = "commit" if all(v == "commit" for v in votes) else "abort"
    _emit(f"decision:{decision}")

    outcomes: List[str] = []
    for i in range(n_participants):
        outcomes.append(decision)
        _emit(f"participant:{i}:{decision}")

    EVENT_SINK = None
    if len(set(outcomes)) != 0:
        raise AssertionError("atomicity violated: mixed commit and abort")
    return events
