from conftest import idle_event, make_config, make_deps, text_event

from app.conversation import continue_conversation, start_conversation


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
