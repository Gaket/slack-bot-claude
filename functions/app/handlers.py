import logging
from typing import TYPE_CHECKING

from .conversation import (
    continue_conversation,
    handle_thread_mention,
    start_conversation,
)

if TYPE_CHECKING:
    from slack_bolt import App

    from .runtime import Deps
GREETING = "Hi! How can I help you?"


def session_key(channel: str, thread_ts: str) -> str:
    # Slack only guarantees ts uniqueness per channel, so scope the key by channel.
    return f"{channel}:{thread_ts}"


def _already_handled(event_id: str | None, deps: "Deps") -> bool:
    # Slack redelivers events whose response missed the 3s deadline (and may
    # duplicate deliveries outright); without this claim each redelivery would
    # start another agent session. Duplicates still get a 200 via ack() so
    # Slack stops retrying.
    #
    # Claim as the LAST step before dispatching work: everything fallible
    # (store reads, reactions) happens first, so a crash after the claim but
    # before the 200 — the one window where a deduped retry would silently
    # drop the message — is nearly impossible. The claim is at-most-once by
    # design: once work is dispatched, failures are reported to the thread
    # by the relay's error path, not retried by Slack.
    if not event_id:
        return False
    if deps.deduper.claim(event_id):
        return False
    logging.info(f"Skipping duplicate Slack delivery for event {event_id}")
    return True


def handle_app_mention(
    event: dict, say, ack, deps: "Deps", event_id: str | None = None
) -> None:
    ack()
    channel = event["channel"]
    # A DM that mentions the bot fires BOTH app_mention and message.im for the
    # same text; the message handler owns DMs, so skip here to avoid double replies.
    if channel.startswith("D"):
        return
    thread_ts = event.get("thread_ts") or event["ts"]
    question = event["text"].split(">", 1)[-1].strip()
    logging.info(f"Mention received, question: '{question}'")

    key = session_key(channel, thread_ts)
    session_id = deps.store.get(key)

    # A bare "@bot" in a brand-new thread has no context to pull in — just greet.
    # (With prior thread messages or an existing session, fall through so the backfill
    # carries the conversation even when the mention itself adds no text.)
    if not question and session_id is None and thread_ts == event["ts"]:
        if not _already_handled(event_id, deps):
            say(text=GREETING, thread_ts=thread_ts)
        return

    deps.poster.add_reaction(channel, event["ts"], "eyes")
    if _already_handled(event_id, deps):
        return
    # The mention is the only trigger in channels; gather every thread message since the
    # bot was last active and continue the thread's session (or start one).
    deps.dispatcher.dispatch(
        lambda: handle_thread_mention(
            deps, channel, key, thread_ts, event["ts"], question, session_id
        )
    )


def handle_message(
    event: dict, ack, deps: "Deps", event_id: str | None = None
) -> None:
    ack()
    # Ignore the bot's own messages and edits/joins/other system subtypes.
    if event.get("bot_id") == deps.config.bot_id or event.get("subtype"):
        return

    channel = event["channel"]
    text = event.get("text", "")
    thread_ts = event.get("thread_ts")

    # Direct message (App Home "Messages" tab): one session per thread, and every
    # message replies (no mention needed, unlike channels). A top-level DM starts a
    # session and replies in its thread; replies inside a DM thread continue (or revive)
    # that thread's session.
    if event.get("channel_type") == "im":
        ts = event["ts"]
        if thread_ts:
            deps.poster.add_reaction(channel, ts, "eyes")
            session_id = deps.store.get(session_key(channel, thread_ts))
            if _already_handled(event_id, deps):
                return
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
            if _already_handled(event_id, deps):
                return
            deps.dispatcher.dispatch(
                lambda: start_conversation(
                    deps, channel, session_key(channel, ts), text, ts
                )
            )
        return

    # Channel/group: the bot only acts when explicitly @-mentioned (handled by
    # handle_app_mention, which backfills everything said since it was last active).
    # Plain thread replies are intentionally ignored here so the bot isn't chatty.


def register_handlers(bolt_app: "App", deps: "Deps") -> None:
    # Shims must declare exactly the params bolt should inject (matched by name);
    # wrapping with functools.partial would break bolt's signature inspection.
    @bolt_app.event("app_mention")
    def _on_mention(body, event, say, ack):
        handle_app_mention(event, say, ack, deps, event_id=body.get("event_id"))

    @bolt_app.event("message")
    def _on_message(body, event, ack):
        handle_message(event, ack, deps, event_id=body.get("event_id"))
