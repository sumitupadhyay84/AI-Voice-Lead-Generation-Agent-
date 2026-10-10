import os
import csv
import time
from datetime import datetime, timezone, timedelta
import dotenv
from telnyx import Telnyx

def log_call(log_file, lead_name, phone, event_id, status):
    """Writes the call attempt to a CSV log file."""
    file_exists = os.path.exists(log_file)
    with open(log_file, 'a', newline='') as csvfile:
        writer = csv.writer(csvfile)
        if not file_exists:
            writer.writerow(['timestamp', 'lead_name', 'phone', 'event_id', 'status'])
        writer.writerow([datetime.now().isoformat(), lead_name, phone, event_id, status])

def chunk_list(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

def main():
    print("🚀 Starting FitPulse AI Outbound Lead Caller...")
    dotenv.load_dotenv()
    
    api_key = os.environ.get("TELNYX_API_KEY")
    agent_number = os.environ.get("TELNYX_PHONE_NUMBER")
    assistant_id = os.environ.get("TELNYX_ASSISTANT_ID")
    leads_file = os.environ.get("LEADS_FILE", "leads.csv")
    batch_size = int(os.environ.get("BATCH_SIZE", 2))
    batch_delay = int(os.environ.get("BATCH_DELAY_SECONDS", 20))
    log_file = "call_log.csv"
    
    if not all([api_key, agent_number, assistant_id]):
        print("❌ Missing required environment variables. Please run setup.py first.")
        return

    client = Telnyx(api_key=api_key)
    
    if not os.path.exists(leads_file):
        print(f"❌ Leads file not found: {leads_file}")
        return

    leads = []
    with open(leads_file, 'r') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
             leads.append(row)
             
    print(f"Found {len(leads)} leads in {leads_file}.")
    print(f"Settings: Batch Size = {batch_size}, Delay Between Batches = {batch_delay}s")
    print("-" * 50)

    batches = list(chunk_list(leads, batch_size))
    
    for batch_idx, batch in enumerate(batches):
        print(f"\n📦 Starting Batch {batch_idx + 1} of {len(batches)} ({len(batch)} leads)")
        
        for lead in batch:
            name = lead.get('name', 'Customer')
            phone = lead.get('phone')
            
            if not phone:
                 print(f"⚠️ Skipping lead {name} - No phone number provided.")
                 continue
                 
            print(f"   -> Preparing to call {name} ({phone}) regarding fitness classes...")
            
            try:
                # Trigger the call ~5 seconds in the future
                scheduled_time = (datetime.now(timezone.utc) + timedelta(seconds=5)).isoformat()
                
                # Pass all CSV data to the AI assistant using dynamic_variables
                event = client.ai.assistants.scheduled_events.create(
                    assistant_id=assistant_id,
                    telnyx_conversation_channel="phone_call",
                    telnyx_end_user_target=phone,
                    telnyx_agent_target=agent_number,
                    scheduled_at_fixed_datetime=scheduled_time,
                    dynamic_variables=lead  # Passes the entire CSV row as a dict
                )
                print(f"      ✅ Call scheduled. Event ID: {event.id} (Status: {event.status})")
                log_call(log_file, name, phone, event.id, event.status)
                
            except Exception as e:
                 print(f"      ❌ Failed to schedule call: {e}")
                 log_call(log_file, name, phone, "ERROR", str(e))
                 
        if batch_idx < len(batches) - 1:
             print(f"\n⏳ Waiting {batch_delay} seconds before next batch...")
             time.sleep(batch_delay)
             
    print("-" * 50)
    print(f"🏁 Finished processing {len(leads)} leads. Results saved to {log_file}")

if __name__ == "__main__":
    main()
