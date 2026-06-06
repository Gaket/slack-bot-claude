import logging
import os
import threading

from anthropic import Anthropic
from dotenv import load_dotenv
from markdown_to_mrkdwn import SlackMarkdownConverter
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

load_dotenv()
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")

client = Anthropic(api_key=os.environ["ANTHROPIC_KEY"])
app = App(token=os.environ["SLACK_BOT_TOKEN"])
mrkdwn = SlackMarkdownConverter()

AGENT_ENV_ID = os.environ["AGENT_ENV_ID"]
AGENT_CONFIG = {
    "id": os.environ["AGENT_ID"],
    "version": int(os.environ["AGENT_VERSION"]),
}

# Bot's user ID (for mentions) — get from auth.test if not in env
BOT_USER_ID = os.environ.get("SLACK_BOT_USER_ID", "U0ACMNZ6SSU")
BOT_ID = os.environ.get("SLACK_BOT_ID", "B0ABX2CETBN")

# Maps Slack thread_ts → Anthropic session_id
thread_sessions: dict[str, str] = {}


def relay_stream(session_id: str, channel: str, thread_ts: str) -> None:
    summary = ""
    posted_progress = False

    for ev in client.beta.sessions.events.stream(session_id):
        if ev.type == "agent.message":
            for block in ev.content:
                if block.type == "text" and block.text.strip():
                    summary = block.text
        elif ev.type == "agent.tool_use" and not posted_progress:
            app.client.chat_postMessage(
                channel=channel, thread_ts=thread_ts, text="Working on it..."
            )
            posted_progress = True
        elif ev.type == "session.status_idle":
            break
        elif ev.type == "session.status_terminated":
            app.client.chat_postMessage(
                channel=channel, thread_ts=thread_ts, text="Session ended."
            )
            return

    if summary:
        text = mrkdwn.convert(summary)
        if len(text) > 3900:
            text = text[:3900] + "\n_(truncated)_"
        app.client.chat_postMessage(channel=channel, thread_ts=thread_ts, text=text)


def start_session(channel: str, thread_ts: str, question: str) -> None:
    try:
        logging.info(f"Starting session for question: '{question}'")
        session = client.beta.sessions.create(
            environment_id=AGENT_ENV_ID,
            agent={"type": "agent", **AGENT_CONFIG},
            metadata={"slack_channel": channel, "slack_thread_ts": thread_ts},
        )
        logging.info(f"Session created: {session.id}")
        thread_sessions[thread_ts] = session.id

        client.beta.sessions.events.send(
            session.id,
            events=[{"type": "user.message", "content": [{"type": "text", "text": question}]}],
        )
        relay_stream(session.id, channel, thread_ts)
    except Exception as e:
        logging.error(f"Session error: {type(e).__name__}: {e}")
        app.client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text=f"Something went wrong: {type(e).__name__}: {e}",
        )


def continue_session(session_id: str, channel: str, thread_ts: str, text: str) -> None:
    try:
        client.beta.sessions.events.send(
            session_id,
            events=[{"type": "user.message", "content": [{"type": "text", "text": text}]}],
        )
        relay_stream(session_id, channel, thread_ts)
    except Exception as e:
        app.client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text=f"Something went wrong: {type(e).__name__}: {e}",
        )


@app.event("app_mention")
def on_mention(event: dict, say: object, ack: object) -> None:
    ack()
    logging.info(f"Mention received: {event}")
    channel = event["channel"]
    thread_ts = event.get("thread_ts") or event["ts"]
    question = event["text"].split(">", 1)[-1].strip()
    logging.info(f"Question: '{question}'")

    if not question:
        say(text="Hi! How can I help you?", thread_ts=thread_ts)
        return

    say(text="On it...", thread_ts=thread_ts)
    threading.Thread(
        target=start_session, args=(channel, thread_ts, question), daemon=True
    ).start()


@app.event("message")
def on_message(event: dict, ack: object) -> None:
    ack()
    text = event.get("text", "")
    channel = event["channel"]
    thread_ts = event.get("thread_ts")

    logging.debug(f"Message event: text='{text[:50]}...', bot_id={event.get('bot_id')}, metadata={event.get('metadata')}")

    # Check if this is a self-triggered message with API marker
    is_self = event.get("bot_id") == BOT_ID
    metadata = event.get("metadata", {}) or {}
    is_api_trigger = metadata.get("event_type") == "nyle_helper_trigger"

    logging.debug(f"is_self={is_self}, is_api_trigger={is_api_trigger}")

    # Skip accidental self-messages, but allow intentional API triggers
    if is_self and not is_api_trigger:
        logging.debug("Skipping self message")
        return

    # Case 1: Reply in existing thread session
    if thread_ts and thread_ts in thread_sessions:
        session_id = thread_sessions[thread_ts]
        threading.Thread(
            target=continue_session, args=(session_id, channel, thread_ts, text), daemon=True
        ).start()
        return

    # Case 2: New message mentioning the bot
    bot_mention = f"<@{BOT_USER_ID}>"
    if bot_mention in text or "@Nyle Helper" in text or is_api_trigger:
        question = text.split(">", 1)[-1].strip() if ">" in text else text.strip()
        if not question:
            return
        thread_ts = thread_ts or event["ts"]
        logging.info(f"Message mention: '{question}'")
        threading.Thread(
            target=start_session, args=(channel, thread_ts, question), daemon=True
        ).start()


if __name__ == "__main__":
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()
