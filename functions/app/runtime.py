import threading
from dataclasses import dataclass

import firebase_admin
from anthropic import Anthropic
from firebase_admin import firestore
from markdown_to_mrkdwn import SlackMarkdownConverter
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler

from .config import Config
from .dispatch import Dispatcher, ThreadDispatcher
from .handlers import register_handlers
from .session_gate import InMemorySessionGate, SessionGate
from .slack_out import SlackPoster
from .store import EventDeduper, FirestoreEventDeduper, FirestoreSessionStore, SessionStore


@dataclass(frozen=True)
class Deps:
    config: Config
    anthropic: Anthropic
    store: SessionStore
    deduper: EventDeduper
    poster: SlackPoster
    dispatcher: Dispatcher
    gate: SessionGate
    bolt_app: App


@dataclass(frozen=True)
class Runtime:
    deps: Deps
    handler: SlackRequestHandler


_lock = threading.Lock()
_runtime: Runtime | None = None


def get_runtime() -> Runtime:
    """Build the object graph once per process, on first request.

    Construction must not happen at import time: Firebase CLI imports the
    codebase at deploy-analysis time with no env vars set.
    """
    global _runtime
    if _runtime is not None:
        return _runtime
    with _lock:
        if _runtime is None:
            _runtime = _build_runtime()
    return _runtime


def _build_runtime() -> Runtime:
    if not firebase_admin._apps:
        firebase_admin.initialize_app()

    config = Config.from_env()
    bolt_app = App(
        token=config.slack_bot_token,
        signing_secret=config.slack_signing_secret,
        process_before_response=True,
    )
    # Named Native-mode database: the project's (default) database is in
    # Datastore Mode, which the Firestore client API cannot use.
    db = firestore.client(database_id="slackbot")
    deps = Deps(
        config=config,
        anthropic=Anthropic(api_key=config.anthropic_api_key),
        store=FirestoreSessionStore(db),
        deduper=FirestoreEventDeduper(db),
        poster=SlackPoster(bolt_app.client, SlackMarkdownConverter()),
        dispatcher=ThreadDispatcher(),
        gate=InMemorySessionGate(),
        bolt_app=bolt_app,
    )
    register_handlers(bolt_app, deps)
    return Runtime(deps=deps, handler=SlackRequestHandler(bolt_app))
