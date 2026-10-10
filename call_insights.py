"""
Call Insights and Transcript Viewer.
Retrieves conversation logs, transcripts, and insights from Telnyx for recent calls.

Usage:
    python call_insights.py
"""
import os
import csv
import dotenv
from telnyx import Telnyx

def view_insights():
    dotenv.load_dotenv()
    api_key = os.environ.get("TELNYX_API_KEY")
    assistant_id = os.environ.get("TELNYX_ASSISTANT_ID")

    if not api_key:
        print("❌ TELNYX_API_KEY missing in .env")
        return

    client = Telnyx(api_key=api_key)

    print("\n" + "="*60)
    print("📊 FitPulse AI Voice Agent - Recent Call Transcripts & Insights")
    print("="*60)

    log_file = "call_log.csv"
    if not os.path.exists(log_file):
        print(f"ℹ️ No call log file found ({log_file}). Make some calls first with caller.py.")
        return

    calls = []
    with open(log_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            calls.append(row)

    if not calls:
        print("ℹ️ No calls logged yet.")
        return

    print(f"Found {len(calls)} logged call attempt(s) in {log_file}:\n")
    for idx, c in enumerate(calls, 1):
        print(f"[{idx}] {c.get('timestamp')} | Lead: {c.get('lead_name')} ({c.get('phone')}) | Status: {c.get('status')} | Event: {c.get('event_id')}")

    print("\n🔍 Fetching latest conversations from Telnyx...")
    try:
        conversations = client.ai.conversations.list()
        if not conversations.data:
            print("ℹ️ No completed conversations recorded on Telnyx yet.")
            return

        for conv in conversations.data[:5]:
            print("\n" + "-"*50)
            print(f"Conversation ID: {conv.id}")
            print(f"Created At: {getattr(conv, 'created_at', 'N/A')}")

            # Fetch messages/transcript
            try:
                msgs = client.ai.conversations.messages.list(conversation_id=conv.id)
                print("\n📝 Transcript:")
                for m in msgs.data:
                    role = getattr(m, 'role', 'speaker').upper()
                    text = getattr(m, 'content', '')
                    print(f"  {role}: {text}")
            except Exception as e:
                print(f"  (Could not fetch messages: {e})")

    except Exception as e:
        print(f"❌ Error fetching conversations: {e}")

if __name__ == "__main__":
    view_insights()
