"""
Simulator script for testing the FitPulse Voice AI Assistant conversation
directly in your terminal without needing a phone number or making phone calls.
"""
import os
import uuid
import dotenv
from telnyx import Telnyx

def run_simulation():
    dotenv.load_dotenv()
    api_key = os.environ.get("TELNYX_API_KEY")
    assistant_id = os.environ.get("TELNYX_ASSISTANT_ID")

    if not api_key or not assistant_id:
        print("❌ TELNYX_API_KEY or TELNYX_ASSISTANT_ID missing in .env")
        return

    client = Telnyx(api_key=api_key)
    
    print("\n" + "="*60)
    print("🥊 FitPulse AI Outbound Caller - Interactive Simulator")
    print("="*60)
    print("Simulating an outbound call to: Rahul Sharma")
    print("Type your responses below (or type 'exit' / 'quit' to end).\n")

    conversation_id = str(uuid.uuid4())

    # Initial AI greeting
    greeting = os.environ.get(
        "ASSISTANT_GREETING",
        "Hi, this is Alex calling from FitPulse Studio. Am I speaking with Rahul Sharma?"
    ).replace("{name}", "Rahul Sharma").replace("{{name}}", "Rahul Sharma")

    print(f"🤖 AI: {greeting}\n")

    while True:
        try:
            user_input = input("👤 You: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ["exit", "quit"]:
                print("\n👋 Ending simulation.")
                break

            response = client.ai.assistants.chat(
                assistant_id=assistant_id,
                conversation_id=conversation_id,
                content=user_input
            )
            print(f"\n🤖 AI: {response.content}\n")
        except (KeyboardInterrupt, EOFError):
            print("\n👋 Exiting simulation.")
            break
        except Exception as e:
            print(f"\n❌ Error during simulation: {e}\n")
            break

if __name__ == "__main__":
    run_simulation()
