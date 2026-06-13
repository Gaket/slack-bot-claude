import threading
from datetime import datetime, timezone
from typing import Protocol


class SessionStore(Protocol):
    """Maps a Slack conversation key (thread_ts or DM channel id) to an agent session id."""

    def get(self, key: str) -> str | None: ...

    def set(self, key: str, session_id: str) -> None: ...


class EventDeduper(Protocol):
    """Claims a Slack event_id so each delivery is processed at most once."""

    def claim(self, event_id: str) -> bool: ...


class FirestoreSessionStore:
    COLLECTION = "thread_sessions"

    def __init__(self, db) -> None:
        self._db = db

    def get(self, key: str) -> str | None:
        doc = self._db.collection(self.COLLECTION).document(key).get()
        return doc.get("session_id") if doc.exists else None

    def set(self, key: str, session_id: str) -> None:
        self._db.collection(self.COLLECTION).document(key).set({"session_id": session_id})


class FirestoreEventDeduper:
    """Slack's Events API is at-least-once: it redelivers (immediately, +1min,
    +5min) whenever a response misses its 3s deadline, reusing the original
    event_id. create() is atomic and fails on an existing doc, so exactly one
    delivery wins the claim; retries and duplicates become no-ops.
    """

    COLLECTION = "processed_events"

    def __init__(self, db) -> None:
        self._db = db

    def claim(self, event_id: str) -> bool:
        # Imported lazily so non-Firestore entrypoints (Railway Socket Mode) never
        # need google-cloud libraries on their import path.
        from google.api_core.exceptions import AlreadyExists

        try:
            # processed_at enables a Firestore TTL policy to expire old claims.
            self._db.collection(self.COLLECTION).document(event_id).create(
                {"processed_at": datetime.now(timezone.utc)}
            )
            return True
        except AlreadyExists:
            return False


class InMemorySessionStore:
    """Process-local session map for the single long-lived Socket Mode instance
    (Railway). State resets on restart, matching the original socket-mode bot.
    """

    def __init__(self) -> None:
        self._data: dict[str, str] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> str | None:
        with self._lock:
            return self._data.get(key)

    def set(self, key: str, session_id: str) -> None:
        with self._lock:
            self._data[key] = session_id


class InMemoryEventDeduper:
    """Process-local at-most-once claim for Socket Mode, which also redelivers
    unacked events. Sufficient for a single instance; claims live for the
    process lifetime.
    """

    def __init__(self) -> None:
        self._claimed: set[str] = set()
        self._lock = threading.Lock()

    def claim(self, event_id: str) -> bool:
        with self._lock:
            if event_id in self._claimed:
                return False
            self._claimed.add(event_id)
            return True
