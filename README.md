# LeadPulse.ai — AI Outbound Voice Caller

**LeadPulse.ai** is an AI lead-calling platform built on Telnyx AI Assistants. It finds and dials leads, checks availability before pitching, handles objections, qualifies interest, and helps book meetings — with natural spoken times and dates.

---

## Conversational Flow Architecture

1. **Identity Confirmation:**
   - *"Hi, this is Alex calling from FitPulse Studio. Am I speaking with {name}?"*
2. **Availability Check (Mandatory BEFORE Pitch):**
   - *"Great! Are you available to chat for a couple of minutes right now, or did I catch you at a busy time?"*
   - *If busy / in a meeting / driving:* Respects their time, asks for a callback window, and concludes without pushing.
3. **Reason for Call & Interest Check:**
   - *"Awesome. The reason I'm reaching out is that you recently interacted with our Instagram ad regarding our fitness classes. I just wanted to check if you're still interested in exploring our fitness classes or getting enrolled in one of them?"*
4. **Complimentary Demo Class Pitch:**
   - *On positive intent:* Enthusiastically offers a free demo session to experience the workouts and studio vibe before deciding.
5. **Session Scheduling:**
   - Coordinates morning or evening slots and days.
6. **Phonetic Time Pronunciation:**
   - Pronounces times naturally (e.g., *"five thirty in the evening"*, *"ten o'clock in the morning"*) instead of robotic numbers like *"5:30"* or *"five three zero"*.

---

## Project Structure & Tools

| Script | Purpose |
| :--- | :--- |
| **`simulator.py`** | **Test the AI conversation interactively in terminal** without phone calls. |
| **`run_scenario_tests.py`** | **Run 18 automated edge-case scenario tests** (busy, driving, Saturday unavailable, price, etc.). |
| **`set_language.py`** | **1-command language switcher** to toggle between **English** and **Hinglish** based on client requirements. |
| **`update_assistant.py`** | Pushes the updated prompt, Stage 6 ending, and disabled expressive mode to Telnyx. |
| **`caller.py`** | Production outbound caller that reads `leads.csv` in batches and places calls. |
| **`call_insights.py`** | Fetches call logs, transcripts, and conversation outcomes from Telnyx. |
| **`setup.py`** | Provisions Telnyx voice infrastructure (TeXML, Outbound Profile, Assistant). |

---

## Web Dashboard (recommended for team use)

```bash
# Terminal 1 — API
pip install -r requirements.txt
python webapp/server.py

# Terminal 2 — UI
cd webapp/dashboard
npm install
npm run dev
```

Open http://localhost:3000 — login `admin@leadpulse.ai` / `admin123`  
Details: [webapp/PLATFORM.md](webapp/PLATFORM.md)

## Quickstart Guide (CLI)

### 1. Run the 18 Automated Scenario Tests
Validate all edge cases, objection handling, Saturday unavailability, and clean call endings:
```bash
python run_scenario_tests.py
```

### 2. Test Conversation Interactively in Terminal
```bash
python simulator.py
```

### 2. Switch Between English & Hinglish on Demand
Whenever your client requests Hinglish (or back to English):
```bash
# Set to English (default)
python set_language.py --lang english

# Switch to Hinglish (Indian English + Hindi blend)
python set_language.py --lang hinglish
```

### 3. Review Leads (`leads.csv`)
Edit `leads.csv` with the leads you want to call:
```csv
name,phone,business_name,fitness_goal,preferred_time,lead_source
Rahul Sharma,+918433198122,FitPulse Studio,Weight Loss & Strength,evening,Instagram ad
Jane Doe,+12125550101,FitPulse Studio,HIIT & Yoga,morning,Instagram ad
```

### 4. Run Outbound Calling (When phone number is configured)
```bash
python caller.py
```

### 5. View Transcripts & Call Reports
```bash
python call_insights.py
```
