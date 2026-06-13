import os
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    anthropic_api_key: str
    slack_bot_token: str
    # Transport-specific credentials, so both default to "" when unused:
    #   - signing_secret verifies HTTP webhooks (Firebase Functions)
    #   - app_token opens the Socket Mode WebSocket (Railway)
    # Each entrypoint asserts the one it needs is present.
    slack_signing_secret: str
    slack_app_token: str
    agent_env_id: str
    agent_id: str
    agent_version: int
    vault_ids: tuple[str, ...]
    bot_id: str

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Config":
        # os.environ must only be read here, never at module scope — Firebase CLI
        # imports the codebase at deploy-analysis time with no env vars set.
        if env is None:
            env = os.environ
        vault_ids_raw = env.get("VAULT_IDS", "")
        return cls(
            anthropic_api_key=env["ANTHROPIC_KEY"],
            slack_bot_token=env["SLACK_BOT_TOKEN"],
            slack_signing_secret=env.get("SLACK_SIGNING_SECRET", ""),
            slack_app_token=env.get("SLACK_APP_TOKEN", ""),
            agent_env_id=env["AGENT_ENV_ID"],
            agent_id=env["AGENT_ID"],
            agent_version=int(env["AGENT_VERSION"]),
            vault_ids=tuple(vault_ids_raw.split(",")) if vault_ids_raw else (),
            bot_id=env.get("SLACK_BOT_ID", ""),
        )
