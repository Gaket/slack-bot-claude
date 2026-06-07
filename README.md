# Slack Managed Claude Bot

A universal Slack bot that connects any Claude Managed Agent to Slack. The bot code stays the same — only the `.env` changes to point at a different agent.

Two ways to run it:

- **`functions/` — Firebase Functions (recommended).** HTTP Events API, sessions persisted in Firestore, unit-tested, survives restarts. See [Deploying to Firebase Functions](#deploying-to-firebase-functions).
- **`bot.py` — local Socket Mode.** Single file, in-memory sessions, good for quick experiments. See [Running locally (Socket Mode)](#running-locally-socket-mode).

## How it works

- Mention the bot in any channel → it creates a new managed agent session, reacts with 👀, and answers in a thread
- Reply in the thread → continues the same session (multi-turn conversation)
- DM the bot → each top-level message starts its own session; replies thread under it
- Swap `AGENT_ENV_ID` / `AGENT_ID` / `AGENT_VERSION` to target any managed agent

## Deploying to Firebase Functions

The `functions/` codebase is a Python 3.13 Gen-2 Cloud Function behind Slack's HTTP Events API.
Layout: `main.py` is a thin entrypoint; logic lives in `app/` (config, Firestore session store,
event handlers, agent-stream relay); tests in `tests/`.

### Prerequisites

- Firebase project on the Blaze plan (`firebase login`, Firebase CLI ≥ 13)
- A Firestore database in **Native mode** (Datastore mode won't work). If your project's
  default database is Datastore mode, create a named one and match `database_id` in
  `app/runtime.py`:
  ```bash
  gcloud firestore databases create --database=slackbot --location=nam5 \
    --type=firestore-native --project=YOUR_PROJECT
  ```
- A Slack app created from the manifest: copy `slack-manifest.example.json` to
  `slack-manifest.json`, replace the `TODO` values (app name, request URL), then import it
  at https://api.slack.com/apps → Create New App → From manifest

### Configure

```bash
cp .firebaserc.example .firebaserc        # set your Firebase project id
cd functions
cp .env.example .env                      # agent IDs + tokens (gitignored, ships with deploy)
python3.13 -m venv venv && venv/bin/pip install -r requirements.txt
```

### Deploy

```bash
firebase deploy --only functions:slackbot --force
```

A deploy takes **~2–4 minutes** end to end (upload, container build, revision rollout).
`--force` is needed because `min_instances: 1` has billing implications.

After the first deploy:

1. Make the endpoint publicly invokable (Slack's requests are verified by signing secret,
   not by IAM):
   ```bash
   gcloud run services add-iam-policy-binding slackbot --region=us-central1 \
     --project=YOUR_PROJECT --member=allUsers --role=roles/run.invoker
   ```
2. In the Slack app config → Event Subscriptions, verify the request URL
   (`https://REGION-PROJECT.cloudfunctions.net/slackbot`) and install the app.

### Tests

```bash
cd functions
venv/bin/pip install -r requirements-dev.txt
venv/bin/python -m pytest tests            # 42 unit tests, no network
env -i venv/bin/python -c "import main"    # deploy-analysis gate: must pass with NO env vars
```

The second command matters: Firebase CLI imports the module at deploy time with no env vars
set, so module scope must stay side-effect free. Keep env access inside `Config.from_env()`.

## Running locally (Socket Mode)

`bot.py` is the original single-file version: in-memory sessions (lost on restart),
channel mentions and thread replies only (no DMs).

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

| Variable | Description | Used by |
|---|---|---|
| `ANTHROPIC_KEY` | Your Anthropic API key | both |
| `SLACK_BOT_TOKEN` | `xoxb-...` Bot User OAuth Token | both |
| `SLACK_SIGNING_SECRET` | App signing secret (Basic Information → App Credentials) | functions |
| `SLACK_APP_TOKEN` | `xapp-...` App-Level Token (Socket Mode) | bot.py |
| `AGENT_ENV_ID` | Managed agent environment ID | both |
| `AGENT_ID` | Managed agent ID | both |
| `AGENT_VERSION` | Managed agent version (integer) | both |
| `VAULT_IDS` | Comma-separated Anthropic vault IDs (optional) | both |
| `SLACK_BOT_ID` | The bot's `B...` id, used to ignore its own messages | both |
