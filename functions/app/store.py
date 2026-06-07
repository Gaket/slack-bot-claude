from datetime import datetime, timezone
from typing import Protocol

from google.api_core.exceptions import AlreadyExists


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
        try:
            # processed_at enables a Firestore TTL policy to expire old claims.
            self._db.collection(self.COLLECTION).document(event_id).create(
                {"processed_at": datetime.now(timezone.utc)}
            )
            return True
        except AlreadyExists:
            return False
