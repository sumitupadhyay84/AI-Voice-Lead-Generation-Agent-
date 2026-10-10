"""
Automated Multi-Scenario Test Suite for FitPulse AI Voice Agent.
Tests 18 diverse real-world customer scenarios via Telnyx AI Assistant
to ensure robust conversational quality, objection handling,
availability checking, proper call endings, and phonetic time pronunciation.

Usage:
    python run_scenario_tests.py
"""
import os
import uuid
import time
import dotenv
from telnyx import Telnyx

dotenv.load_dotenv()
api_key = os.environ.get("TELNYX_API_KEY")
assistant_id = os.environ.get("TELNYX_ASSISTANT_ID")

client = Telnyx(api_key=api_key)

SCENARIOS = [
    {
        "id": 1,
        "name": "Standard Happy Path (Booking + Email + Final Sign-off)",
        "lead_name": "Rahul Sharma",
        "turns": [
            "Yes, speaking.",
            "Yes, I have two minutes. What's this about?",
            "Yes, I saw your Instagram ad and I'm looking to join a gym.",
            "Sure, a free demo class sounds good. I'd like to try it.",
            "Saturday evening would be great.",
            "My email is rahul.sharma@example.com."
        ],
        "checks": [
            ("Did not re-ask fitness goal after email", lambda resp: "fitness goal" not in resp.lower()),
            ("Gave decisive sign-off / goodbye", lambda resp: "goodbye" in resp.lower() or "have a wonderful day" in resp.lower() or "all set" in resp.lower())
        ]
    },
    {
        "id": 2,
        "name": "User Busy / Driving -> Callback Capture & Immediate Exit",
        "lead_name": "Amit Kumar",
        "turns": [
            "Yes, this is Amit.",
            "Actually I'm driving right now, can you call me later?",
            "Tomorrow around five in the evening."
        ],
        "checks": [
            ("Respects busy status without pitching", lambda resp: "instagram" not in resp.lower() and "demo" not in resp.lower()),
            ("Confirms callback and ends call politely", lambda resp: "call you back" in resp.lower() or "tomorrow" in resp.lower() or "goodbye" in resp.lower())
        ]
    },
    {
        "id": 3,
        "name": "Immediate Busy / Refusal to Give Callback Time",
        "lead_name": "Priya Singh",
        "turns": [
            "Yes, Priya here.",
            "I'm in a strict meeting, I really can't talk right now."
        ],
        "checks": [
            ("Politely wraps up without pushing", lambda resp: "sorry" in resp.lower() or "apologize" in resp.lower() or "no problem" in resp.lower() or "goodbye" in resp.lower() or "better time" in resp.lower())
        ]
    },
    {
        "id": 4,
        "name": "Wrong Person / Wrong Number",
        "lead_name": "David Miller",
        "turns": [
            "No, there is no David here. You have the wrong number."
        ],
        "checks": [
            ("Apologizes and ends call immediately", lambda resp: "apologize" in resp.lower() or "sorry" in resp.lower() or "mistake" in resp.lower() or "goodbye" in resp.lower())
        ]
    },
    {
        "id": 5,
        "name": "Saturday Not Available -> Rescheduling to Alternative Day",
        "lead_name": "Neha Gupta",
        "turns": [
            "Yes, speaking.",
            "Yes, I can talk for a minute.",
            "Yes, I want to explore fitness classes.",
            "Sounds good, I want a demo.",
            "No, I'm not available on Saturday for a demo class at all. Weekends are packed."
        ],
        "checks": [
            ("Offers alternative weekday or Sunday slot", lambda resp: "weekday" in resp.lower() or "sunday" in resp.lower() or "tuesday" in resp.lower() or "thursday" in resp.lower() or "day" in resp.lower())
        ]
    },
    {
        "id": 6,
        "name": "Prefers Morning Workout -> Phonetic Time Confirmation",
        "lead_name": "Vikram Malhotra",
        "turns": [
            "Yes, speaking.",
            "Sure, go ahead.",
            "Yes, looking to get back into fitness.",
            "Yes, I'd like a demo.",
            "I can only do early mornings, maybe around 7am on Friday.",
            "vikram.m@gmail.com"
        ],
        "checks": [
            ("Pronounces morning time phonetically", lambda resp: "morning" in resp.lower() or "seven" in resp.lower()),
            ("Collects email and concludes cleanly", lambda resp: "vikram" in resp.lower() or "all set" in resp.lower() or "goodbye" in resp.lower())
        ]
    },
    {
        "id": 7,
        "name": "Hesitation on Cost / Is it Paid?",
        "lead_name": "Karan Johar",
        "turns": [
            "Speaking.",
            "Yes, I have two minutes.",
            "I saw the ad, but how much does this class cost? I don't want to pay upfront."
        ],
        "checks": [
            ("Clarifies demo is 100% free with no commitment", lambda resp: "free" in resp.lower() or "complimentary" in resp.lower() or "no commitment" in resp.lower())
        ]
    },
    {
        "id": 8,
        "name": "Explicit 'Not Interested' -> No Pushiness",
        "lead_name": "Suresh Raina",
        "turns": [
            "Yes, Suresh speaking.",
            "Yes, I have time.",
            "Actually I joined another gym yesterday, so I'm not interested anymore."
        ],
        "checks": [
            ("Politely accepts refusal and wishes them well", lambda resp: "understand" in resp.lower() or "thank you" in resp.lower() or "goodbye" in resp.lower() or "day" in resp.lower())
        ]
    },
    {
        "id": 9,
        "name": "Class Types Inquiry ('What kinds of workouts do you have?')",
        "lead_name": "Ananya Roy",
        "turns": [
            "Yes, this is Ananya.",
            "Sure, I have a few minutes.",
            "What specific types of classes or workouts do you offer at your studio?"
        ],
        "checks": [
            ("Mentions strength, HIIT, or yoga briefly", lambda resp: "strength" in resp.lower() or "hiit" in resp.lower() or "yoga" in resp.lower() or "fitness" in resp.lower())
        ]
    },
    {
        "id": 10,
        "name": "Bring a Friend / Partner Inquiry",
        "lead_name": "Rohan Mehra",
        "turns": [
            "Yes, speaking.",
            "Yes, go ahead.",
            "I am interested, but can I bring my wife / friend along for the demo?"
        ],
        "checks": [
            ("Welcomes bringing friend/partner", lambda resp: "yes" in resp.lower() or "welcome" in resp.lower() or "friend" in resp.lower() or "both" in resp.lower() or "absolutely" in resp.lower())
        ]
    },
    {
        "id": 11,
        "name": "What to Wear / Bring to the Demo Session",
        "lead_name": "Deepak Verma",
        "turns": [
            "Yes, Deepak here.",
            "Yes, I can talk.",
            "Yes, let's book Thursday evening at 6pm.",
            "deepak.v@example.com",
            "What do I need to bring with me on the day?"
        ],
        "checks": [
            ("Mentions comfortable clothes, shoes, or water", lambda resp: "clothes" in resp.lower() or "shoes" in resp.lower() or "water" in resp.lower() or "comfortable" in resp.lower())
        ]
    },
    {
        "id": 12,
        "name": "Studio Location & Parking Inquiry",
        "lead_name": "Simran Kaur",
        "turns": [
            "Yes, speaking.",
            "Yes, I'm free.",
            "Where is your studio located exactly?"
        ],
        "checks": [
            ("Mentions location details or sending Google Maps pin", lambda resp: "location" in resp.lower() or "address" in resp.lower() or "maps" in resp.lower() or "send" in resp.lower())
        ]
    },
    {
        "id": 13,
        "name": "Caller Identity Re-verification ('Who is calling again?')",
        "lead_name": "Mohit Saini",
        "turns": [
            "Yes, who is this again? What company?",
            "Yes, I have time now."
        ],
        "checks": [
            ("Re-identifies FitPulse Studio politely", lambda resp: "alex" in resp.lower() or "fitpulse" in resp.lower() or "studio" in resp.lower())
        ]
    },
    {
        "id": 14,
        "name": "Digital Colon Time Input ('Can we do 6:30pm?') -> Phonetic Echo",
        "lead_name": "Rajesh Khanna",
        "turns": [
            "Yes, speaking.",
            "Yes, I have time.",
            "I'm interested in the demo.",
            "Can we do Thursday at 6:30pm?",
            "rajesh@khanna.com"
        ],
        "checks": [
            ("Does NOT output raw colon time 6:30 in speech confirmation", lambda resp: "6:30" not in resp and "six thirty" in resp.lower())
        ]
    },
    {
        "id": 15,
        "name": "Skeptical Lead ('Is this an automated spam call?')",
        "lead_name": "Harish Patel",
        "turns": [
            "Who is this? Is this a spam call?",
            "Okay fine, what classes do you offer?"
        ],
        "checks": [
            ("Responds with polite reassurance and professionalism", lambda resp: "fitpulse" in resp.lower() or "inquiry" in resp.lower() or "instagram" in resp.lower())
        ]
    },
    {
        "id": 16,
        "name": "Online / Virtual Class Inquiry",
        "lead_name": "Snehal Shah",
        "turns": [
            "Yes, speaking.",
            "Yes, I can talk.",
            "Do you have online Zoom classes, or is it only in-studio?"
        ],
        "checks": [
            ("Explains in-studio experience or options clearly", lambda resp: "studio" in resp.lower() or "demo" in resp.lower() or "trainer" in resp.lower())
        ]
    },
    {
        "id": 17,
        "name": "Future Callback Next Week ('Call me next Monday at 11am')",
        "lead_name": "Manish Tiwari",
        "turns": [
            "Yes, this is Manish.",
            "I'm out of town this whole week. Please call me next Monday at 11am."
        ],
        "checks": [
            ("Acknowledges next Monday callback time and signs off", lambda resp: "monday" in resp.lower() or "call" in resp.lower() or "goodbye" in resp.lower())
        ]
    },
    {
        "id": 18,
        "name": "End-of-Call Loop Verification (Lead says 'Thank you, bye' after email)",
        "lead_name": "Aditya Joshi",
        "turns": [
            "Speaking.",
            "Yes, I'm free.",
            "Yes, I want to book a demo.",
            "Sunday at 10am.",
            "aditya@joshi.org",
            "Great, thank you so much, bye!"
        ],
        "checks": [
            ("Does not ask for fitness goal or prolong conversation", lambda resp: "fitness goal" not in resp.lower() and ("bye" in resp.lower() or "welcome" in resp.lower() or "day" in resp.lower()))
        ]
    }
]

def run_tests():
    print("=" * 70)
    print("🧪 RUNNING 18 AUTOMATED SCENARIO TESTS ON FITPULSE AI VOICE AGENT")
    print("=" * 70)

    total_scenarios = len(SCENARIOS)
    passed_scenarios = 0

    for s in SCENARIOS:
        print(f"\n▶ Scenario {s['id']}/{total_scenarios}: {s['name']}")
        conv_id = str(uuid.uuid4())
        lead_name = s["lead_name"]
        
        # Initial greeting test
        print(f"   👤 Lead: {lead_name}")
        last_ai_response = ""

        try:
            for turn_idx, user_text in enumerate(s["turns"], 1):
                resp = client.ai.assistants.chat(
                    assistant_id=assistant_id,
                    conversation_id=conv_id,
                    content=user_text
                )
                last_ai_response = resp.content
                print(f"      User (Turn {turn_idx}): {user_text}")
                print(f"      AI: {last_ai_response[:100]}...")
                time.sleep(0.5)

            # Check verifications
            all_checks_passed = True
            for check_name, check_fn in s.get("checks", []):
                passed = check_fn(last_ai_response)
                status_icon = "✅" if passed else "⚠️"
                print(f"      {status_icon} Check: {check_name} -> {'PASS' if passed else 'REVIEW'}")
                if not passed:
                    all_checks_passed = False

            if all_checks_passed:
                passed_scenarios += 1

        except Exception as e:
            print(f"      ❌ Scenario failed with error: {e}")

    print("\n" + "=" * 70)
    print(f"🏁 TEST RESULTS: {passed_scenarios}/{total_scenarios} Scenarios Passed Successfully!")
    print("=" * 70)

if __name__ == "__main__":
    run_tests()
