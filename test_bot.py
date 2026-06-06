import os
from dotenv import load_dotenv
from slack_sdk import WebClient

load_dotenv()

client = WebClient(token=os.environ["SLACK_BOT_TOKEN"])

channel = "C0B8PKJ0ES1"
bot_user_id = os.environ.get("SLACK_BOT_USER_ID", "U0ACMNZ6SSU")  # Bot's user ID
message = f"<@{bot_user_id}> test via api"

response = client.chat_postMessage(
    channel=channel,
    text=message,
    metadata={
        "event_type": "nyle_helper_trigger",
        "event_payload": {},
    },
)
print(f"✓ Message sent! ts={response['ts']}, channel={response['channel']}")
