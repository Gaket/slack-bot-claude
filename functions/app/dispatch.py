import threading
from collections.abc import Callable
from typing import Protocol


class Dispatcher(Protocol):
    def dispatch(self, fn: Callable[[], None]) -> None: ...


class ThreadDispatcher:
    """Runs work on a daemon thread so handlers can ack Slack within its 3s deadline.

    Relies on min_instances=1 and the long function timeout to keep the Cloud Run
    instance (and its CPU) alive while the thread streams the agent response.
    """

    def dispatch(self, fn: Callable[[], None]) -> None:
        threading.Thread(target=fn, daemon=True).start()


class InlineDispatcher:
    """Synchronous dispatcher for tests."""

    def dispatch(self, fn: Callable[[], None]) -> None:
        fn()
