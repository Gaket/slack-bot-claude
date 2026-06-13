from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING

from anthropic import Anthropic
from markdown_to_mrkdwn import SlackMarkdownConverter
from slack_bolt import App

from .config import Config
from .dispatch import Dispatcher, ThreadDispatcher
from .handlers import register_handlers
from .slack_out import SlackPoster
from .store import EventDeduper, SessionStore

if TYPE_CHECKING:
    from slack_bolt.adapter.flask import SlackRequestHandler


@dataclass(frozen=True)
class Deps:
    config: Config
    anthropic: Anthropic
    store: SessionStore
    deduper: EventDeduper
    poster: SlackPoster
    dispatcher: Dispatcher
    bolt_app: App


@dataclass(frozen=True)
class Runtime:
    deps: Deps
    handler: SlackRequestHandler


def build_deps(
    config: Config, bolt_app: App, store: SessionStore, deduper: EventDeduper
) -> Deps:
    """Wire the transport-agnostic object graph and register handlers.

    Both entrypoints share this: Firebase passes a Firestore-backed store and an
    HTTP-configured Bolt app; Railway passes in-memory stores and a Socket Mode
    Bolt app. Everything downstream of here is identical.
    """
    deps = Deps(
        config=config,
        anthropic=Anthropic(api_key=config.anthropic_api_key),
        store=store,
        deduper=deduper,
        poster=SlackPoster(bolt_app.client, SlackMarkdownConverter()),
        dispatcher=ThreadDispatcher(),
        bolt_app=bolt_app,
    )
    register_handlers(bolt_app, deps)
    return deps


_lock = threading.Lock()
_runtime: Runtime | None = None


def get_runtime() -> Runtime:
    """Build the Firebase Functions (HTTP) object graph once per process, on
    first request.

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
    # Firebase/Flask/Firestore imports are local so the Railway Socket Mode
    # entrypoint can import build_deps without pulling in firebase-admin or
    # google-cloud libraries (which it neither has nor needs).
    import firebase_admin
    from firebase_admin import firestore
    from slack_bolt.adapter.flask import SlackRequestHandler

    from .store import FirestoreEventDeduper, FirestoreSessionStore

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
    deps = build_deps(
        config, bolt_app, FirestoreSessionStore(db), FirestoreEventDeduper(db)
    )
    return Runtime(deps=deps, handler=SlackRequestHandler(bolt_app))
