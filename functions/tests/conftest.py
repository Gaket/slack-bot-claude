import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Config  # noqa: E402
from app.dispatch import InlineDispatcher  # noqa: E402
from app.slack_out import SlackPoster  # noqa: E402


class FakeStore:
    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, session_id):
        self.data[key] = session_id


class FakeDeduper:
    def __init__(self):
        self.claimed = set()

    def claim(self, event_id):
        if event_id in self.claimed:
            return False
        self.claimed.add(event_id)
        return True


class FakeSlackClient:
    def __init__(self):
        self.calls = []
        self.reactions = []
        self.updates = []

    def chat_postMessage(self, **kwargs):
        self.calls.append(kwargs)
        return {"ts": f"posted_{len(self.calls)}"}

    def chat_update(self, **kwargs):
        self.updates.append(kwargs)

    def reactions_add(self, **kwargs):
        self.reactions.append(kwargs)

    @property
    def texts(self):
        return [c["text"] for c in self.calls]


class FakeSessions:
    def __init__(self, stream_events=()):
        self.created = []
        self.sent = []
        self.stream_events = list(stream_events)
        self.events = SimpleNamespace(send=self._send, stream=self._stream)

    def create(self, **kwargs):
        self.created.append(kwargs)
        return SimpleNamespace(id="sesn_test")

    def _send(self, session_id, events):
        self.sent.append((session_id, events))

    def _stream(self, session_id):
        return list(self.stream_events)


class FakeAnthropic:
    def __init__(self, stream_events=()):
        self.sessions = FakeSessions(stream_events)
        self.beta = SimpleNamespace(sessions=self.sessions)


class IdentityConverter:
    """Pass-through converter so chunking tests control exact lengths."""

    def convert(self, text):
        return text


def text_event(text):
    return SimpleNamespace(
        type="agent.message", content=[SimpleNamespace(type="text", text=text)]
    )


def thinking_event(thinking):
    return SimpleNamespace(
        type="agent.message", content=[SimpleNamespace(type="thinking", thinking=thinking)]
    )


def tool_use_event():
    return SimpleNamespace(type="agent.tool_use")


def idle_event():
    return SimpleNamespace(type="session.status_idle")


def terminated_event():
    return SimpleNamespace(type="session.status_terminated")


def make_config(**overrides):
    base = dict(
        anthropic_api_key="sk-test",
        slack_bot_token="xoxb-test",
        slack_signing_secret="sig-test",
        agent_env_id="env_test",
        agent_id="agent_test",
        agent_version=1,
        vault_ids=("vlt_test",),
        bot_id="B_TEST",
    )
    base.update(overrides)
    return Config(**base)


def make_deps(stream_events=(), config=None, slack_client=None):
    """Deps stand-in: everything duck-typed, dispatcher runs inline."""
    client = slack_client if slack_client is not None else FakeSlackClient()
    return SimpleNamespace(
        config=config or make_config(),
        anthropic=FakeAnthropic(stream_events),
        store=FakeStore(),
        deduper=FakeDeduper(),
        poster=SlackPoster(client, IdentityConverter()),
        dispatcher=InlineDispatcher(),
        slack_client=client,
    )
