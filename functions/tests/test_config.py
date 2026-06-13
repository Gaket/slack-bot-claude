import pytest

from app.config import Config

FULL_ENV = {
    "ANTHROPIC_KEY": "sk-x",
    "SLACK_BOT_TOKEN": "xoxb-x",
    "SLACK_SIGNING_SECRET": "sig-x",
    "SLACK_APP_TOKEN": "xapp-x",
    "AGENT_ENV_ID": "env_x",
    "AGENT_ID": "agent_x",
    "AGENT_VERSION": "3",
    "VAULT_IDS": "vlt_a,vlt_b",
    "SLACK_BOT_ID": "B123",
}


def test_happy_path():
    cfg = Config.from_env(FULL_ENV)
    assert cfg.anthropic_api_key == "sk-x"
    assert cfg.slack_bot_token == "xoxb-x"
    assert cfg.slack_signing_secret == "sig-x"
    assert cfg.slack_app_token == "xapp-x"
    assert cfg.agent_env_id == "env_x"
    assert cfg.agent_id == "agent_x"
    assert cfg.agent_version == 3
    assert cfg.vault_ids == ("vlt_a", "vlt_b")
    assert cfg.bot_id == "B123"


@pytest.mark.parametrize(
    "missing",
    ["ANTHROPIC_KEY", "SLACK_BOT_TOKEN", "AGENT_ENV_ID", "AGENT_ID", "AGENT_VERSION"],
)
def test_missing_required_raises(missing):
    env = {k: v for k, v in FULL_ENV.items() if k != missing}
    with pytest.raises(KeyError):
        Config.from_env(env)


@pytest.mark.parametrize("optional", ["SLACK_SIGNING_SECRET", "SLACK_APP_TOKEN"])
def test_transport_tokens_default_empty(optional):
    # Each transport only needs its own credential, so the other may be absent.
    env = {k: v for k, v in FULL_ENV.items() if k != optional}
    cfg = Config.from_env(env)
    attr = optional.lower().removeprefix("slack_")
    assert getattr(cfg, f"slack_{attr}") == ""


def test_vault_ids_absent():
    env = {k: v for k, v in FULL_ENV.items() if k != "VAULT_IDS"}
    assert Config.from_env(env).vault_ids == ()


def test_vault_ids_empty():
    assert Config.from_env({**FULL_ENV, "VAULT_IDS": ""}).vault_ids == ()


def test_vault_ids_single():
    assert Config.from_env({**FULL_ENV, "VAULT_IDS": "vlt_only"}).vault_ids == ("vlt_only",)


def test_bot_id_defaults_empty():
    env = {k: v for k, v in FULL_ENV.items() if k != "SLACK_BOT_ID"}
    assert Config.from_env(env).bot_id == ""


def test_agent_version_coerced_to_int():
    assert Config.from_env({**FULL_ENV, "AGENT_VERSION": "42"}).agent_version == 42
