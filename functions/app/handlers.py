import logging
from typing import TYPE_CHECKING

from .conversation import continue_conversation, start_conversation

if TYPE_CHECKING:
    from slack_bolt import App

    from .runtime import Deps

GREETING = "Hi! How can I help you?"
ACK_MESSAGE = "On it..."


def session_key(channel: str, thread_ts: str) -> str:
    # Slack only guarantees ts uniqueness per channel, so scope the key by channel.
    return f"{channel}:{thread_ts}"


def handle_app_mention(event: dict, say, ack, deps: "Deps") -> None:
    ack()
    channel = event["channel"]
    # A DM that mentions the bot fires BOTH app_mention and message.im for the
    # same text; the message handler owns DMs, so skip here to avoid double replies.
    if channel.startswith("D"):
        return
    thread_ts = event.get("thread_ts") or event["ts"]
    question = event["text"].split(">", 1)[-1].strip()
    logging.info(f"Mention received, question: '{question}'")

    if not question:
        say(text=GREETING, thread_ts=thread_ts)
        return

    deps.poster.add_reaction(channel, event["ts"], "eyes")
    say(text=ACK_MESSAGE, thread_ts=thread_ts)
    # In a channel, the session is keyed by the thread and replies thread under the mention.
    deps.dispatcher.dispatch(
        lambda: start_conversation(
            deps, channel, session_key(channel, thread_ts), question, thread_ts
        )
    )


def handle_message(event: dict, ack, deps: "Deps") -> None:
    ack()
    # Ignore the bot's own messages and edits/joins/other system subtypes.
    if event.get("bot_id") == deps.config.bot_id or event.get("subtype"):
        return

    channel = event["channel"]
    text = event.get("text", "")
    thread_ts = event.get("thread_ts")

    # Direct message (App Home "Messages" tab): one session per thread, mirroring
    # channel behavior. A top-level DM starts a session and replies in its thread;
    # replies inside a DM thread continue (or revive) that thread's session.
    if event.get("channel_type") == "im":
        ts = event["ts"]
        if thread_ts:
            session_id = deps.store.get(session_key(channel, thread_ts))
            if session_id:
                deps.dispatcher.dispatch(
                    lambda: continue_conversation(deps, session_id, channel, text, thread_ts)
                )
            else:
                deps.dispatcher.dispatch(
                    lambda: start_conversation(
                        deps, channel, session_key(channel, thread_ts), text, thread_ts
                    )
                )
        else:
            deps.poster.add_reaction(channel, ts, "eyes")
            deps.dispatcher.dispatch(
                lambda: start_conversation(
                    deps, channel, session_key(channel, ts), text, ts
                )
            )
        return

    # Channel/group: only continue an existing thread session.
    # New conversations in channels start via app_mention, not here.
    if thread_ts:
        session_id = deps.store.get(session_key(channel, thread_ts))
        if session_id:
            deps.dispatcher.dispatch(
                lambda: continue_conversation(deps, session_id, channel, text, thread_ts)
            )


def register_handlers(bolt_app: "App", deps: "Deps") -> None:
    # Shims must declare exactly the params bolt should inject (matched by name);
    # wrapping with functools.partial would break bolt's signature inspection.
    @bolt_app.event("app_mention")
    def _on_mention(event, say, ack):
        handle_app_mention(event, say, ack, deps)

    @bolt_app.event("message")
    def _on_message(event, ack):
        handle_message(event, ack, deps)
