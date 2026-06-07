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


def test_tool_use_posts_nothing():
    poster, client = make_poster()
    relay_stream(
        [tool_use_event(), tool_use_event(), tool_use_event(), idle_event()],
        poster,
        "C1",
        "ts1",
    )
    assert client.texts == []


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
