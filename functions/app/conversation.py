import logging
from typing import TYPE_CHECKING

from .relay import relay_stream

if TYPE_CHECKING:
    from .runtime import Deps

# Anthropic archives a session after it has been idle long enough; sending to it
# then fails with 400 "Cannot send events to archived session: ...". The thread
# it was bound to is effectively dead, so we tell the user how to start fresh
# instead of surfacing a raw stack-trace-looking error.
ARCHIVED_SESSION_MESSAGE = (
    "💤 This conversation has been archived, so I can't pick it back up. "
    "Mention me in a new message to start a fresh one."
)


def _is_archived_session_error(exc: Exception) -> bool:
    # Match on the API message rather than the SDK exception class: a plain test
    # double works, and it survives SDK class renames.
    return "archived session" in str(exc).lower()


def _post_failure(deps: "Deps", channel: str, thread_ts: str | None, exc: Exception) -> None:
    if _is_archived_session_error(exc):
        deps.poster.post(channel, thread_ts, ARCHIVED_SESSION_MESSAGE)
    else:
        deps.poster.post_error(channel, thread_ts, exc)


def _send_message(deps: "Deps", session_id: str, text: str) -> None:
    deps.anthropic.beta.sessions.events.send(
        session_id,
        events=[{"type": "user.message", "content": [{"type": "text", "text": text}]}],
    )


def _drive(deps: "Deps", session_id: str, channel: str, reply_thread_ts: str | None) -> None:
    """Relay the session to Slack, but only if no relay is already streaming it.

    When a reply lands mid-run the gate returns False: the message was already
    sent above, and the relay loop that's still open will surface its response —
    so we must not open a second stream (that's what double-posted every reply).
    """
    if not deps.gate.enter(session_id):
        return
    try:
        while True:
            relay_stream(
                deps.anthropic.beta.sessions.events.stream(session_id),
                deps.poster,
                channel,
                reply_thread_ts,
            )
            if not deps.gate.finish(session_id):
                return
    except Exception:
        deps.gate.release(session_id)
        raise


def start_conversation(
    deps: "Deps",
    channel: str,
    session_key: str,
    question: str,
    reply_thread_ts: str | None,
) -> None:
    try:
        logging.info(f"Starting session for question: '{question}'")
        session_params = {
            "environment_id": deps.config.agent_env_id,
            "agent": {
                "type": "agent",
                "id": deps.config.agent_id,
                "version": deps.config.agent_version,
            },
            "metadata": {"slack_channel": channel, "slack_session_key": session_key},
        }
        if deps.config.vault_ids:
            session_params["vault_ids"] = list(deps.config.vault_ids)
        if deps.config.memory_store_id:
            session_params["resources"] = [
                {
                    "type": "memory_store",
                    "memory_store_id": deps.config.memory_store_id,
                    "access": "read_write",
                }
            ]
        session = deps.anthropic.beta.sessions.create(**session_params)
        logging.info(f"Session created: {session.id}")
        deps.store.set(session_key, session.id)

        _send_message(deps, session.id, question)
        _drive(deps, session.id, channel, reply_thread_ts)
    except Exception as e:
        logging.error(f"Session error: {type(e).__name__}: {e}")
        _post_failure(deps, channel, reply_thread_ts, e)


def continue_conversation(
    deps: "Deps",
    session_id: str,
    channel: str,
    text: str,
    reply_thread_ts: str | None,
) -> None:
    try:
        _send_message(deps, session_id, text)
        _drive(deps, session_id, channel, reply_thread_ts)
    except Exception as e:
        _post_failure(deps, channel, reply_thread_ts, e)
