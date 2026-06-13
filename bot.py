"""Railway entrypoint — runs the shared Slack app over Socket Mode.

Railway has no public URL and no GCP credentials, so this reuses the exact same
Bolt handlers as the Firebase HTTP function (functions/app/) but swaps in an
in-memory store and a WebSocket transport. One source of truth for handler
logic across both deployments; this file is only transport glue.

Railway keeps its existing `python bot.py` start command — we add functions/ to
the import path so the `app` package resolves the same way it does under
Firebase Functions.
"""

import logging
import os
import sys

from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "functions"))

from app.config import Config  # noqa: E402
from app.runtime import build_deps  # noqa: E402
from app.store import InMemoryEventDeduper, InMemorySessionStore  # noqa: E402

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def main() -> None:
    config = Config.from_env()
    if not config.slack_app_token:
        raise SystemExit("SLACK_APP_TOKEN is required for Socket Mode (Railway)")

    # Socket Mode needs no signing secret, and process_before_response is an
    # HTTP/FaaS concern — the Bolt defaults are correct for a long-lived process.
    bolt_app = App(token=config.slack_bot_token)
    build_deps(
        config=config,
        bolt_app=bolt_app,
        store=InMemorySessionStore(),
        deduper=InMemoryEventDeduper(),
    )
    SocketModeHandler(bolt_app, config.slack_app_token).start()


if __name__ == "__main__":
    main()
