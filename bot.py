import os
import threading

from anthropic import Anthropic
from dotenv import load_dotenv
from markdown_to_mrkdwn import SlackMarkdownConverter
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

load_dotenv()

client = Anthropic(api_key=os.environ["ANTHROPIC_KEY"])
app = App(token=os.environ["SLACK_BOT_TOKEN"])
mrkdwn = SlackMarkdownConverter()

AGENT_ENV_ID = os.environ["AGENT_ENV_ID"]
AGENT_CONFIG = {
    "id": os.environ["AGENT_ID"],
    "version": int(os.environ["AGENT_VERSION"]),
}

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
        session = client.beta.sessions.create(
            environment_id=AGENT_ENV_ID,
            agent={"type": "agent", **AGENT_CONFIG},
            metadata={"slack_channel": channel, "slack_thread_ts": thread_ts},
        )
        thread_sessions[thread_ts] = session.id

        client.beta.sessions.events.send(
            session.id,
            events=[{"type": "user.message", "content": [{"type": "text", "text": question}]}],
        )
        relay_stream(session.id, channel, thread_ts)
    except Exception as e:
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
    channel = event["channel"]
    thread_ts = event.get("thread_ts") or event["ts"]
    question = event["text"].split(">", 1)[-1].strip()

    say(text="On it...", thread_ts=thread_ts)
    threading.Thread(
        target=start_session, args=(channel, thread_ts, question), daemon=True
    ).start()


@app.event("message")
def on_thread_reply(event: dict, ack: object) -> None:
    ack()
    thread_ts = event.get("thread_ts")
    if not thread_ts or event.get("bot_id") or thread_ts not in thread_sessions:
        return

    channel = event["channel"]
    text = event.get("text", "")
    session_id = thread_sessions[thread_ts]

    threading.Thread(
        target=continue_session, args=(session_id, channel, thread_ts, text), daemon=True
    ).start()


if __name__ == "__main__":
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()
