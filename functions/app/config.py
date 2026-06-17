import os
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    anthropic_api_key: str
    slack_bot_token: str
    slack_signing_secret: str
    agent_env_id: str
    agent_id: str
    agent_version: int
    vault_ids: tuple[str, ...]
    memory_store_id: str
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
            slack_signing_secret=env["SLACK_SIGNING_SECRET"],
            agent_env_id=env["AGENT_ENV_ID"],
            agent_id=env["AGENT_ID"],
            agent_version=int(env["AGENT_VERSION"]),
            vault_ids=tuple(vault_ids_raw.split(",")) if vault_ids_raw else (),
            memory_store_id=env.get("MEMORY_STORE_ID", ""),
            bot_id=env.get("SLACK_BOT_ID", ""),
        )
