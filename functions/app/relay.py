from collections.abc import Iterable
from typing import Any

from .slack_out import SlackPoster

TERMINATED_MESSAGE = "⏹ Session ended."


def relay_stream(
    events: Iterable[Any], poster: SlackPoster, channel: str, thread_ts: str | None
) -> None:
    """Relay agent session events to Slack until the session goes idle or terminates."""
    for ev in events:
        if ev.type == "agent.message":
            for block in ev.content:
                if hasattr(block, "type"):
                    if block.type == "thinking" and hasattr(block, "thinking"):
                        thinking = block.thinking.strip()
                        if thinking:
                            poster.post_thinking(channel, thread_ts, thinking)
                    elif block.type == "text" and block.text.strip():
                        poster.post_text(channel, thread_ts, block.text)
        elif ev.type == "session.status_idle":
            break
        elif ev.type == "session.status_terminated":
            poster.post(channel, thread_ts, TERMINATED_MESSAGE)
            return
