from app.store import FirestoreSessionStore


# Minimal Firestore stand-in: just enough of document().get()/set(merge=) to prove
# session_id and last_seen_ts coexist on the same doc.
class _FakeDoc:
    def __init__(self):
        self.data = None

    @property
    def exists(self):
        return self.data is not None

    def to_dict(self):
        return dict(self.data or {})


class _FakeDocRef:
    def __init__(self, doc):
        self._doc = doc

    def get(self):
        return self._doc

    def set(self, data, merge=False):
        if merge and self._doc.data is not None:
            self._doc.data.update(data)
        else:
            self._doc.data = dict(data)


class _FakeCollection:
    def __init__(self):
        self.docs = {}

    def document(self, key):
        return _FakeDocRef(self.docs.setdefault(key, _FakeDoc()))


class FakeDb:
    def __init__(self):
        self.cols = {}

    def collection(self, name):
        return self.cols.setdefault(name, _FakeCollection())


def test_set_then_set_watermark_preserves_both():
    store = FirestoreSessionStore(FakeDb())
    store.set("k", "sesn_1")
    store.set_watermark("k", "100.0")
    assert store.get("k") == "sesn_1"
    assert store.get_watermark("k") == "100.0"


def test_set_watermark_then_set_preserves_both():
    store = FirestoreSessionStore(FakeDb())
    store.set_watermark("k", "100.0")
    store.set("k", "sesn_1")
    assert store.get("k") == "sesn_1"
    assert store.get_watermark("k") == "100.0"


def test_missing_keys_return_none():
    store = FirestoreSessionStore(FakeDb())
    assert store.get("nope") is None
    assert store.get_watermark("nope") is None
