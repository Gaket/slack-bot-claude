from collections.abc import Iterable
from typing import Any

from .slack_out import SlackPoster

TERMINATED_MESSAGE = "⏹ Session ended."
STATUS_WORKING = "🔧 Working on it…"


def _steps(n: int) -> str:
    return f"({n} step{'s' if n != 1 else ''})"


def relay_stream(
    events: Iterable[Any], poster: SlackPoster, channel: str, thread_ts: str | None
) -> None:
    """Relay agent session events to Slack until the session goes idle or terminates.

    Tool use is surfaced as a single status message edited in place (one line of
    progress, not a stream of tool calls), finalized when the session ends.
    """
    status_ts: str | None = None
    status_attempted = False
    finalized = False
    steps = 0
    try:
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
            elif ev.type == "agent.tool_use":
                steps += 1
                if not status_attempted:
                    status_attempted = True
                    status_ts = poster.post_status(channel, thread_ts, STATUS_WORKING)
                elif status_ts:
                    poster.update_status(
                        channel, status_ts, f"{STATUS_WORKING} {_steps(steps)}"
                    )
            elif ev.type == "session.status_idle":
                if status_ts:
                    poster.update_status(channel, status_ts, f"✅ Done {_steps(steps)}")
                    finalized = True
                break
            elif ev.type == "session.status_terminated":
                if status_ts:
                    poster.update_status(channel, status_ts, f"✅ Done {_steps(steps)}")
                    finalized = True
                poster.post(channel, thread_ts, TERMINATED_MESSAGE)
                return
    finally:
        # Abnormal exit (stream error mid-relay): don't leave the status
        # message spinning on "Working on it…" above the error reply.
        if status_ts and not finalized:
            poster.update_status(channel, status_ts, f"⚠️ Interrupted {_steps(steps)}")
