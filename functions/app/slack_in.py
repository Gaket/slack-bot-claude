import logging


class SlackReader:
    """All bot reads from Slack go through here (the input counterpart to SlackPoster)."""

    REPLY_LIMIT = 200  # Threads rarely exceed this; pagination is a future concern.

    def __init__(self, client) -> None:
        self._client = client

    def fetch_thread_messages(
        self, channel: str, thread_ts: str, oldest: str | None
    ) -> list[dict]:
        # oldest=None → fetch the whole thread (first mention into a pre-existing thread).
        # Slack's `oldest` is inclusive; callers filter the boundary themselves.
        # On any failure return [] so the caller degrades to the mention text rather than
        # failing the reply outright.
        try:
            kwargs = {"channel": channel, "ts": thread_ts, "limit": self.REPLY_LIMIT}
            if oldest is not None:
                kwargs["oldest"] = oldest
                kwargs["inclusive"] = True
            resp = self._client.conversations_replies(**kwargs)
            return list(resp.get("messages", []))
        except Exception as e:
            logging.warning(f"Could not fetch thread messages: {type(e).__name__}: {e}")
            return []
