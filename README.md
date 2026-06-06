# Slack Managed Claude Bot

A universal Slack bot that connects any Claude Managed Agent to Slack. The bot code stays the same — only the `.env` changes to point at a different agent.

## How it works

- Mention the bot in any channel → it creates a new managed agent session
- Reply in the thread → continues the same session (multi-turn conversation)
- Swap `AGENT_ENV_ID` / `AGENT_ID` / `AGENT_VERSION` to target any managed agent

## Setup

### 1. Create a Slack App

1. Go to https://api.slack.com/apps and create a new app
2. Under **Socket Mode**, enable it and generate an App-Level Token with scope `connections:write` — this is your `SLACK_APP_TOKEN`
3. Under **OAuth & Permissions**, add these Bot Token Scopes:
   - `app_mentions:read`
   - `chat:write`
   - `channels:history`
   - `groups:history`
4. Install the app to your workspace and copy the Bot User OAuth Token — this is your `SLACK_BOT_TOKEN`
5. Under **Event Subscriptions → Subscribe to bot events**, add:
   - `app_mention`
   - `message.channels`
   - `message.groups`

### 2. Configure

```bash
cp .env.example .env
# Fill in all values in .env
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run

```bash
python bot.py
```

### 5. Invite the bot to a channel

```
/invite @your-bot-name
```

## Environment Variables

| Variable | Description |
|---|---|
| `ANTHROPIC_KEY` | Your Anthropic API key |
| `APIFY_KEY` | Your Apify API key |
| `SLACK_BOT_TOKEN` | `xoxb-...` Bot User OAuth Token |
| `SLACK_APP_TOKEN` | `xapp-...` App-Level Token (Socket Mode) |
| `AGENT_ENV_ID` | Managed agent environment ID |
| `AGENT_ID` | Managed agent ID |
| `AGENT_VERSION` | Managed agent version (integer) |
