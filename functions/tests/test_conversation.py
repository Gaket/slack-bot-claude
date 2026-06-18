from conftest import idle_event, make_config, make_deps, text_event

from app.conversation import (
    continue_conversation,
    handle_thread_mention,
    start_conversation,
)


def test_start_creates_session_with_exact_params():
    deps = make_deps(stream_events=[idle_event()])
    start_conversation(deps, "C1", "ts1", "what is up?", "ts1")

    [created] = deps.anthropic.sessions.created
    assert created == {
        "environment_id": "env_test",
        "agent": {"type": "agent", "id": "agent_test", "version": 1},
        "metadata": {"slack_channel": "C1", "slack_session_key": "ts1"},
        "vault_ids": ["vlt_test"],
    }


def test_start_omits_vault_ids_when_empty():
    deps = make_deps(stream_events=[idle_event()], config=make_config(vault_ids=()))
    start_conversation(deps, "C1", "ts1", "q", "ts1")
    [created] = deps.anthropic.sessions.created
    assert "vault_ids" not in created


def test_start_attaches_memory_store_when_set():
    deps = make_deps(
        stream_events=[idle_event()],
        config=make_config(memory_store_id="memstore_test"),
    )
    start_conversation(deps, "C1", "ts1", "q", "ts1")
    [created] = deps.anthropic.sessions.created
    assert created["resources"] == [
        {
            "type": "memory_store",
            "memory_store_id": "memstore_test",
            "access": "read_write",
        }
    ]


def test_start_omits_resources_when_no_memory_store():
    deps = make_deps(stream_events=[idle_event()], config=make_config(memory_store_id=""))
    start_conversation(deps, "C1", "ts1", "q", "ts1")
    [created] = deps.anthropic.sessions.created
    assert "resources" not in created


def test_start_stores_mapping_and_sends_question():
    deps = make_deps(stream_events=[text_event("answer"), idle_event()])
    start_conversation(deps, "C1", "ts1", "the question", "ts1")

    assert deps.store.get("ts1") == "sesn_test"
    [(session_id, events)] = deps.anthropic.sessions.sent
    assert session_id == "sesn_test"
    assert events == [
        {"type": "user.message", "content": [{"type": "text", "text": "the question"}]}
    ]
    assert "answer" in deps.slack_client.texts


def test_start_error_posts_to_right_place():
    deps = make_deps()
    deps.anthropic.sessions.create = None  # not callable -> TypeError
    start_conversation(deps, "C1", "ts1", "q", "ts1")

    [call] = deps.slack_client.calls
    assert call["channel"] == "C1"
    assert call["thread_ts"] == "ts1"
    assert call["text"].startswith("Something went wrong: TypeError:")


def test_continue_sends_to_existing_session():
    deps = make_deps(stream_events=[text_event("more"), idle_event()])
    continue_conversation(deps, "sesn_existing", "C1", "follow up", "ts1")

    [(session_id, events)] = deps.anthropic.sessions.sent
    assert session_id == "sesn_existing"
    assert events[0]["content"][0]["text"] == "follow up"
    assert deps.anthropic.sessions.created == []  # no new session
    assert "more" in deps.slack_client.texts


def test_continue_error_posts_message():
    deps = make_deps()
    deps.anthropic.sessions.events.send = None  # not callable -> TypeError
    continue_conversation(deps, "sesn_x", "C1", "text", None)

    [call] = deps.slack_client.calls
    assert call["thread_ts"] is None
    assert call["text"].startswith("Something went wrong: TypeError:")


# Regression: a reply that lands while the agent is still answering the previous
# turn used to open a SECOND stream on the same session. The Anthropic event
# stream is a live tail, so both loops then relayed every event — every message
# posted twice. The gate makes the mid-run reply a no-op for streaming: it's
# forwarded to the session, but the already-open relay loop owns the stream.


def test_continue_does_not_open_second_stream_when_session_already_streaming():
    deps = make_deps(stream_events=[text_event("answer"), idle_event()])
    deps.gate.enter("sesn_busy")  # a relay loop is already streaming this session

    continue_conversation(deps, "sesn_busy", "C1", "reply mid-run", "100.1")

    # The reply is forwarded to the session so the active loop surfaces it...
    [(session_id, events)] = deps.anthropic.sessions.sent
    assert session_id == "sesn_busy"
    assert events[0]["content"][0]["text"] == "reply mid-run"
    # ...but no second relay ran, so nothing was double-posted.
    assert deps.slack_client.calls == []


def test_continue_streams_normally_when_session_idle():
    # The common case: reply arrives after the previous turn finished. One relay.
    deps = make_deps(stream_events=[text_event("the answer"), idle_event()])
    continue_conversation(deps, "sesn_free", "C1", "follow up", "100.1")
    assert "the answer" in deps.slack_client.texts


# Anthropic archives idle sessions; sending to one then fails with a 400
# "Cannot send events to archived session". Surface a friendly nudge, not a raw
# error string.


def _archived_error(*args, **kwargs):
    raise Exception(
        "Error code: 400 - {'type': 'error', 'error': {'type': "
        "'invalid_request_error', 'message': 'Cannot send events to archived "
        "session: sesn_01DxLooTtkcgUEpCcUYFAzkC'}}"
    )


def test_continue_archived_session_posts_friendly_message():
    deps = make_deps()
    deps.anthropic.sessions.events.send = _archived_error

    continue_conversation(deps, "sesn_archived", "C1", "still there?", "100.1")

    [call] = deps.slack_client.calls
    assert call["channel"] == "C1"
    assert call["thread_ts"] == "100.1"
    assert "archived" in call["text"].lower()
    assert not call["text"].startswith("Something went wrong")


def test_start_archived_session_also_uses_friendly_message():
    deps = make_deps()
    deps.anthropic.sessions.events.send = _archived_error
    start_conversation(deps, "C1", "ts1", "q", "ts1")

    [call] = deps.slack_client.calls
    assert "archived" in call["text"].lower()


# --- Thread-mention backfill ---------------------------------------------------
#
# In channels the bot only acts when @-mentioned, and a mention should hand the
# agent everything said in the thread since the bot was last active — not just the
# mention text.


def _payload_of(deps):
    [(session_id, events)] = deps.anthropic.sessions.sent
    return session_id, events[0]["content"][0]["text"]


def test_mention_backfills_messages_since_watermark():
    deps = make_deps(stream_events=[idle_event()])
    deps.store.set("C1:50.0", "sesn_thread")
    deps.store.set_watermark("C1:50.0", "100.0")
    deps.slack_client.replies = [
        {"ts": "100.0", "user": "U1", "text": "already seen (at watermark)"},
        {"ts": "101.0", "user": "U1", "text": "msg one"},
        {"ts": "102.0", "user": "U2", "text": "msg two"},
        {"ts": "103.0", "user": "U1", "text": "<@U_BOT> please answer"},
    ]
    handle_thread_mention(
        deps, "C1", "C1:50.0", "50.0", "103.0", "please answer", "sesn_thread"
    )

    session_id, payload = _payload_of(deps)
    assert session_id == "sesn_thread"  # continues, no new session
    assert deps.anthropic.sessions.created == []
    assert "already seen" not in payload  # ts <= watermark excluded
    assert "<@U1>: msg one" in payload
    assert "<@U2>: msg two" in payload
    assert "<@U1>: please answer" in payload  # mention rendered with clean question
    assert "<@U_BOT>" not in payload  # raw bot tag never leaks into the prompt
    assert deps.store.watermarks["C1:50.0"] == "103.0"  # advanced to the mention


def test_mention_backfill_excludes_bot_and_subtype_messages():
    deps = make_deps(stream_events=[idle_event()])
    deps.slack_client.replies = [
        {"ts": "10.0", "user": "U1", "text": "a human question"},
        {"ts": "11.0", "bot_id": "B_TEST", "text": "✅ Done (3 steps)"},
        {"ts": "12.0", "user": "U2", "text": "edited", "subtype": "message_changed"},
        {"ts": "13.0", "user": "U1", "text": "<@U_BOT> go"},
    ]
    handle_thread_mention(deps, "C1", "C1:5.0", "5.0", "13.0", "go", None)

    _, payload = _payload_of(deps)
    assert "a human question" in payload
    assert "Done (3 steps)" not in payload  # bot's own post dropped
    assert "edited" not in payload  # subtype dropped
    assert "<@U1>: go" in payload
    # No watermark → whole thread fetched (oldest omitted).
    [call] = deps.slack_client.replies_calls
    assert "oldest" not in call


def test_bare_mention_with_no_new_messages_greets_without_agent():
    deps = make_deps()
    deps.store.set("C1:5.0", "sesn_thread")
    deps.store.set_watermark("C1:5.0", "20.0")
    deps.slack_client.replies = [
        {"ts": "20.0", "user": "U1", "text": "already seen"},
        {"ts": "21.0", "user": "U1", "text": "<@U_BOT>"},  # bare mention, empty text
    ]
    handle_thread_mention(deps, "C1", "C1:5.0", "5.0", "21.0", "", "sesn_thread")

    assert deps.anthropic.sessions.sent == []  # agent not bothered
    [call] = deps.slack_client.calls
    assert "how can i help" in call["text"].lower()
    assert deps.store.watermarks["C1:5.0"] == "21.0"  # still advances


def test_mention_fetch_failure_falls_back_to_question():
    deps = make_deps(stream_events=[idle_event()])

    def boom(**kwargs):
        raise RuntimeError("api down")

    deps.slack_client.conversations_replies = boom
    handle_thread_mention(deps, "C1", "C1:5.0", "5.0", "9.0", "just this", None)

    _, payload = _payload_of(deps)
    assert payload == "just this"
