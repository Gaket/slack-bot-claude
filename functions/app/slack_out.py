import logging


class SlackPoster:
    """All bot output to Slack goes through here: mrkdwn conversion, chunking, posting."""

    CHUNK_SIZE = 3900  # Slack rejects messages over 4000 chars
    THINKING_LIMIT = 800

    def __init__(self, client, converter) -> None:
        self._client = client
        self._converter = converter

    def post(self, channel: str, thread_ts: str | None, text: str) -> None:
        self._client.chat_postMessage(channel=channel, thread_ts=thread_ts, text=text)

    def post_thinking(self, channel: str, thread_ts: str | None, thinking: str) -> None:
        logging.info(f"Thinking: {thinking[:100]}...")
        text = f"💭 *Thinking:*\n```\n{thinking[:self.THINKING_LIMIT]}\n```"
        if len(thinking) > self.THINKING_LIMIT:
            text += "\n_(continued in thread)_"
        self.post(channel, thread_ts, text)

    def post_text(self, channel: str, thread_ts: str | None, markdown: str) -> None:
        text = self._converter.convert(markdown)
        chunks = [
            text[i : i + self.CHUNK_SIZE] for i in range(0, len(text), self.CHUNK_SIZE)
        ]
        for i, chunk in enumerate(chunks):
            if i > 0:
                chunk = f"_(continued...)_\n{chunk}"
            self.post(channel, thread_ts, chunk)

    def post_error(self, channel: str, thread_ts: str | None, exc: Exception) -> None:
        self.post(channel, thread_ts, f"Something went wrong: {type(exc).__name__}: {exc}")

    def post_status(self, channel: str, thread_ts: str | None, text: str) -> str | None:
        # Best-effort progress indicator; returns the message ts so it can be
        # edited in place. None means "don't try to update later".
        try:
            resp = self._client.chat_postMessage(
                channel=channel, thread_ts=thread_ts, text=text
            )
            return resp["ts"] if resp else None
        except Exception as e:
            logging.warning(f"Could not post status: {type(e).__name__}: {e}")
            return None

    def update_status(self, channel: str, ts: str, text: str) -> None:
        try:
            self._client.chat_update(channel=channel, ts=ts, text=text)
        except Exception as e:
            logging.warning(f"Could not update status: {type(e).__name__}: {e}")

    def add_reaction(self, channel: str, ts: str, name: str) -> None:
        # Best-effort: missing reactions:write scope must not break the reply flow.
        try:
            self._client.reactions_add(channel=channel, timestamp=ts, name=name)
        except Exception as e:
            logging.warning(f"Could not add reaction '{name}': {type(e).__name__}: {e}")
