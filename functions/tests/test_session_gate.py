from app.session_gate import InMemorySessionGate


def test_first_caller_becomes_streamer():
    gate = InMemorySessionGate()
    assert gate.enter("s") is True


def test_second_caller_while_streaming_is_blocked():
    gate = InMemorySessionGate()
    gate.enter("s")
    # A reply landing mid-run must NOT get its own stream.
    assert gate.enter("s") is False


def test_finish_relays_one_more_round_when_reply_arrived_midstream():
    gate = InMemorySessionGate()
    gate.enter("s")
    gate.enter("s")  # mid-stream reply -> pending
    assert gate.finish("s") is True   # don't drop the reply's response
    assert gate.finish("s") is False  # nothing left -> released


def test_finish_releases_when_nothing_pending():
    gate = InMemorySessionGate()
    gate.enter("s")
    assert gate.finish("s") is False
    # Released, so a later turn can stream again.
    assert gate.enter("s") is True


def test_distinct_sessions_do_not_block_each_other():
    gate = InMemorySessionGate()
    assert gate.enter("a") is True
    assert gate.enter("b") is True


def test_release_unwedges_after_error():
    gate = InMemorySessionGate()
    gate.enter("s")
    gate.enter("s")  # pending set too
    gate.release("s")
    assert gate.enter("s") is True
