from conftest import (
    FakeSlackClient,
    IdentityConverter,
    idle_event,
    terminated_event,
    text_event,
    thinking_event,
    tool_use_event,
)

from app.relay import TERMINATED_MESSAGE, relay_stream
from app.slack_out import SlackPoster


def make_poster():
    client = FakeSlackClient()
    return SlackPoster(client, IdentityConverter()), client


def test_text_block_posted():
    poster, client = make_poster()
    relay_stream([text_event("hello world"), idle_event()], poster, "C1", "ts1")
    assert client.texts == ["hello world"]
    assert client.calls[0]["channel"] == "C1"
    assert client.calls[0]["thread_ts"] == "ts1"


def test_long_text_chunked_with_continuation_prefix():
    poster, client = make_poster()
    long_text = "x" * 4000
    relay_stream([text_event(long_text), idle_event()], poster, "C1", "ts1")
    assert len(client.calls) == 2
    assert client.texts[0] == "x" * 3900
    assert client.texts[1] == "_(continued...)_\n" + "x" * 100


def test_thinking_truncated_at_800_with_suffix():
    poster, client = make_poster()
    relay_stream([thinking_event("t" * 900), idle_event()], poster, "C1", "ts1")
    [text] = client.texts
    assert text.startswith("💭 *Thinking:*\n```\n" + "t" * 800)
    assert text.endswith("\n_(continued in thread)_")


def test_short_thinking_no_suffix():
    poster, client = make_poster()
    relay_stream([thinking_event("brief")], poster, "C1", "ts1")
    [text] = client.texts
    assert "brief" in text
    assert "_(continued in thread)_" not in text


def test_empty_blocks_skipped():
    poster, client = make_poster()
    relay_stream(
        [text_event("   "), thinking_event("  "), idle_event()], poster, "C1", "ts1"
    )
    assert client.calls == []


def test_first_tool_use_posts_single_status_message():
    poster, client = make_poster()
    relay_stream([tool_use_event(), idle_event()], poster, "C1", "ts1")
    [status] = client.texts
    assert "Working" in status
    assert client.calls[0]["thread_ts"] == "ts1"


def test_more_tool_uses_update_status_in_place():
    poster, client = make_poster()
    relay_stream(
        [tool_use_event(), tool_use_event(), tool_use_event(), idle_event()],
        poster,
        "C1",
        "ts1",
    )
    # One posted message, edited in place — not a stream of new ones.
    assert len(client.calls) == 1
    assert client.updates[0]["ts"] == "posted_1"
    assert "(3 steps)" in client.updates[-2]["text"]


def test_status_finalized_on_idle():
    poster, client = make_poster()
    relay_stream([tool_use_event(), tool_use_event(), idle_event()], poster, "C1", "ts1")
    assert "✅" in client.updates[-1]["text"]
    assert "(2 steps)" in client.updates[-1]["text"]


def test_no_status_message_without_tool_use():
    poster, client = make_poster()
    relay_stream([text_event("quick answer"), idle_event()], poster, "C1", "ts1")
    assert client.texts == ["quick answer"]
    assert client.updates == []


def test_status_finalized_on_terminated():
    poster, client = make_poster()
    relay_stream([tool_use_event(), terminated_event()], poster, "C1", "ts1")
    assert "✅" in client.updates[-1]["text"]
    assert TERMINATED_MESSAGE in client.texts


def test_status_marked_interrupted_when_stream_raises():
    poster, client = make_poster()

    def broken_stream():
        yield tool_use_event()
        raise RuntimeError("stream died")

    try:
        relay_stream(broken_stream(), poster, "C1", "ts1")
    except RuntimeError:
        pass
    assert "⚠️" in client.updates[-1]["text"]


def test_status_precedes_answer_text():
    poster, client = make_poster()
    relay_stream(
        [tool_use_event(), text_event("the number is 42"), idle_event()],
        poster,
        "C1",
        "ts1",
    )
    assert "Working" in client.texts[0]
    assert client.texts[1] == "the number is 42"


def test_idle_stops_stream():
    poster, client = make_poster()
    relay_stream(
        [text_event("before"), idle_event(), text_event("after")], poster, "C1", "ts1"
    )
    assert client.texts == ["before"]


def test_terminated_posts_message_and_stops():
    poster, client = make_poster()
    relay_stream(
        [terminated_event(), text_event("after")], poster, "C1", "ts1"
    )
    assert client.texts == [TERMINATED_MESSAGE]


def test_dm_flat_replies_use_none_thread():
    poster, client = make_poster()
    relay_stream([text_event("dm reply"), idle_event()], poster, "D1", None)
    assert client.calls[0]["thread_ts"] is None
