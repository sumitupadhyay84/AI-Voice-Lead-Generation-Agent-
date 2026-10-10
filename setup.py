import os
import time
import requests
import dotenv
from telnyx import Telnyx

def update_env_file(key, value):
    """Updates or adds a key-value pair in the .env file."""
    env_file = ".env"
    if not os.path.exists(env_file):
        with open(env_file, 'w') as f:
            f.write("")
    
    # Read current lines
    with open(env_file, 'r') as f:
        lines = f.readlines()
        
    # Write back with update
    with open(env_file, 'w') as f:
        updated = False
        for line in lines:
            if line.startswith(f"{key}="):
                f.write(f"{key}={value}\n")
                updated = True
            else:
                f.write(line)
        if not updated:
            f.write(f"{key}={value}\n")
    print(f"Updated .env: {key}={value}")

def main():
    print("Starting Telnyx AI Outbound Caller Setup...")
    dotenv.load_dotenv()
    
    api_key = os.environ.get("TELNYX_API_KEY")
    if not api_key:
        print("[ERROR] TELNYX_API_KEY not found in .env")
        return
        
    client = Telnyx(api_key=api_key)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    
    # 1. Buy a number (if not already set)
    phone = os.environ.get("TELNYX_PHONE_NUMBER")
    if not phone:
        print("\n[1/5] Purchasing a new phone number...")
        try:
            available = client.available_phone_numbers.list(filter={"country_code": "US", "limit": 1})
            if not available.data:
                print("[ERROR] No US numbers available to purchase.")
                phone = None
            else:
                phone = available.data[0].phone_number
                order = client.number_orders.create(phone_numbers=[{"phone_number": phone}])
                print(f"Purchased number: {phone}")
                time.sleep(3) # Wait for order to process
                update_env_file("TELNYX_PHONE_NUMBER", phone)
        except Exception as e:
            print(f"[ERROR] Error purchasing number: {e}")
            print("Note: Your account may need funding (balance > $0.00) to purchase numbers.")
            phone = None # Allow script to continue
    else:
        print(f"\n[1/5] Using existing phone number: {phone}")

    # 2. Create TeXML app (if not already set)
    app_id = os.environ.get("TELNYX_TEXML_APP_ID")
    if not app_id:
        print("\n[2/5] Creating TeXML Application...")
        try:
            app = client.texml_applications.create(
                friendly_name="Plant Solution App",
                voice_url="https://example.com/placeholder", # Required by API, unused by AI outbound
            )
            app_id = app.data.id
            print(f"Created TeXML App ID: {app_id}")
            update_env_file("TELNYX_TEXML_APP_ID", app_id)
        except Exception as e:
            print(f"[ERROR] Error creating TeXML App: {e}")
            app_id = None
    else:
        print(f"\n[2/5] Using existing TeXML App ID: {app_id}")

    # 3. Assign number to TeXML App
    print("\n[3/5] Assigning phone number to TeXML App...")
    if phone and app_id:
        try:
            requests.patch(
                f"https://api.telnyx.com/v2/phone_numbers/{phone}",
                headers=headers,
                json={"connection_id": app_id},
            )
            print(f"Assigned {phone} -> App {app_id}")
        except Exception as e:
             print(f"[ERROR] Error assigning number: {e}")
    else:
        print("[SKIP] Skipping assignment (missing phone or app_id)")

    # 4. Configure outbound profile (Whitelist countries)
    print("\n[4/5] Configuring Outbound Voice Profile...")
    countries = os.environ.get("CALL_LEAD_COUNTRIES", "US,IN").split(",")
    countries = [c.strip() for c in countries]
    try:
        # Get the default outbound profile
        ovps = requests.get("https://api.telnyx.com/v2/outbound_voice_profiles", headers=headers).json()
        if not ovps.get("data"):
            print("[ERROR] No Outbound Voice Profile found on account.")
            ovp_id = None
        else:
            ovp_id = ovps["data"][0]["id"]
            
            # Whitelist destinations
            requests.patch(
                f"https://api.telnyx.com/v2/outbound_voice_profiles/{ovp_id}",
                headers=headers,
                json={"whitelisted_destinations": countries},
            )
            print(f"Whitelisted countries: {countries} on Profile {ovp_id}")
            
            # Assign profile to TeXML App
            if app_id:
                requests.patch(
                    f"https://api.telnyx.com/v2/texml_applications/{app_id}",
                    headers=headers,
                    json={
                        "friendly_name": "Plant Solution App",
                        "voice_url": "https://example.com/placeholder",
                        "outbound": {"outbound_voice_profile_id": ovp_id},
                    },
                )
                print(f"Assigned Outbound Profile {ovp_id} -> App {app_id}")
    except Exception as e:
        print(f"[ERROR] Error configuring outbound profile: {e}")

    # 5. Create AI Assistant
    assistant_id = os.environ.get("TELNYX_ASSISTANT_ID")
    if not assistant_id:
        print("\n[5/5] Creating AI Voice Assistant...")
        name = os.environ.get("ASSISTANT_NAME", "FitPulseOutboundCaller")
        instructions = (
            "You are Alex, a warm, professional, and courteous AI caller calling from {{business_name|FitPulse Studio}}. "
            "Your goal is to conduct a natural phone qualification for leads who inquired about fitness classes.\n\n"
            "CONVERSATION FLOW - FOLLOW STRICTLY IN SEQUENCE:\n\n"
            "STAGE 1: IDENTITY CONFIRMATION\n"
            "- You opened the call with: \"Hi, this is Alex calling from {{business_name|FitPulse Studio}}. Am I speaking with {{name}}?\"\n"
            "- Listen to their answer. If confirmed (\"Yes\", \"Speaking\"), proceed to STAGE 2. If wrong person, apologize politely and end the call.\n\n"
            "STAGE 2: AVAILABILITY CHECK (MANDATORY BEFORE ANY PITCH)\n"
            "- Once identity is confirmed, check if they are free to talk: "
            "\"Great! Are you available to chat for a couple of minutes right now, or did I catch you at a busy time?\"\n"
            "- IF BUSY / DRIVING / IN A MEETING / CANNOT TALK: Do NOT pitch. Immediately respect their time: "
            "\"No problem at all! When would be a better time for me to call you back?\" "
            "Note their requested time, say \"Sure, I will call you back then. Have a wonderful day, goodbye!\", and end the call.\n\n"
            "STAGE 3: REASON FOR CALL & INTEREST CHECK\n"
            "- ONLY when they confirm they have time to talk: "
            "\"Awesome. The reason I'm reaching out is that you recently interacted with our Instagram ad regarding our fitness classes. "
            "I wanted to check if you're still looking to explore our fitness classes or get enrolled in one of them?\"\n"
            "- IF NOT INTERESTED: Say \"I completely understand! Thank you for your time today, {{name}}. Have a wonderful day, goodbye!\" and end the call.\n\n"
            "STAGE 4: COMPLIMENTARY DEMO CLASS PITCH (TRIGGER ON POSITIVE INTENT)\n"
            "- If they show ANY positive intent (\"Yes\", \"Tell me more\", \"I'm interested\", \"What classes do you have?\"): "
            "\"That sounds great! We're actually offering a complimentary demo class so you can experience the workout, check out the studio, "
            "and meet our trainers before making any decision. Would you like to try out a free demo session this week?\"\n\n"
            "STAGE 5: SCHEDULE THE DEMO SESSION & COLLECT EMAIL\n"
            "- Ask: \"Which day works best for you this week, and would you prefer a morning or an evening session?\"\n"
            "- If they say they are NOT available on a specific day (e.g. \"I'm not free Saturday\"): "
            "Offer alternative: \"No worries at all! How does Sunday or a weekday evening like Tuesday or Thursday work for you?\"\n"
            "- Once day and time are chosen, collect their email: "
            "\"Awesome! What is the best email address to send your demo class pass and studio directions to?\"\n"
            "- Repeat back the email clearly for confirmation.\n\n"
            "STAGE 6: CALL WRAP-UP & DECISIVE SIGN-OFF (STRICT FINAL STEP)\n"
            "- CRITICAL RULE: Once the demo is scheduled and email is collected, the booking is COMPLETE.\n"
            "- DO NOT re-ask for their fitness goals, budget, or any previously provided details.\n"
            "- Provide a clean, warm conclusion and end the call: "
            "\"You're all set, {{name}}! We've booked your free demo for [Day] at [Time spoken in words], and I've sent the confirmation to [Email]. "
            "Thank you so much for your time, have a wonderful day, and goodbye!\"\n\n"
            "HANDLING COMMON QUESTIONS:\n"
            "- \"What kinds of classes do you have?\": \"We offer strength training, HIIT, functional fitness, and yoga, suitable for all fitness levels.\"\n"
            "- \"How much does it cost after the demo?\": \"The demo session is completely free with no commitment. Our trainers can walk you through the membership plans after your workout.\"\n"
            "- \"Can I bring a friend or partner?\": \"Yes, absolutely! You are more than welcome to bring a workout buddy.\"\n"
            "- \"What should I wear or bring?\": \"Just comfortable workout clothes, sports shoes, and a water bottle. We provide towels and equipment.\"\n\n"
            "CRITICAL TIME & NUMBER PRONUNCIATION RULES (TEXT-TO-SPEECH FORMAT):\n"
            "- NEVER write digits with colons (NEVER write \"5:30\", \"6:00 PM\", \"10:30 AM\", \"17:30\").\n"
            "- NEVER say raw numbers for times (NEVER say \"five three zero\" or \"five colon thirty\").\n"
            "- ALWAYS write times phonetically in conversational words: \"five thirty in the evening\", \"seven o'clock in the morning\", \"six in the evening\".\n"
            "- For dates, say \"this Thursday\", \"tomorrow morning\", or \"Saturday, the tenth\". Never write slashes like \"10/10/2026\".\n"
            "- For fees, say \"two thousand rupees\" or \"fifteen hundred rupees\". Never write symbols like \"₹2000\".\n\n"
            "VOICEMAIL INSTRUCTION:\n"
            "If answering machine detection indicates voicemail, wait for the beep and leave: "
            "\"Hi {{name}}, this is Alex from {{business_name|FitPulse Studio}} following up on your fitness inquiry. Please give us a call back whenever you're free. Have a great day!\" and hang up."
        )
        greeting = os.environ.get("ASSISTANT_GREETING", "Hi, this is Alex calling from {{business_name|FitPulse Studio}}. Am I speaking with {{name}}?")
        
        try:
            assistant = client.ai.assistants.create(
                name=name,
                model="moonshotai/Kimi-K2.6",
                instructions=instructions,
                greeting=greeting,
                voice_settings={
                    "voice": "Telnyx.Ultra.f786b574-daa5-4673-aa0c-cbe3e8534c02",
                    "expressive_mode": False,
                    "voice_speed": 1.0
                },
                telephony_settings={
                    "default_texml_app_id": app_id,
                    "answering_machine_detection": "premium"
                },
            )
            assistant_id = assistant.id
            print(f"Created AI Assistant ID: {assistant_id}")
            update_env_file("TELNYX_ASSISTANT_ID", assistant_id)
            print("\n[SUCCESS] Setup Complete! You can now run caller.py")
        except Exception as e:
            print(f"[ERROR] Error creating assistant: {e}")
            if "not available for inference" in str(e):
                 print("Note: The requested model might not be enabled for your account.")
    else:
        print(f"\n[5/5] Using existing AI Assistant ID: {assistant_id}")
        print("\n[SUCCESS] Setup Complete! You can now run caller.py")

if __name__ == "__main__":
    main()
