#!/usr/bin/env python3
"""
Iteration test script: Send a mention to the bot via API and wait for response.
Useful for testing bot behavior without manual Slack interaction.
"""
import os
import time
from dotenv import load_dotenv
from slack_sdk import WebClient

load_dotenv()

client = WebClient(token=os.environ["SLACK_BOT_TOKEN"])

channel = "C0B8PKJ0ES1"
bot_user_id = os.environ.get("SLACK_BOT_USER_ID", "U0ACMNZ6SSU")

def test_bot(prompt: str):
    """Send a prompt to the bot and wait for response."""
    message = f"<@{bot_user_id}> {prompt}"

    print(f"📤 Sending: {message}")
    response = client.chat_postMessage(
        channel=channel,
        text=message,
        metadata={
            "event_type": "nyle_helper_trigger",
            "event_payload": {},
        },
    )
    ts = response['ts']
    print(f"✓ Sent (ts={ts})")

    # Wait a bit for bot to process
    print("⏳ Waiting for bot response...")
    time.sleep(8)

    # Get thread messages
    try:
        thread = client.conversations_replies(channel=channel, ts=ts)
        print(f"\n📨 Thread ({len(thread['messages'])} messages):")
        for msg in thread['messages']:
            user = msg.get('username') or msg.get('user', '?')
            text = msg.get('text', '')[:100]
            print(f"  {user}: {text}")
    except Exception as e:
        print(f"Error fetching thread: {e}")

if __name__ == "__main__":
    import sys
    prompt = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "hello"
    test_bot(prompt)
