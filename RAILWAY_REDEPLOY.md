# Railway Redeploy Instructions

## Automatic Redeploy (Recommended)
Railway auto-deploys from GitHub when commits are pushed to `main`:
```bash
git push origin main
```
The deployment usually starts within 30 seconds and completes in 1-2 minutes.

**Check deployment status:**
1. Go to https://railway.app
2. Select the `slack-bot-claude` project
3. Click "Deployments" tab
4. View the latest deployment status (green = success, red = failed)
5. Click "View logs" to debug if needed

---

## Manual Redeploy (If Auto-Deploy Fails)
If the GitHub integration isn't working:

1. **Get Railway CLI token** (if needed):
   - https://railway.app/account/tokens
   - Copy your API token

2. **Login to Railway CLI**:
   ```bash
   railway login
   ```
   (Paste API token when prompted)

3. **Link to this project**:
   ```bash
   railway link
   ```
   (Select `slack-bot-claude` when prompted)

4. **Deploy current code**:
   ```bash
   railway up
   ```

---

## Environment Variables
All credentials are stored in Railway's "Variables" section:
- https://railway.app → `slack-bot-claude` → "Variables" tab

Current vars needed:
- `ANTHROPIC_KEY` — Anthropic API key
- `SLACK_BOT_TOKEN` — Slack bot token
- `SLACK_APP_TOKEN` — Slack app token
- `AGENT_ENV_ID` — Managed agent environment ID
- `AGENT_ID` — Managed agent ID
- `AGENT_VERSION` — Agent version number
- `VAULT_IDS` — MCP vault IDs (comma-separated, optional)
- `APIFY_KEY` — Apify API key (optional)

---

## Architecture: shared code, two transports
`bot.py` (the Railway entrypoint) is now thin transport glue. It reuses the same
Bolt handlers as the Firebase Functions deployment (`functions/app/`) — there is
one source of truth for handler logic. The only differences on Railway are:
- **Transport:** Socket Mode (WebSocket) instead of HTTP webhooks, so no public
  URL and no `SLACK_SIGNING_SECRET` are needed.
- **Storage:** in-memory session map + event dedup (`InMemorySessionStore` /
  `InMemoryEventDeduper`) instead of Firestore, so no GCP credentials are needed.
  State resets on restart, matching the original socket-mode bot.

## Socket Mode Connection
The bot connects via Slack Socket Mode (WebSocket):
- No need to expose HTTP endpoints
- Railway auto-restarts the bot if the connection drops
- Check "Console" tab in Railway to see real-time logs

If Socket Mode keeps disconnecting, check:
1. `SLACK_APP_TOKEN` is correct
2. Slack app still has "Socket Mode" enabled in app settings
3. Event Subscriptions are configured: `message.channels`, `message.groups`, `app_mention`

---

## Testing Without Railway
Run locally for quick testing:
```bash
cp .env.example .env
# Edit .env with actual credentials
python bot.py
```

Then in Slack, `@Nyle Helper your question` to test.
