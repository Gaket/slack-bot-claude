from conftest import FakeSlackClient

from app.slack_in import SlackReader


def test_reader_passes_oldest_inclusive_when_watermark_present():
    client = FakeSlackClient()
    client.replies = [{"ts": "5.0", "text": "x"}]
    reader = SlackReader(client)

    out = reader.fetch_thread_messages("C1", "1.0", "3.0")

    assert out == [{"ts": "5.0", "text": "x"}]
    [call] = client.replies_calls
    assert call["channel"] == "C1"
    assert call["ts"] == "1.0"
    assert call["oldest"] == "3.0"
    assert call["inclusive"] is True


def test_reader_omits_oldest_when_none():
    client = FakeSlackClient()
    reader = SlackReader(client)

    reader.fetch_thread_messages("C1", "1.0", None)

    [call] = client.replies_calls
    assert "oldest" not in call
    assert "inclusive" not in call


def test_reader_returns_empty_on_error():
    client = FakeSlackClient()

    def boom(**kwargs):
        raise RuntimeError("nope")

    client.conversations_replies = boom
    reader = SlackReader(client)

    assert reader.fetch_thread_messages("C1", "1.0", None) == []
