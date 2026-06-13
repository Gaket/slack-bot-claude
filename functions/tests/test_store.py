from app.store import InMemoryEventDeduper, InMemorySessionStore


def test_session_store_roundtrip():
    store = InMemorySessionStore()
    assert store.get("C1:100.1") is None
    store.set("C1:100.1", "sesn_a")
    assert store.get("C1:100.1") == "sesn_a"


def test_session_store_overwrites():
    store = InMemorySessionStore()
    store.set("k", "sesn_a")
    store.set("k", "sesn_b")
    assert store.get("k") == "sesn_b"


def test_deduper_claims_once():
    deduper = InMemoryEventDeduper()
    assert deduper.claim("Ev1") is True
    assert deduper.claim("Ev1") is False


def test_deduper_independent_ids():
    deduper = InMemoryEventDeduper()
    assert deduper.claim("Ev1") is True
    assert deduper.claim("Ev2") is True
