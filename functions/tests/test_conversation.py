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
