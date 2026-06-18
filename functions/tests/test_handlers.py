from conftest import idle_event, make_deps, text_event

from app.handlers import GREETING, handle_app_mention, handle_message


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
    assert say.calls == []
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
    # 👀 on the reply itself signals the message was received
    assert deps.slack_client.reactions == [
        {"channel": "D1", "timestamp": "2.0", "name": "eyes"}
    ]


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


def test_channel_thread_reply_without_mention_is_noop():
    # New behavior: in channels the bot only acts when @-mentioned. A plain thread
    # reply — even with a live session — must not trigger a response or a reaction.
    deps = make_deps(stream_events=[idle_event()])
    deps.store.set("C1:100.1", "sesn_thread")
    handle_message(
        {"channel": "C1", "thread_ts": "100.1", "text": "follow up", "ts": "101.0"},
        AckRecorder(),
        deps,
    )

    assert deps.anthropic.sessions.sent == []
    assert deps.slack_client.reactions == []


def test_mention_in_existing_thread_continues_session_and_advances_watermark():
    deps = make_deps(stream_events=[idle_event()])
    deps.store.set("C1:100.1", "sesn_thread")
    handle_app_mention(
        mention_event(text="<@U_BOT> more", ts="105.0", thread_ts="100.1"),
        SayRecorder(),
        AckRecorder(),
        deps,
    )

    # No new session created; the existing one is reused.
    assert deps.anthropic.sessions.created == []
    [(session_id, _)] = deps.anthropic.sessions.sent
    assert session_id == "sesn_thread"
    assert deps.store.watermarks["C1:100.1"] == "105.0"


def test_remention_in_thread_does_not_create_second_session():
    # Regression: handle_app_mention used to always start_conversation, overwriting
    # the stored session id on every re-mention and discarding context.
    deps = make_deps(stream_events=[idle_event()])
    handle_app_mention(mention_event(), SayRecorder(), AckRecorder(), deps, event_id="E1")
    assert len(deps.anthropic.sessions.created) == 1
    handle_app_mention(
        mention_event(text="<@U_BOT> again", ts="102.0", thread_ts="100.1"),
        SayRecorder(),
        AckRecorder(),
        deps,
        event_id="E2",
    )
    assert len(deps.anthropic.sessions.created) == 1


def test_thread_reply_without_session_is_noop():
    deps = make_deps()
    handle_message(
        {"channel": "C1", "thread_ts": "999.9", "text": "hi", "ts": "1000.0"},
        AckRecorder(),
        deps,
    )
    assert deps.anthropic.sessions.sent == []
    assert deps.anthropic.sessions.created == []
    # No session for this thread → bot isn't involved, so no reaction either
    assert deps.slack_client.reactions == []


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


# Slack's Events API is at-least-once: it redelivers (immediately, +1min, +5min)
# whenever a response misses its 3s deadline, reusing the same event_id. Each
# delivery must be processed at most once or every retry spawns a new session.


def test_duplicate_dm_delivery_same_event_id_starts_one_session():
    deps = make_deps(stream_events=[idle_event()])
    ev = {"channel": "D1", "channel_type": "im", "text": "hi", "ts": "1.0"}
    handle_message(dict(ev), AckRecorder(), deps, event_id="Ev1")
    handle_message(dict(ev), AckRecorder(), deps, event_id="Ev1")
    assert len(deps.anthropic.sessions.created) == 1


def test_duplicate_mention_delivery_same_event_id_starts_one_session():
    deps = make_deps(stream_events=[idle_event()])
    handle_app_mention(mention_event(), SayRecorder(), AckRecorder(), deps, event_id="Ev2")
    handle_app_mention(mention_event(), SayRecorder(), AckRecorder(), deps, event_id="Ev2")
    assert len(deps.anthropic.sessions.created) == 1


def test_duplicate_mention_in_existing_thread_sends_once():
    deps = make_deps(stream_events=[idle_event()])
    deps.store.set("C1:100.1", "sesn_thread")
    ev = mention_event(text="<@U_BOT> follow up", ts="101.0", thread_ts="100.1")
    handle_app_mention(dict(ev), SayRecorder(), AckRecorder(), deps, event_id="Ev3")
    handle_app_mention(dict(ev), SayRecorder(), AckRecorder(), deps, event_id="Ev3")
    assert len(deps.anthropic.sessions.sent) == 1


def test_duplicate_delivery_still_acks():
    deps = make_deps(stream_events=[idle_event()])
    ev = {"channel": "D1", "channel_type": "im", "text": "hi", "ts": "1.0"}
    handle_message(dict(ev), AckRecorder(), deps, event_id="Ev4")
    ack = AckRecorder()
    handle_message(dict(ev), AckRecorder(), deps, event_id="Ev4")
    handle_message(dict(ev), ack, deps, event_id="Ev4")
    assert ack.count == 1


def test_distinct_event_ids_processed_independently():
    deps = make_deps(stream_events=[idle_event()])
    handle_message(
        {"channel": "D1", "channel_type": "im", "text": "one", "ts": "1.0"},
        AckRecorder(), deps, event_id="EvA",
    )
    handle_message(
        {"channel": "D1", "channel_type": "im", "text": "two", "ts": "2.0"},
        AckRecorder(), deps, event_id="EvB",
    )
    assert len(deps.anthropic.sessions.created) == 2


def test_missing_event_id_still_processed():
    deps = make_deps(stream_events=[idle_event()])
    handle_message(
        {"channel": "D1", "channel_type": "im", "text": "hi", "ts": "1.0"},
        AckRecorder(), deps,
    )
    assert len(deps.anthropic.sessions.created) == 1


def test_ack_always_called():
    deps = make_deps()
    ack = AckRecorder()
    handle_message(
        {"channel": "C1", "text": "x", "ts": "1.0", "subtype": "channel_join"}, ack, deps
    )
    assert ack.count == 1
