from typing import Protocol


class SessionStore(Protocol):
    """Maps a Slack conversation key (thread_ts or DM channel id) to an agent session id."""

    def get(self, key: str) -> str | None: ...

    def set(self, key: str, session_id: str) -> None: ...


class FirestoreSessionStore:
    COLLECTION = "thread_sessions"

    def __init__(self, db) -> None:
        self._db = db

    def get(self, key: str) -> str | None:
        doc = self._db.collection(self.COLLECTION).document(key).get()
        return doc.get("session_id") if doc.exists else None

    def set(self, key: str, session_id: str) -> None:
        self._db.collection(self.COLLECTION).document(key).set({"session_id": session_id})
