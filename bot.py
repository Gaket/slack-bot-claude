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
VAULT_IDS = os.environ.get("VAULT_IDS", "").split(",") if os.environ.get("VAULT_IDS") else []

# Bot's user ID (for mentions) — get from auth.test if not in env
BOT_USER_ID = os.environ.get("SLACK_BOT_USER_ID", "U0ACMNZ6SSU")
BOT_ID = os.environ.get("SLACK_BOT_ID", "B0ABX2CETBN")

# Maps Slack thread_ts → Anthropic session_id
thread_sessions: dict[str, str] = {}


def relay_stream(session_id: str, channel: str, thread_ts: str) -> None:
    posted_progress = False

    for ev in client.beta.sessions.events.stream(session_id):
        if ev.type == "agent.message":
            for block in ev.content:
                if hasattr(block, "type"):
                    # Post thinking blocks immediately
                    if block.type == "thinking" and hasattr(block, "thinking"):
                        thinking = block.thinking.strip()
                        if thinking:
                            logging.info(f"Thinking: {thinking[:100]}...")
                            thinking_text = f"💭 *Thinking:*\n```\n{thinking[:800]}\n```"
                            if len(thinking) > 800:
                                thinking_text += "\n_(truncated)_"
                            app.client.chat_postMessage(
                                channel=channel, thread_ts=thread_ts, text=thinking_text
                            )
                    # Post text blocks immediately
                    elif block.type == "text" and block.text.strip():
                        text = mrkdwn.convert(block.text)
                        if len(text) > 3900:
                            text = text[:3900] + "\n_(truncated)_"
                        app.client.chat_postMessage(
                            channel=channel, thread_ts=thread_ts, text=text
                        )
        elif ev.type == "agent.tool_use" and not posted_progress:
            app.client.chat_postMessage(
                channel=channel, thread_ts=thread_ts, text="🔧 Working on it..."
            )
            posted_progress = True
        elif ev.type == "session.status_idle":
            break
        elif ev.type == "session.status_terminated":
            app.client.chat_postMessage(
                channel=channel, thread_ts=thread_ts, text="⏹ Session ended."
            )
            return


def start_session(channel: str, thread_ts: str, question: str) -> None:
    try:
        logging.info(f"Starting session for question: '{question}'")
        session_params = {
            "environment_id": AGENT_ENV_ID,
            "agent": {"type": "agent", **AGENT_CONFIG},
            "metadata": {"slack_channel": channel, "slack_thread_ts": thread_ts},
        }
        if VAULT_IDS:
            session_params["vault_ids"] = VAULT_IDS
        session = client.beta.sessions.create(**session_params)
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

    logging.debug(f"Message event: text='{text[:50]}...', bot_id={event.get('bot_id')}")

    # Skip own messages to prevent recursion
    if event.get("bot_id") == BOT_ID:
        logging.debug("Skipping self message")
        return

    # Only handle thread replies in message events
    # (New mentions are handled by app_mention event to avoid duplicates)
    if thread_ts and thread_ts in thread_sessions:
        session_id = thread_sessions[thread_ts]
        logging.debug(f"Continuing session in thread: {session_id}")
        threading.Thread(
            target=continue_session, args=(session_id, channel, thread_ts, text), daemon=True
        ).start()


if __name__ == "__main__":
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()
