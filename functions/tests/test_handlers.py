from conftest import idle_event, make_deps, text_event

from app.handlers import ACK_MESSAGE, GREETING, handle_app_mention, handle_message


class SayRecorder:
    def __init__(self):
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)


class AckRecorder:
    def __init__(self):
        self.count = 0

    def __call__(self):
        self.count += 1


def mention_event(text="<@U_BOT> hello", ts="100.1", thread_ts=None):
    ev = {"channel": "C1", "ts": ts, "text": text}
    if thread_ts:
        ev["thread_ts"] = thread_ts
    return ev


def test_empty_mention_greets():
    deps, say, ack = make_deps(), SayRecorder(), AckRecorder()
    handle_app_mention(mention_event(text="<@U_BOT>"), say, ack, deps)
    assert ack.count == 1
    assert say.calls == [{"text": GREETING, "thread_ts": "100.1"}]
    assert deps.anthropic.sessions.created == []


def test_mention_starts_session_keyed_by_ts():
    deps = make_deps(stream_events=[text_event("answer"), idle_event()])
    say, ack = SayRecorder(), AckRecorder()
    handle_app_mention(mention_event(), say, ack, deps)

    assert ack.count == 1
    assert say.calls[0]["text"] == ACK_MESSAGE
    [created] = deps.anthropic.sessions.created
    assert created["metadata"]["slack_session_key"] == "C1:100.1"
    assert deps.store.get("C1:100.1") == "sesn_test"


def test_mention_in_thread_keyed_by_thread_ts():
    deps = make_deps(stream_events=[idle_event()])
    handle_app_mention(
        mention_event(thread_ts="50.0"), SayRecorder(), AckRecorder(), deps
    )
    [created] = deps.anthropic.sessions.created
    assert created["metadata"]["slack_session_key"] == "C1:50.0"


def test_dm_top_level_starts_session_keyed_by_ts_and_replies_in_thread():
    deps = make_deps(stream_events=[text_event("dm answer"), idle_event()])
    ack = AckRecorder()
    handle_message(
        {"channel": "D1", "channel_type": "im", "text": "hi", "ts": "1.0"}, ack, deps
    )

    assert ack.count == 1
    [created] = deps.anthropic.sessions.created
    assert created["metadata"]["slack_session_key"] == "D1:1.0"
    assert deps.store.get("D1:1.0") == "sesn_test"
    # Replies thread under the originating DM message
    assert all(c["thread_ts"] == "1.0" for c in deps.slack_client.calls)
    # 👀 reaction on the thread-start message
    assert deps.slack_client.reactions == [
        {"channel": "D1", "timestamp": "1.0", "name": "eyes"}
    ]


def test_dm_thread_reply_continues_existing_session():
    deps = make_deps(stream_events=[idle_event()])
    deps.store.set("D1:1.0", "sesn_dm")
    handle_message(
        {
            "channel": "D1",
            "channel_type": "im",
            "text": "more",
            "ts": "2.0",
            "thread_ts": "1.0",
        },
        AckRecorder(),
        deps,
    )

    assert deps.anthropic.sessions.created == []
    [(session_id, _)] = deps.anthropic.sessions.sent
    assert session_id == "sesn_dm"
    # No reaction on thread replies
    assert deps.slack_client.reactions == []


def test_dm_thread_reply_without_session_starts_one_keyed_by_thread():
    deps = make_deps(stream_events=[idle_event()])
    handle_message(
        {
            "channel": "D1",
            "channel_type": "im",
            "text": "orphan reply",
            "ts": "5.0",
            "thread_ts": "4.0",
        },
        AckRecorder(),
        deps,
    )

    [created] = deps.anthropic.sessions.created
    assert created["metadata"]["slack_session_key"] == "D1:4.0"


def test_mention_in_dm_skipped_message_handler_owns_it():
    deps = make_deps()
    say, ack = SayRecorder(), AckRecorder()
    handle_app_mention(
        {"channel": "D1", "ts": "1.0", "text": "<@U_BOT> hi"}, say, ack, deps
    )
    assert ack.count == 1
    assert say.calls == []
    assert deps.anthropic.sessions.created == []


def test_mention_adds_eyes_reaction():
    deps = make_deps(stream_events=[idle_event()])
    handle_app_mention(mention_event(), SayRecorder(), AckRecorder(), deps)
    assert deps.slack_client.reactions == [
        {"channel": "C1", "timestamp": "100.1", "name": "eyes"}
    ]


def test_reaction_failure_does_not_break_flow():
    deps = make_deps(stream_events=[text_event("still works"), idle_event()])

    def boom(**kwargs):
        raise RuntimeError("missing_scope")

    deps.slack_client.reactions_add = boom
    handle_app_mention(mention_event(), SayRecorder(), AckRecorder(), deps)
    assert "still works" in deps.slack_client.texts


def test_thread_reply_continues_existing_session():
    deps = make_deps(stream_events=[idle_event()])
    deps.store.set("C1:100.1", "sesn_thread")
    handle_message(
        {"channel": "C1", "thread_ts": "100.1", "text": "follow up", "ts": "101.0"},
        AckRecorder(),
        deps,
    )

    [(session_id, _)] = deps.anthropic.sessions.sent
    assert session_id == "sesn_thread"


def test_thread_reply_without_session_is_noop():
    deps = make_deps()
    handle_message(
        {"channel": "C1", "thread_ts": "999.9", "text": "hi", "ts": "1000.0"},
        AckRecorder(),
        deps,
    )
    assert deps.anthropic.sessions.sent == []
    assert deps.anthropic.sessions.created == []


def test_non_thread_channel_message_ignored():
    deps = make_deps()
    handle_message({"channel": "C1", "text": "hi", "ts": "1.0"}, AckRecorder(), deps)
    assert deps.anthropic.sessions.created == []


def test_own_bot_message_ignored():
    deps = make_deps()
    deps.store.set("D1", "sesn_dm")
    handle_message(
        {
            "channel": "D1",
            "channel_type": "im",
            "text": "echo",
            "ts": "3.0",
            "bot_id": "B_TEST",
        },
        AckRecorder(),
        deps,
    )
    assert deps.anthropic.sessions.sent == []


def test_subtype_message_ignored():
    deps = make_deps()
    handle_message(
        {
            "channel": "D1",
            "channel_type": "im",
            "text": "edited",
            "ts": "4.0",
            "subtype": "message_changed",
        },
        AckRecorder(),
        deps,
    )
    assert deps.anthropic.sessions.created == []


def test_ack_always_called():
    deps = make_deps()
    ack = AckRecorder()
    handle_message(
        {"channel": "C1", "text": "x", "ts": "1.0", "subtype": "channel_join"}, ack, deps
    )
    assert ack.count == 1
