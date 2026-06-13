import logging

from firebase_functions import https_fn, options

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


@https_fn.on_request(
    region="us-central1",
    timeout_sec=3540,
    memory=options.MemoryOption.MB_512,
    # Scale to zero when idle: event_id dedup makes cold-start Slack retries
    # harmless, so a warm instance only buys a faster first 👀 reaction.
    # Requires --no-cpu-throttling on the service so post-response relay
    # threads keep CPU while the instance is up.
    min_instances=0,
)
def slackbot(req: https_fn.Request) -> https_fn.Response:
    # Imported here, not at module scope: deploy analysis imports this file with
    # no env vars set, so nothing from app/ may load before the first request.
    from app.runtime import get_runtime

    # Keepalive target for Cloud Scheduler: building the runtime here both
    # keeps the instance alive and pre-warms the object graph, so the first
    # real Slack event after a quiet spell skips the multi-second lazy init.
    if req.path == "/health":
        get_runtime()
        return https_fn.Response("ok", status=200)

    return get_runtime().handler.handle(req)
