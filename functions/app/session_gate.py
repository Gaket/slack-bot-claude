import threading
from typing import Protocol


class SessionGate(Protocol):
    """Guarantees at most one relay loop streams a given agent session at a time."""

    def enter(self, session_id: str) -> bool: ...

    def finish(self, session_id: str) -> bool: ...

    def release(self, session_id: str) -> None: ...


class InMemorySessionGate:
    """Serializes relay loops per session within a process.

    The Anthropic session event stream is a live tail: every open stream for a
    session receives every event appended from that point on (it does NOT replay
    history). So when a user replies in a thread while the agent is still
    answering the previous turn, opening a *second* stream makes BOTH relay loops
    post every subsequent message — the duplicate-replies bug. This gate ensures
    only one relay loop ever streams a session: a reply that lands mid-run is
    forwarded to the session (the already-open tail relays its response) instead
    of starting a second loop.

    Process-local by design: the relay loop runs in-process on the instance that
    owns the stream, so coordinating in memory is sufficient as long as a
    session's traffic stays on one instance (min_instances=1, low volume).
    Cross-instance duplication would need a shared lock — out of scope here.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._streaming: set[str] = set()
        self._pending: set[str] = set()

    def enter(self, session_id: str) -> bool:
        """Claim the streamer role for this session.

        True  => caller owns the stream; it must relay, then call finish().
        False => a relay is already active and will pick up the just-sent
                 message via its open tail; caller must NOT open a stream.
        """
        with self._lock:
            if session_id in self._streaming:
                self._pending.add(session_id)
                return False
            self._streaming.add(session_id)
            return True

    def finish(self, session_id: str) -> bool:
        """Called by the streamer when a relay round ends (session went idle).

        True  => a reply arrived in the narrow window as this round was ending;
                 relay one more round so its response isn't dropped.
        False => nothing pending, session fully released.
        """
        with self._lock:
            if session_id in self._pending:
                self._pending.discard(session_id)
                return True
            self._streaming.discard(session_id)
            return False

    def release(self, session_id: str) -> None:
        """Hard release after a stream error so the session isn't left wedged."""
        with self._lock:
            self._streaming.discard(session_id)
            self._pending.discard(session_id)
