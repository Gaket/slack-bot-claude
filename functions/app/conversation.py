import logging
from typing import TYPE_CHECKING

from .relay import relay_stream

if TYPE_CHECKING:
    from .runtime import Deps


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
        session = deps.anthropic.beta.sessions.create(**session_params)
        logging.info(f"Session created: {session.id}")
        deps.store.set(session_key, session.id)

        deps.anthropic.beta.sessions.events.send(
            session.id,
            events=[
                {"type": "user.message", "content": [{"type": "text", "text": question}]}
            ],
        )
        relay_stream(
            deps.anthropic.beta.sessions.events.stream(session.id),
            deps.poster,
            channel,
            reply_thread_ts,
        )
    except Exception as e:
        logging.error(f"Session error: {type(e).__name__}: {e}")
        deps.poster.post_error(channel, reply_thread_ts, e)


def continue_conversation(
    deps: "Deps",
    session_id: str,
    channel: str,
    text: str,
    reply_thread_ts: str | None,
) -> None:
    try:
        deps.anthropic.beta.sessions.events.send(
            session_id,
            events=[
                {"type": "user.message", "content": [{"type": "text", "text": text}]}
            ],
        )
        relay_stream(
            deps.anthropic.beta.sessions.events.stream(session_id),
            deps.poster,
            channel,
            reply_thread_ts,
        )
    except Exception as e:
        deps.poster.post_error(channel, reply_thread_ts, e)
