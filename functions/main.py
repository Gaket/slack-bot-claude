import logging

from firebase_functions import https_fn, options

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


@https_fn.on_request(
    region="us-central1",
    timeout_sec=3540,
    memory=options.MemoryOption.MB_512,
    min_instances=1,
)
def slackbot(req: https_fn.Request) -> https_fn.Response:
    # Imported here, not at module scope: deploy analysis imports this file with
    # no env vars set, so nothing from app/ may load before the first request.
    from app.runtime import get_runtime

    return get_runtime().handler.handle(req)
