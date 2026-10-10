"""
LeadPulse.ai Calling Platform - Flask Backend
Wraps Telnyx AI calling infrastructure into secure REST APIs.
"""
import os
import json
import csv
import uuid
import hashlib
import sqlite3
from datetime import datetime, timezone, timedelta
from functools import wraps

from flask import Flask, request, jsonify, send_from_directory, g
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required,
    get_jwt_identity, get_jwt
)
from werkzeug.security import generate_password_hash, check_password_hash
import dotenv

dotenv.load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

app = Flask(__name__, static_folder='../frontend', static_url_path='')
app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', 'leadpulse-secret-change-in-prod-2026')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=8)
_cors_origins = os.environ.get('CORS_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000').split(',')
CORS(app, resources={r"/api/*": {"origins": _cors_origins + ["*"]}}, supports_credentials=True)
jwt = JWTManager(app)

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'platform.db')

# ─── Database ──────────────────────────────────────────────────────────────────

def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    db = get_db()
    db.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        name TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'operator',
        workspace_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS workspaces (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        owner_id TEXT NOT NULL,
        plan TEXT DEFAULT 'free',
        plan_expires_at TEXT,
        created_at TEXT NOT NULL,
        settings TEXT DEFAULT '{}'
    );
    CREATE TABLE IF NOT EXISTS leads (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        name TEXT,
        phone TEXT NOT NULL,
        email TEXT,
        business_name TEXT,
        fitness_goal TEXT,
        preferred_time TEXT,
        lead_source TEXT,
        status TEXT DEFAULT 'new',
        last_call_date TEXT,
        call_attempts INTEGER DEFAULT 0,
        last_outcome TEXT,
        created_at TEXT NOT NULL,
        notes TEXT,
        campaign_id TEXT,
        UNIQUE(workspace_id, phone)
    );
    CREATE TABLE IF NOT EXISTS campaigns (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        name TEXT NOT NULL,
        description TEXT,
        assistant_id TEXT,
        agent_number TEXT,
        status TEXT DEFAULT 'draft',
        batch_size INTEGER DEFAULT 2,
        delay_seconds INTEGER DEFAULT 20,
        total_leads INTEGER DEFAULT 0,
        called_leads INTEGER DEFAULT 0,
        failed_leads INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        started_at TEXT,
        completed_at TEXT,
        created_by TEXT
    );
    CREATE TABLE IF NOT EXISTS calls (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        campaign_id TEXT,
        lead_id TEXT,
        lead_name TEXT,
        phone TEXT,
        direction TEXT DEFAULT 'outbound',
        status TEXT DEFAULT 'queued',
        outcome TEXT,
        event_id TEXT,
        agent_number TEXT,
        assistant_id TEXT,
        started_at TEXT,
        ended_at TEXT,
        duration_seconds INTEGER,
        recording_url TEXT,
        transcript TEXT,
        error_msg TEXT,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS audit_log (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        user_id TEXT,
        action TEXT NOT NULL,
        resource_type TEXT,
        resource_id TEXT,
        details TEXT,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS calling_slots (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        name TEXT,
        days TEXT,
        start_time TEXT,
        end_time TEXT,
        timezone TEXT DEFAULT 'Asia/Kolkata',
        is_enabled INTEGER DEFAULT 1,
        created_at TEXT NOT NULL
    );
    """)
    db.commit()
    # Seed default admin if no users exist
    existing = db.execute("SELECT COUNT(*) as cnt FROM users").fetchone()
    if existing['cnt'] == 0:
        ws_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        db.execute("INSERT INTO workspaces VALUES (?,?,?,?,?,?,?)",
                   (ws_id, 'LeadPulse', user_id, 'pro',
                    (datetime.now(timezone.utc) + timedelta(days=365)).isoformat(),
                    now, '{}'))
        db.execute("INSERT INTO users VALUES (?,?,?,?,?,?,?,?)",
                   (user_id, 'admin@leadpulse.ai',
                    generate_password_hash('admin123'),
                    'Admin User', 'owner', ws_id, now, 1))
        db.commit()
    # Soft rebrand existing seed accounts / workspace names
    db.execute(
        "UPDATE users SET email=? WHERE email=? AND is_active=1",
        ('admin@leadpulse.ai', 'admin@fitpulse.com')
    )
    db.execute(
        "UPDATE workspaces SET name=? WHERE name IN (?, ?)",
        ('LeadPulse', 'FitPulse Studio', 'FitPulse')
    )
    db.commit()
    db.close()
    ensure_extra_tables()

# ─── Helpers ──────────────────────────────────────────────────────────────────

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def audit(workspace_id, user_id, action, resource_type=None, resource_id=None, details=None):
    db = get_db()
    db.execute("INSERT INTO audit_log VALUES (?,?,?,?,?,?,?,?)",
               (str(uuid.uuid4()), workspace_id, user_id, action,
                resource_type, resource_id,
                json.dumps(details) if details else None, now_iso()))
    db.commit()
    db.close()

def get_telnyx_client():
    import telnyx
    return telnyx.Telnyx(api_key=os.environ.get('TELNYX_API_KEY'))

def role_required(*roles):
    def decorator(fn):
        @wraps(fn)
        @jwt_required()
        def wrapper(*args, **kwargs):
            identity = get_jwt_identity()
            db = get_db()
            user = db.execute("SELECT * FROM users WHERE id=?", (identity,)).fetchone()
            db.close()
            if not user or user['role'] not in roles:
                return jsonify(error="Insufficient permissions"), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator

def current_user_and_workspace():
    identity = get_jwt_identity()
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?", (identity,)).fetchone()
    ws = db.execute("SELECT * FROM workspaces WHERE id=?", (user['workspace_id'],)).fetchone() if user else None
    db.close()
    return user, ws

def ensure_extra_tables():
    """Idempotent schema upgrades for billing + call conversation linkage."""
    db = get_db()
    db.executescript("""
    CREATE TABLE IF NOT EXISTS subscriptions (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        plan_id TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        amount INTEGER NOT NULL,
        currency TEXT NOT NULL DEFAULT 'INR',
        provider TEXT DEFAULT 'manual',
        provider_order_id TEXT,
        provider_payment_id TEXT,
        started_at TEXT,
        expires_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS billing_events (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        subscription_id TEXT,
        event_type TEXT NOT NULL,
        payload TEXT,
        created_at TEXT NOT NULL
    );
    """)
    # Add conversation_id column if missing
    cols = [r['name'] for r in db.execute("PRAGMA table_info(calls)").fetchall()]
    if 'conversation_id' not in cols:
        db.execute("ALTER TABLE calls ADD COLUMN conversation_id TEXT")
    db.commit()
    db.close()

def is_within_calling_slots(workspace_id):
    """Return (allowed: bool, reason: str). Empty slots = always allowed."""
    db = get_db()
    slots = db.execute(
        "SELECT * FROM calling_slots WHERE workspace_id=? AND is_enabled=1",
        (workspace_id,)
    ).fetchall()
    db.close()
    if not slots:
        return True, "No slots configured — calling allowed"

    from zoneinfo import ZoneInfo
    day_map = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    for slot in slots:
        try:
            tz = ZoneInfo(slot['timezone'] or 'Asia/Kolkata')
        except Exception:
            tz = timezone.utc
        local_now = datetime.now(tz)
        day_name = day_map[local_now.weekday()]
        days = json.loads(slot['days'] or '[]')
        if day_name not in days:
            continue
        start = slot['start_time'] or '00:00'
        end = slot['end_time'] or '23:59'
        current = local_now.strftime('%H:%M')
        if start <= current <= end:
            return True, f"Within slot '{slot['name']}'"
    return False, "Outside configured calling slots"

def plan_entitled(ws):
    """True if workspace has an active (non-expired) paid/pro plan or seed plan."""
    if not ws:
        return False
    plan = (ws['plan'] or 'free').lower()
    if plan in ('free', 'expired'):
        return False
    expires = ws['plan_expires_at']
    if expires:
        try:
            exp = datetime.fromisoformat(expires.replace('Z', '+00:00'))
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > exp:
                return False
        except Exception:
            pass
    return True

# ─── Auth routes ──────────────────────────────────────────────────────────────

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    # Accept legacy FitPulse seed email during rebrand
    if email == 'admin@fitpulse.com':
        email = 'admin@leadpulse.ai'
    password = data.get('password', '')
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE email=? AND is_active=1", (email,)).fetchone()
    if not user and email == 'admin@leadpulse.ai':
        user = db.execute(
            "SELECT * FROM users WHERE email=? AND is_active=1", ('admin@fitpulse.com',)
        ).fetchone()
        if user:
            db.execute("UPDATE users SET email=? WHERE id=?", ('admin@leadpulse.ai', user['id']))
            db.commit()
            user = db.execute("SELECT * FROM users WHERE id=?", (user['id'],)).fetchone()
    db.close()
    if not user or not check_password_hash(user['password_hash'], password):
        return jsonify(error="Invalid credentials"), 401
    token = create_access_token(identity=user['id'], additional_claims={'role': user['role'], 'workspace_id': user['workspace_id']})
    return jsonify(token=token, user=dict(id=user['id'], name=user['name'], email=user['email'], role=user['role'], workspace_id=user['workspace_id']))

@app.route('/api/auth/me', methods=['GET'])
@jwt_required()
def me():
    user, ws = current_user_and_workspace()
    if not user:
        return jsonify(error="Not found"), 404
    return jsonify(
        user=dict(id=user['id'], name=user['name'], email=user['email'], role=user['role'], workspace_id=user['workspace_id']),
        workspace=dict(id=ws['id'], name=ws['name'], plan=ws['plan'], plan_expires_at=ws['plan_expires_at']) if ws else None
    )

@app.route('/api/auth/change-password', methods=['POST'])
@jwt_required()
def change_password():
    data = request.get_json() or {}
    user, _ = current_user_and_workspace()
    if not check_password_hash(user['password_hash'], data.get('current_password', '')):
        return jsonify(error="Current password incorrect"), 400
    new_hash = generate_password_hash(data['new_password'])
    db = get_db()
    db.execute("UPDATE users SET password_hash=? WHERE id=?", (new_hash, user['id']))
    db.commit()
    db.close()
    return jsonify(message="Password changed")

# ─── Dashboard / Overview ─────────────────────────────────────────────────────

@app.route('/api/dashboard/stats', methods=['GET'])
@jwt_required()
def dashboard_stats():
    user, ws = current_user_and_workspace()
    ws_id = ws['id']
    today = datetime.now(timezone.utc).date().isoformat()
    db = get_db()

    total_leads = db.execute("SELECT COUNT(*) as c FROM leads WHERE workspace_id=?", (ws_id,)).fetchone()['c']
    ready_leads = db.execute("SELECT COUNT(*) as c FROM leads WHERE workspace_id=? AND status='new'", (ws_id,)).fetchone()['c']
    active_campaigns = db.execute("SELECT COUNT(*) as c FROM campaigns WHERE workspace_id=? AND status='running'", (ws_id,)).fetchone()['c']
    calls_today = db.execute("SELECT COUNT(*) as c FROM calls WHERE workspace_id=? AND created_at LIKE ?", (ws_id, f'{today}%')).fetchone()['c']
    completed_today = db.execute("SELECT COUNT(*) as c FROM calls WHERE workspace_id=? AND status='completed' AND created_at LIKE ?", (ws_id, f'{today}%')).fetchone()['c']
    failed_today = db.execute("SELECT COUNT(*) as c FROM calls WHERE workspace_id=? AND status='failed' AND created_at LIKE ?", (ws_id, f'{today}%')).fetchone()['c']
    total_calls = db.execute("SELECT COUNT(*) as c FROM calls WHERE workspace_id=?", (ws_id,)).fetchone()['c']
    total_campaigns = db.execute("SELECT COUNT(*) as c FROM campaigns WHERE workspace_id=?", (ws_id,)).fetchone()['c']
    completed_all = db.execute("SELECT COUNT(*) as c FROM calls WHERE workspace_id=? AND status='completed'", (ws_id,)).fetchone()['c']
    failed_all = db.execute("SELECT COUNT(*) as c FROM calls WHERE workspace_id=? AND status='failed'", (ws_id,)).fetchone()['c']
    inbound_count = db.execute("SELECT COUNT(*) as c FROM calls WHERE workspace_id=? AND direction='inbound'", (ws_id,)).fetchone()['c']
    outbound_count = db.execute("SELECT COUNT(*) as c FROM calls WHERE workspace_id=? AND direction='outbound'", (ws_id,)).fetchone()['c']
    avg_row = db.execute(
        "SELECT AVG(duration_seconds) as avg_d FROM calls WHERE workspace_id=? AND duration_seconds IS NOT NULL",
        (ws_id,)
    ).fetchone()
    avg_duration = round(avg_row['avg_d'] or 0, 1)

    outcome_rows = db.execute(
        """SELECT COALESCE(outcome, status) as outcome, COUNT(*) as c FROM calls
           WHERE workspace_id=? GROUP BY COALESCE(outcome, status) ORDER BY c DESC LIMIT 8""",
        (ws_id,)
    ).fetchall()

    # Recent calls (last 7 days)
    recent_calls = db.execute(
        "SELECT * FROM calls WHERE workspace_id=? ORDER BY created_at DESC LIMIT 10", (ws_id,)
    ).fetchall()
    recent_campaigns = db.execute(
        "SELECT * FROM campaigns WHERE workspace_id=? ORDER BY created_at DESC LIMIT 5", (ws_id,)
    ).fetchall()
    attention = db.execute(
        """SELECT * FROM calls WHERE workspace_id=? AND status IN ('failed','error')
           ORDER BY created_at DESC LIMIT 8""",
        (ws_id,)
    ).fetchall()

    # Daily trend last 7 days (inbound vs outbound)
    trend = []
    for i in range(6, -1, -1):
        day = (datetime.now(timezone.utc) - timedelta(days=i)).date().isoformat()
        out_c = db.execute(
            "SELECT COUNT(*) as c FROM calls WHERE workspace_id=? AND direction='outbound' AND created_at LIKE ?",
            (ws_id, f'{day}%')
        ).fetchone()['c']
        in_c = db.execute(
            "SELECT COUNT(*) as c FROM calls WHERE workspace_id=? AND direction='inbound' AND created_at LIKE ?",
            (ws_id, f'{day}%')
        ).fetchone()['c']
        trend.append({'date': day, 'calls': out_c + in_c, 'outbound': out_c, 'inbound': in_c})

    db.close()

    # Telnyx balance
    balance = None
    balance_currency = None
    balance_refreshed_at = None
    try:
        import requests as req
        r = req.get('https://api.telnyx.com/v2/balance',
                    headers={'Authorization': f"Bearer {os.environ.get('TELNYX_API_KEY')}"}, timeout=5)
        if r.status_code == 200:
            bdata = r.json().get('data', {})
            balance = bdata.get('balance')
            balance_currency = bdata.get('currency')
            balance_refreshed_at = now_iso()
    except Exception:
        pass

    return jsonify(
        total_leads=total_leads,
        ready_leads=ready_leads,
        active_campaigns=active_campaigns,
        calls_today=calls_today,
        completed_today=completed_today,
        failed_today=failed_today,
        total_calls=total_calls,
        total_campaigns=total_campaigns,
        completed_calls=completed_all,
        failed_calls=failed_all,
        successful_connections=completed_all,
        inbound_calls=inbound_count,
        outbound_calls=outbound_count,
        avg_duration_seconds=avg_duration,
        outcome_distribution=[{'outcome': r['outcome'], 'count': r['c']} for r in outcome_rows],
        telnyx_balance=balance,
        telnyx_balance_currency=balance_currency,
        balance_refreshed_at=balance_refreshed_at,
        plan=ws['plan'],
        plan_expires_at=ws['plan_expires_at'],
        entitled=plan_entitled(ws),
        trend=trend,
        recent_calls=[dict(r) for r in recent_calls],
        recent_campaigns=[dict(r) for r in recent_campaigns],
        attention_calls=[dict(r) for r in attention],
    )

def _classify_lead_temperature(lead):
    """
    Map existing lead fields to hot/warm/cold.
    Uses last_outcome + status only — no invented scores.
    Returns (bucket, label, reason).
    """
    outcome = (lead['last_outcome'] or '').strip().lower()
    status = (lead['status'] or 'new').strip().lower()
    text = f"{outcome} {status}"

    hot_keys = ('interested', 'meeting', 'booked', 'demo', 'qualified', 'hot', 'yes', 'enroll')
    warm_keys = ('follow', 'callback', 'busy', 'later', 'warm', 'considering', 'callback', 'reschedule')
    cold_keys = ('not interested', 'declined', 'dnc', 'do not call', 'cold', 'no answer', 'failed', 'rejected')

    if any(k in text for k in hot_keys):
        return 'hot', 'Hot', f"Matched outcome/status: {outcome or status}"
    if any(k in text for k in cold_keys):
        return 'cold', 'Cold', f"Matched outcome/status: {outcome or status}"
    if any(k in text for k in warm_keys) or status == 'called':
        return 'warm', 'Warm', f"Contacted / follow-up signals ({outcome or status})"
    # Never called — nurturing pool
    return 'cold', 'Cold', f"Not yet qualified (status={status})"

def _is_meeting_outcome(text):
    t = (text or '').lower()
    return any(k in t for k in ('meeting', 'booked', 'demo scheduled', 'appointment', 'enrolled'))

def _summarize_call(call):
    """Build a short summary from stored transcript/outcome — never fabricate content."""
    if call['outcome']:
        return call['outcome']
    transcript = call['transcript'] or ''
    if transcript.strip():
        lines = [ln.strip() for ln in transcript.split('\n') if ln.strip()]
        # Prefer last non-empty lines as a compact summary snippet
        snippet = ' · '.join(lines[-3:]) if lines else ''
        return snippet[:280] if snippet else None
    if call['status'] == 'scheduled':
        return 'Call scheduled — waiting for completion'
    if call['status'] == 'failed':
        return call['error_msg'] or 'Call failed'
    if call['status'] == 'cancelled':
        return 'Call cancelled'
    return None

@app.route('/api/dashboard/lead-gen', methods=['GET'])
@jwt_required()
def dashboard_lead_gen():
    """Overview payload for the AI Lead Generation landing dashboard."""
    user, ws = current_user_and_workspace()
    ws_id = ws['id']
    db = get_db()

    leads = db.execute(
        "SELECT * FROM leads WHERE workspace_id=? ORDER BY created_at DESC", (ws_id,)
    ).fetchall()
    lead_status_rows = db.execute(
        "SELECT status, COUNT(*) as c FROM leads WHERE workspace_id=? GROUP BY status", (ws_id,)
    ).fetchall()

    hot = warm = cold = 0
    qualified = 0
    for lead in leads:
        bucket, _, _ = _classify_lead_temperature(lead)
        if bucket == 'hot':
            hot += 1
            qualified += 1
        elif bucket == 'warm':
            warm += 1
        else:
            cold += 1

    total_leads = len(leads)
    ready_leads = sum(1 for l in leads if (l['status'] or '') == 'new')

    inbound = db.execute(
        "SELECT COUNT(*) as c FROM calls WHERE workspace_id=? AND direction='inbound'", (ws_id,)
    ).fetchone()['c']
    outbound = db.execute(
        "SELECT COUNT(*) as c FROM calls WHERE workspace_id=? AND direction='outbound'", (ws_id,)
    ).fetchone()['c']
    connected = db.execute(
        "SELECT COUNT(*) as c FROM calls WHERE workspace_id=? AND status='completed'", (ws_id,)
    ).fetchone()['c']
    active_calls = db.execute(
        """SELECT COUNT(*) as c FROM calls WHERE workspace_id=?
           AND status IN ('scheduled','queued','ringing','in_progress','answered')""",
        (ws_id,)
    ).fetchone()['c']

    meeting_ids = set()
    for lead in leads:
        if _is_meeting_outcome(lead['last_outcome']):
            meeting_ids.add(f"lead:{lead['id']}")
    for c in db.execute(
        "SELECT id, lead_id, outcome FROM calls WHERE workspace_id=?", (ws_id,)
    ).fetchall():
        if _is_meeting_outcome(c['outcome']):
            meeting_ids.add(f"lead:{c['lead_id']}" if c['lead_id'] else f"call:{c['id']}")
    meetings_booked = len(meeting_ids)

    recent_calls = db.execute(
        "SELECT * FROM calls WHERE workspace_id=? ORDER BY created_at DESC LIMIT 8", (ws_id,)
    ).fetchall()
    insight_calls = []
    for c in recent_calls:
        cd = dict(c)
        summary = _summarize_call(c)
        follow_up = None
        outcome_l = (c['outcome'] or '').lower()
        if any(k in outcome_l for k in ('follow', 'callback', 'busy', 'later')):
            follow_up = c['outcome']
        elif c['status'] == 'failed':
            follow_up = 'Retry or review failure reason'
        insight_calls.append({
            **cd,
            'summary': summary,
            'follow_up': follow_up,
            'has_recording': bool(c['recording_url']),
            'has_transcript': bool(c['transcript']),
        })

    sample_out = []
    for l in leads[:5]:
        bucket, label, reason = _classify_lead_temperature(l)
        sample_out.append({
            **dict(l),
            'temperature': bucket,
            'temperature_label': label,
            'temperature_reason': reason,
        })

    db.close()

    # Agent availability from Telnyx (best-effort)
    agent = None
    try:
        client = get_telnyx_client()
        aid = os.environ.get('TELNYX_ASSISTANT_ID')
        if aid:
            a = client.ai.assistants.retrieve(aid)
            agent = {
                'id': a.id,
                'name': getattr(a, 'name', '') or 'LeadPulse Agent',
                'model': getattr(a, 'model', ''),
                'greeting': getattr(a, 'greeting', ''),
                'available': True,
            }
        else:
            agents = client.ai.assistants.list()
            if agents.data:
                a = agents.data[0]
                agent = {
                    'id': a.id,
                    'name': getattr(a, 'name', '') or 'AI Agent',
                    'model': getattr(a, 'model', ''),
                    'greeting': getattr(a, 'greeting', ''),
                    'available': True,
                }
    except Exception as e:
        agent = {
            'id': os.environ.get('TELNYX_ASSISTANT_ID'),
            'name': 'AI Agent',
            'available': False,
            'error': str(e)[:160],
        }

    denom = total_leads if total_leads > 0 else 0
    def pct(n):
        return round((n / denom) * 100, 1) if denom else 0.0

    allowed, slot_reason = is_within_calling_slots(ws_id)

    return jsonify(
        headline='AI Lead Generation',
        total_leads=total_leads,
        ready_leads=ready_leads,
        lead_statuses=[{'status': r['status'] or 'unknown', 'count': r['c']} for r in lead_status_rows],
        sample_leads=sample_out,
        qualification={
            'hot': hot,
            'warm': warm,
            'cold': cold,
            'hot_pct': pct(hot),
            'warm_pct': pct(warm),
            'cold_pct': pct(cold),
            'rules': {
                'hot': 'last_outcome/status contains interested, meeting, booked, demo, qualified',
                'warm': 'called / follow-up / callback signals',
                'cold': 'not interested, failed, or not yet contacted',
            },
        },
        metrics={
            'total_leads': total_leads,
            'inbound_calls': inbound,
            'outbound_calls': outbound,
            'connected_calls': connected,
            'qualified_leads': qualified,
            'meetings_booked': meetings_booked,
            'active_calls': active_calls,
        },
        agent=agent,
        calling_window={'allowed': allowed, 'reason': slot_reason},
        phone_configured=bool(os.environ.get('TELNYX_PHONE_NUMBER')),
        recent_insights=insight_calls,
    )

# ─── Leads ────────────────────────────────────────────────────────────────────

@app.route('/api/leads', methods=['GET'])
@jwt_required()
def list_leads():
    user, ws = current_user_and_workspace()
    ws_id = ws['id']
    search = request.args.get('search', '')
    status = request.args.get('status', '')
    page = max(1, int(request.args.get('page', 1)))
    per_page = min(100, int(request.args.get('per_page', 25)))
    offset = (page - 1) * per_page

    db = get_db()
    where = "WHERE workspace_id=?"
    params = [ws_id]
    if search:
        where += " AND (name LIKE ? OR phone LIKE ? OR email LIKE ?)"
        params += [f'%{search}%', f'%{search}%', f'%{search}%']
    if status:
        where += " AND status=?"
        params.append(status)

    total = db.execute(f"SELECT COUNT(*) as c FROM leads {where}", params).fetchone()['c']
    rows = db.execute(f"SELECT * FROM leads {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                      params + [per_page, offset]).fetchall()
    db.close()
    return jsonify(leads=[dict(r) for r in rows], total=total, page=page, per_page=per_page)

@app.route('/api/leads', methods=['POST'])
@jwt_required()
def create_lead():
    user, ws = current_user_and_workspace()
    data = request.get_json() or {}
    if not data.get('phone'):
        return jsonify(error="Phone is required"), 400
    db = get_db()
    lead_id = str(uuid.uuid4())
    try:
        db.execute("""INSERT INTO leads VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                   (lead_id, ws['id'], data.get('name'), data['phone'], data.get('email'),
                    data.get('business_name'), data.get('fitness_goal'), data.get('preferred_time'),
                    data.get('lead_source'), data.get('status', 'new'), None, 0, None,
                    now_iso(), data.get('notes'), data.get('campaign_id')))
        db.commit()
    except sqlite3.IntegrityError:
        db.close()
        return jsonify(error="Lead with this phone number already exists"), 409
    db.close()
    audit(ws['id'], user['id'], 'create_lead', 'lead', lead_id, {'phone': data['phone']})
    return jsonify(id=lead_id, message="Lead created"), 201

@app.route('/api/leads/<lead_id>', methods=['PUT'])
@jwt_required()
def update_lead(lead_id):
    user, ws = current_user_and_workspace()
    data = request.get_json() or {}
    db = get_db()
    fields = ['name', 'phone', 'email', 'business_name', 'fitness_goal',
              'preferred_time', 'lead_source', 'status', 'notes', 'campaign_id']
    sets = ', '.join(f"{f}=?" for f in fields if f in data)
    vals = [data[f] for f in fields if f in data]
    if sets:
        db.execute(f"UPDATE leads SET {sets} WHERE id=? AND workspace_id=?",
                   vals + [lead_id, ws['id']])
        db.commit()
    db.close()
    return jsonify(message="Updated")

@app.route('/api/leads/<lead_id>', methods=['DELETE'])
@jwt_required()
def delete_lead(lead_id):
    user, ws = current_user_and_workspace()
    db = get_db()
    db.execute("DELETE FROM leads WHERE id=? AND workspace_id=?", (lead_id, ws['id']))
    db.commit()
    db.close()
    audit(ws['id'], user['id'], 'delete_lead', 'lead', lead_id)
    return jsonify(message="Deleted")

@app.route('/api/leads/template', methods=['GET'])
@jwt_required()
def leads_template():
    """CSV template for lead import."""
    from flask import Response
    csv_body = (
        "name,phone,email,business_name,fitness_goal,preferred_time,lead_source,notes\n"
        "Rahul Sharma,+918433198122,,LeadPulse,Weight Loss,evening,Import,\n"
    )
    return Response(
        csv_body,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads_template.csv"},
    )

@app.route('/api/leads/import', methods=['POST'])
@jwt_required()
def import_leads():
    """Import leads from JSON array (parsed from CSV on frontend)."""
    user, ws = current_user_and_workspace()
    data = request.get_json() or {}
    rows = data.get('rows', [])
    duplicate_policy = data.get('duplicate_policy', 'skip')  # skip or update

    accepted = 0
    rejected = 0
    duplicates = 0
    errors = []
    db = get_db()
    for i, row in enumerate(rows):
        phone = str(row.get('phone', '')).strip()
        if not phone:
            rejected += 1
            errors.append({'row': i + 1, 'reason': 'Missing phone number'})
            continue
        lead_id = str(uuid.uuid4())
        try:
            db.execute("""INSERT INTO leads VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                       (lead_id, ws['id'], row.get('name'), phone, row.get('email'),
                        row.get('business_name'), row.get('fitness_goal'), row.get('preferred_time'),
                        row.get('lead_source', 'Import'), row.get('status', 'new'),
                        None, 0, None, now_iso(), row.get('notes'), None))
            accepted += 1
        except sqlite3.IntegrityError:
            duplicates += 1
            if duplicate_policy == 'update':
                db.execute("""UPDATE leads SET name=?, email=?, business_name=?, fitness_goal=?,
                              preferred_time=?, lead_source=?, notes=? WHERE workspace_id=? AND phone=?""",
                           (row.get('name'), row.get('email'), row.get('business_name'),
                            row.get('fitness_goal'), row.get('preferred_time'),
                            row.get('lead_source'), row.get('notes'), ws['id'], phone))
                accepted += 1
    db.commit()
    db.close()
    audit(ws['id'], user['id'], 'import_leads', details={'accepted': accepted, 'rejected': rejected})
    return jsonify(accepted=accepted, rejected=rejected, duplicates=duplicates, errors=errors[:20])

# ─── Test-a-Number ────────────────────────────────────────────────────────────

@app.route('/api/calls/test', methods=['POST'])
@jwt_required()
def test_call():
    user, ws = current_user_and_workspace()
    data = request.get_json() or {}
    phone = data.get('phone', '').strip()
    name = data.get('name', 'Test Contact')
    assistant_id = data.get('assistant_id') or os.environ.get('TELNYX_ASSISTANT_ID')
    agent_number = data.get('agent_number') or os.environ.get('TELNYX_PHONE_NUMBER')

    if not phone:
        return jsonify(error="Phone number is required"), 400
    if not agent_number:
        return jsonify(error="Agent phone number not configured. Add TELNYX_PHONE_NUMBER to .env"), 400
    if not assistant_id:
        return jsonify(error="Assistant ID not configured"), 400

    force = bool(data.get('force'))
    allowed, slot_reason = is_within_calling_slots(ws['id'])
    if not allowed and not force:
        return jsonify(error=slot_reason, code='outside_calling_slots'), 403

    try:
        client = get_telnyx_client()
        scheduled_time = (datetime.now(timezone.utc) + timedelta(seconds=5)).isoformat()
        dynamic_vars = {
            'name': name,
            'business_name': ws['name'],
            **(data.get('variables', {}))
        }
        event = client.ai.assistants.scheduled_events.create(
            assistant_id=assistant_id,
            telnyx_conversation_channel="phone_call",
            telnyx_end_user_target=phone,
            telnyx_agent_target=agent_number,
            scheduled_at_fixed_datetime=scheduled_time,
            dynamic_variables=dynamic_vars
        )
        call_id = str(uuid.uuid4())
        db = get_db()
        db.execute("""INSERT INTO calls VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                   (call_id, ws['id'], None, None, name, phone, 'outbound',
                    'scheduled', None, event.id, agent_number, assistant_id,
                    scheduled_time, None, None, None, None, None, now_iso()))
        db.commit()
        db.close()
        audit(ws['id'], user['id'], 'test_call', 'call', call_id, {'phone': phone})
        return jsonify(call_id=call_id, event_id=event.id, status='scheduled', message=f"Call scheduled for {phone}")
    except Exception as e:
        return jsonify(error=str(e)), 500

@app.route('/api/calls/status/<event_id>', methods=['GET'])
@jwt_required()
def call_status(event_id):
    try:
        client = get_telnyx_client()
        event = client.ai.assistants.scheduled_events.retrieve(event_id)
        return jsonify(event_id=event_id, status=getattr(event, 'status', 'unknown'),
                       details=str(event))
    except Exception as e:
        return jsonify(event_id=event_id, status='unknown', error=str(e))

# ─── Campaigns ────────────────────────────────────────────────────────────────

@app.route('/api/campaigns', methods=['GET'])
@jwt_required()
def list_campaigns():
    user, ws = current_user_and_workspace()
    db = get_db()
    rows = db.execute("SELECT * FROM campaigns WHERE workspace_id=? ORDER BY created_at DESC",
                      (ws['id'],)).fetchall()
    db.close()
    return jsonify(campaigns=[dict(r) for r in rows])

@app.route('/api/campaigns', methods=['POST'])
@jwt_required()
def create_campaign():
    user, ws = current_user_and_workspace()
    data = request.get_json() or {}
    if not data.get('name'):
        return jsonify(error="Campaign name required"), 400
    camp_id = str(uuid.uuid4())
    assistant_id = data.get('assistant_id') or os.environ.get('TELNYX_ASSISTANT_ID')
    agent_number = data.get('agent_number') or os.environ.get('TELNYX_PHONE_NUMBER')
    db = get_db()
    # Count leads in campaign
    total = db.execute("SELECT COUNT(*) as c FROM leads WHERE workspace_id=? AND status='new'", (ws['id'],)).fetchone()['c']
    db.execute("""INSERT INTO campaigns VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
               (camp_id, ws['id'], data['name'], data.get('description'),
                assistant_id, agent_number,
                'draft', data.get('batch_size', 2), data.get('delay_seconds', 20),
                total, 0, 0, now_iso(), None, None, user['id']))
    db.commit()
    db.close()
    audit(ws['id'], user['id'], 'create_campaign', 'campaign', camp_id, {'name': data['name']})
    return jsonify(id=camp_id, message="Campaign created"), 201

@app.route('/api/campaigns/<camp_id>/launch', methods=['POST'])
@jwt_required()
def launch_campaign(camp_id):
    user, ws = current_user_and_workspace()
    db = get_db()
    camp = db.execute("SELECT * FROM campaigns WHERE id=? AND workspace_id=?", (camp_id, ws['id'])).fetchone()
    if not camp:
        db.close()
        return jsonify(error="Campaign not found"), 404
    if camp['status'] == 'running':
        db.close()
        return jsonify(error="Campaign already running"), 409

    force = bool((request.get_json() or {}).get('force'))
    allowed, slot_reason = is_within_calling_slots(ws['id'])
    if not allowed and not force:
        db.close()
        return jsonify(error=slot_reason, code='outside_calling_slots'), 403

    agent_number = camp['agent_number'] or os.environ.get('TELNYX_PHONE_NUMBER')
    assistant_id = camp['assistant_id'] or os.environ.get('TELNYX_ASSISTANT_ID')

    if not agent_number:
        db.close()
        return jsonify(error="Agent phone number not configured"), 400

    # Get new leads
    leads = db.execute(
        "SELECT * FROM leads WHERE workspace_id=? AND status='new' ORDER BY created_at ASC",
        (ws['id'],)
    ).fetchall()

    db.execute("UPDATE campaigns SET status='running', started_at=?, total_leads=? WHERE id=?",
               (now_iso(), len(leads), camp_id))
    db.commit()

    scheduled = 0
    failed = 0
    delay = camp['delay_seconds'] or 20
    client = get_telnyx_client()

    for idx, lead in enumerate(leads):
        try:
            sched_time = (datetime.now(timezone.utc) + timedelta(seconds=5 + idx * delay)).isoformat()
            dynamic_vars = {k: lead[k] for k in lead.keys() if lead[k] is not None}
            dynamic_vars['business_name'] = ws['name']
            event = client.ai.assistants.scheduled_events.create(
                assistant_id=assistant_id,
                telnyx_conversation_channel="phone_call",
                telnyx_end_user_target=lead['phone'],
                telnyx_agent_target=agent_number,
                scheduled_at_fixed_datetime=sched_time,
                dynamic_variables=dynamic_vars
            )
            call_id = str(uuid.uuid4())
            db.execute("""INSERT INTO calls VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                       (call_id, ws['id'], camp_id, lead['id'], lead['name'], lead['phone'],
                        'outbound', 'scheduled', None, event.id, agent_number, assistant_id,
                        sched_time, None, None, None, None, None, now_iso()))
            db.execute("UPDATE leads SET status='called', last_call_date=?, call_attempts=call_attempts+1, campaign_id=? WHERE id=?",
                       (now_iso(), camp_id, lead['id']))
            scheduled += 1
        except Exception as e:
            failed += 1
            call_id = str(uuid.uuid4())
            db.execute("""INSERT INTO calls VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                       (call_id, ws['id'], camp_id, lead['id'], lead['name'], lead['phone'],
                        'outbound', 'failed', None, None, agent_number, assistant_id,
                        None, None, None, None, None, str(e), now_iso()))

    db.execute("UPDATE campaigns SET called_leads=?, failed_leads=? WHERE id=?",
               (scheduled, failed, camp_id))
    db.commit()
    db.close()
    audit(ws['id'], user['id'], 'launch_campaign', 'campaign', camp_id,
          {'scheduled': scheduled, 'failed': failed})
    return jsonify(message=f"Campaign launched: {scheduled} calls scheduled, {failed} failed",
                   scheduled=scheduled, failed=failed)

@app.route('/api/campaigns/<camp_id>/pause', methods=['POST'])
@jwt_required()
def pause_campaign(camp_id):
    user, ws = current_user_and_workspace()
    db = get_db()
    db.execute("UPDATE campaigns SET status='paused' WHERE id=? AND workspace_id=?", (camp_id, ws['id']))
    db.commit()
    db.close()
    audit(ws['id'], user['id'], 'pause_campaign', 'campaign', camp_id)
    return jsonify(message="Campaign paused. Note: already-scheduled Telnyx events may still fire.")

@app.route('/api/campaigns/<camp_id>/resume', methods=['POST'])
@jwt_required()
def resume_campaign(camp_id):
    user, ws = current_user_and_workspace()
    db = get_db()
    camp = db.execute("SELECT * FROM campaigns WHERE id=? AND workspace_id=?", (camp_id, ws['id'])).fetchone()
    if not camp:
        db.close()
        return jsonify(error="Campaign not found"), 404
    if camp['status'] not in ('paused', 'stopped'):
        db.close()
        return jsonify(error=f"Cannot resume campaign in status '{camp['status']}'"), 400
    db.execute("UPDATE campaigns SET status='running', completed_at=NULL WHERE id=?", (camp_id,))
    db.commit()
    db.close()
    audit(ws['id'], user['id'], 'resume_campaign', 'campaign', camp_id)
    return jsonify(message="Campaign resumed. Launch again to schedule remaining new leads.")

@app.route('/api/campaigns/<camp_id>/stop', methods=['POST'])
@jwt_required()
def stop_campaign(camp_id):
    user, ws = current_user_and_workspace()
    db = get_db()
    # Best-effort cancel pending scheduled events for this campaign
    pending = db.execute(
        "SELECT event_id, assistant_id FROM calls WHERE campaign_id=? AND workspace_id=? AND status='scheduled' AND event_id IS NOT NULL",
        (camp_id, ws['id'])
    ).fetchall()
    cancelled = 0
    try:
        client = get_telnyx_client()
        for row in pending:
            try:
                client.ai.assistants.scheduled_events.delete(
                    assistant_id=row['assistant_id'] or os.environ.get('TELNYX_ASSISTANT_ID'),
                    event_id=row['event_id']
                )
                db.execute("UPDATE calls SET status='cancelled' WHERE event_id=?", (row['event_id'],))
                cancelled += 1
            except Exception:
                pass
    except Exception:
        pass
    db.execute("UPDATE campaigns SET status='stopped', completed_at=? WHERE id=? AND workspace_id=?",
               (now_iso(), camp_id, ws['id']))
    db.commit()
    db.close()
    audit(ws['id'], user['id'], 'stop_campaign', 'campaign', camp_id, {'cancelled_events': cancelled})
    return jsonify(message="Campaign stopped", cancelled_events=cancelled)

@app.route('/api/campaigns/<camp_id>', methods=['GET'])
@jwt_required()
def get_campaign(camp_id):
    user, ws = current_user_and_workspace()
    db = get_db()
    camp = db.execute("SELECT * FROM campaigns WHERE id=? AND workspace_id=?", (camp_id, ws['id'])).fetchone()
    if not camp:
        db.close()
        return jsonify(error="Not found"), 404
    by_status = db.execute(
        "SELECT status, COUNT(*) as c FROM calls WHERE campaign_id=? GROUP BY status", (camp_id,)
    ).fetchall()
    recent = db.execute(
        "SELECT * FROM calls WHERE campaign_id=? ORDER BY created_at DESC LIMIT 20", (camp_id,)
    ).fetchall()
    db.close()
    return jsonify(
        campaign=dict(camp),
        call_counts={r['status']: r['c'] for r in by_status},
        recent_calls=[dict(r) for r in recent]
    )

@app.route('/api/campaigns/<camp_id>', methods=['DELETE'])
@jwt_required()
def delete_campaign(camp_id):
    user, ws = current_user_and_workspace()
    db = get_db()
    db.execute("DELETE FROM campaigns WHERE id=? AND workspace_id=?", (camp_id, ws['id']))
    db.commit()
    db.close()
    audit(ws['id'], user['id'], 'delete_campaign', 'campaign', camp_id)
    return jsonify(message="Deleted")

# ─── Call History ─────────────────────────────────────────────────────────────

@app.route('/api/calls', methods=['GET'])
@jwt_required()
def list_calls():
    user, ws = current_user_and_workspace()
    ws_id = ws['id']
    search = request.args.get('search', '')
    status = request.args.get('status', '')
    direction = request.args.get('direction', '')
    page = max(1, int(request.args.get('page', 1)))
    per_page = min(100, int(request.args.get('per_page', 25)))
    offset = (page - 1) * per_page

    db = get_db()
    where = "WHERE workspace_id=?"
    params = [ws_id]
    if search:
        where += " AND (lead_name LIKE ? OR phone LIKE ?)"
        params += [f'%{search}%', f'%{search}%']
    if status:
        where += " AND status=?"
        params.append(status)
    if direction:
        where += " AND direction=?"
        params.append(direction)

    total = db.execute(f"SELECT COUNT(*) as c FROM calls {where}", params).fetchone()['c']
    rows = db.execute(f"SELECT * FROM calls {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                      params + [per_page, offset]).fetchall()
    db.close()
    return jsonify(calls=[dict(r) for r in rows], total=total, page=page, per_page=per_page)

@app.route('/api/calls/<call_id>', methods=['GET'])
@jwt_required()
def get_call(call_id):
    if call_id in ('live', 'test', 'sync', 'status'):
        return jsonify(error="Not found"), 404
    user, ws = current_user_and_workspace()
    db = get_db()
    call = db.execute("SELECT * FROM calls WHERE id=? AND workspace_id=?", (call_id, ws['id'])).fetchone()
    db.close()
    if not call:
        return jsonify(error="Not found"), 404
    return jsonify(dict(call))

# ─── AI Agents ────────────────────────────────────────────────────────────────

@app.route('/api/agents', methods=['GET'])
@jwt_required()
def list_agents():
    try:
        client = get_telnyx_client()
        agents = client.ai.assistants.list()
        result = []
        for a in agents.data:
            result.append({
                'id': a.id,
                'name': getattr(a, 'name', ''),
                'model': getattr(a, 'model', ''),
                'greeting': getattr(a, 'greeting', ''),
                'created_at': getattr(a, 'created_at', ''),
                'voice': getattr(getattr(a, 'voice_settings', None), 'voice', '') if a else ''
            })
        return jsonify(agents=result)
    except Exception as e:
        return jsonify(error=str(e)), 500

@app.route('/api/agents/<agent_id>', methods=['GET'])
@jwt_required()
def get_agent(agent_id):
    try:
        client = get_telnyx_client()
        a = client.ai.assistants.retrieve(agent_id)
        return jsonify({
            'id': a.id,
            'name': getattr(a, 'name', ''),
            'model': getattr(a, 'model', ''),
            'instructions': getattr(a, 'instructions', ''),
            'greeting': getattr(a, 'greeting', ''),
            'voice_settings': str(getattr(a, 'voice_settings', {})),
            'telephony_settings': str(getattr(a, 'telephony_settings', {}))
        })
    except Exception as e:
        return jsonify(error=str(e)), 500

@app.route('/api/agents/<agent_id>', methods=['PUT'])
@jwt_required()
def update_agent(agent_id):
    user, ws = current_user_and_workspace()
    data = request.get_json() or {}
    try:
        client = get_telnyx_client()
        kwargs = {}
        if 'name' in data: kwargs['name'] = data['name']
        if 'instructions' in data: kwargs['instructions'] = data['instructions']
        if 'greeting' in data: kwargs['greeting'] = data['greeting']
        if 'model' in data: kwargs['model'] = data['model']
        updated = client.ai.assistants.update(agent_id, **kwargs)
        audit(ws['id'], user['id'], 'update_agent', 'agent', agent_id, {'fields': list(kwargs.keys())})
        return jsonify(message="Agent updated", id=updated.id)
    except Exception as e:
        return jsonify(error=str(e)), 500

# ─── Usage & Balance ──────────────────────────────────────────────────────────

@app.route('/api/usage/balance', methods=['GET'])
@jwt_required()
def get_balance():
    try:
        import requests as req
        r = req.get('https://api.telnyx.com/v2/balance',
                    headers={'Authorization': f"Bearer {os.environ.get('TELNYX_API_KEY')}"}, timeout=8)
        if r.status_code == 200:
            return jsonify(r.json().get('data', {}))
        return jsonify(error="Failed to fetch balance", status=r.status_code), 502
    except Exception as e:
        return jsonify(error=str(e)), 500

@app.route('/api/usage/stats', methods=['GET'])
@jwt_required()
def usage_stats():
    user, ws = current_user_and_workspace()
    db = get_db()
    total_calls = db.execute("SELECT COUNT(*) as c FROM calls WHERE workspace_id=?", (ws['id'],)).fetchone()['c']
    completed = db.execute("SELECT COUNT(*) as c FROM calls WHERE workspace_id=? AND status='completed'", (ws['id'],)).fetchone()['c']
    failed = db.execute("SELECT COUNT(*) as c FROM calls WHERE workspace_id=? AND status='failed'", (ws['id'],)).fetchone()['c']
    db.close()
    return jsonify(total_calls=total_calls, completed=completed, failed=failed,
                   plan=ws['plan'], plan_expires_at=ws['plan_expires_at'])

# ─── Phone Numbers ────────────────────────────────────────────────────────────

@app.route('/api/phone-numbers', methods=['GET'])
@jwt_required()
def phone_numbers():
    try:
        client = get_telnyx_client()
        nums = client.phone_numbers.list()
        result = [{'phone_number': n.phone_number, 'status': getattr(n, 'status', ''),
                   'country_code': getattr(n, 'country_code', '')} for n in nums.data]
        return jsonify(phone_numbers=result)
    except Exception as e:
        return jsonify(error=str(e)), 500

@app.route('/api/phone-numbers/available', methods=['GET'])
@jwt_required()
def available_numbers():
    try:
        import requests as req
        country = request.args.get('country', 'US')
        r = req.get(f'https://api.telnyx.com/v2/available_phone_numbers?filter[country_code]={country}&filter[limit]=10',
                    headers={'Authorization': f"Bearer {os.environ.get('TELNYX_API_KEY')}"}, timeout=8)
        if r.status_code == 200:
            return jsonify(numbers=r.json().get('data', []))
        return jsonify(error="Failed to fetch numbers"), 502
    except Exception as e:
        return jsonify(error=str(e)), 500

# ─── Calling Slots ────────────────────────────────────────────────────────────

@app.route('/api/slots', methods=['GET'])
@jwt_required()
def list_slots():
    user, ws = current_user_and_workspace()
    db = get_db()
    rows = db.execute("SELECT * FROM calling_slots WHERE workspace_id=? ORDER BY created_at DESC", (ws['id'],)).fetchall()
    db.close()
    return jsonify(slots=[dict(r) for r in rows])

@app.route('/api/slots', methods=['POST'])
@jwt_required()
def create_slot():
    user, ws = current_user_and_workspace()
    data = request.get_json() or {}
    slot_id = str(uuid.uuid4())
    db = get_db()
    db.execute("INSERT INTO calling_slots VALUES (?,?,?,?,?,?,?,?,?)",
               (slot_id, ws['id'], data.get('name', 'Default Slot'),
                json.dumps(data.get('days', ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'])),
                data.get('start_time', '09:00'), data.get('end_time', '18:00'),
                data.get('timezone', 'Asia/Kolkata'), 1, now_iso()))
    db.commit()
    db.close()
    return jsonify(id=slot_id, message="Slot created"), 201

@app.route('/api/slots/<slot_id>', methods=['PUT'])
@jwt_required()
def update_slot(slot_id):
    user, ws = current_user_and_workspace()
    data = request.get_json() or {}
    db = get_db()
    db.execute("""UPDATE calling_slots SET name=?, days=?, start_time=?, end_time=?, timezone=?, is_enabled=?
                  WHERE id=? AND workspace_id=?""",
               (data.get('name'), json.dumps(data.get('days', [])),
                data.get('start_time'), data.get('end_time'), data.get('timezone'),
                1 if data.get('is_enabled', True) else 0,
                slot_id, ws['id']))
    db.commit()
    db.close()
    return jsonify(message="Slot updated")

@app.route('/api/slots/<slot_id>', methods=['DELETE'])
@jwt_required()
def delete_slot(slot_id):
    user, ws = current_user_and_workspace()
    db = get_db()
    db.execute("DELETE FROM calling_slots WHERE id=? AND workspace_id=?", (slot_id, ws['id']))
    db.commit()
    db.close()
    return jsonify(message="Deleted")

# ─── Team ─────────────────────────────────────────────────────────────────────

@app.route('/api/team', methods=['GET'])
@jwt_required()
def list_team():
    user, ws = current_user_and_workspace()
    if user['role'] not in ['owner', 'admin']:
        return jsonify(error="Insufficient permissions"), 403
    db = get_db()
    rows = db.execute("SELECT id, email, name, role, created_at, is_active FROM users WHERE workspace_id=?",
                      (ws['id'],)).fetchall()
    db.close()
    return jsonify(members=[dict(r) for r in rows])

@app.route('/api/team/invite', methods=['POST'])
@jwt_required()
def invite_member():
    user, ws = current_user_and_workspace()
    if user['role'] not in ['owner', 'admin']:
        return jsonify(error="Insufficient permissions"), 403
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    if not email:
        return jsonify(error="Email required"), 400
    db = get_db()
    existing = db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
    if existing:
        db.close()
        return jsonify(error="User already exists"), 409
    new_id = str(uuid.uuid4())
    temp_pass = generate_password_hash('Welcome@2026')
    db.execute("INSERT INTO users VALUES (?,?,?,?,?,?,?,?)",
               (new_id, email, temp_pass, data.get('name', email), data.get('role', 'operator'),
                ws['id'], now_iso(), 1))
    db.commit()
    db.close()
    audit(ws['id'], user['id'], 'invite_team_member', 'user', new_id, {'email': email})
    return jsonify(id=new_id, message=f"User {email} added. Temp password: Welcome@2026"), 201

@app.route('/api/team/<member_id>', methods=['DELETE'])
@jwt_required()
def remove_member(member_id):
    user, ws = current_user_and_workspace()
    if user['role'] not in ['owner', 'admin']:
        return jsonify(error="Insufficient permissions"), 403
    if member_id == user['id']:
        return jsonify(error="Cannot remove yourself"), 400
    db = get_db()
    db.execute("UPDATE users SET is_active=0 WHERE id=? AND workspace_id=?", (member_id, ws['id']))
    db.commit()
    db.close()
    audit(ws['id'], user['id'], 'remove_team_member', 'user', member_id)
    return jsonify(message="Member deactivated")

# ─── Audit Log ────────────────────────────────────────────────────────────────

@app.route('/api/audit', methods=['GET'])
@jwt_required()
def audit_logs():
    user, ws = current_user_and_workspace()
    if user['role'] not in ['owner', 'admin']:
        return jsonify(error="Insufficient permissions"), 403
    page = max(1, int(request.args.get('page', 1)))
    per_page = 50
    offset = (page - 1) * per_page
    db = get_db()
    rows = db.execute("""SELECT a.*, u.name as user_name FROM audit_log a
                         LEFT JOIN users u ON a.user_id=u.id
                         WHERE a.workspace_id=? ORDER BY a.created_at DESC LIMIT ? OFFSET ?""",
                      (ws['id'], per_page, offset)).fetchall()
    total = db.execute("SELECT COUNT(*) as c FROM audit_log WHERE workspace_id=?", (ws['id'],)).fetchone()['c']
    db.close()
    return jsonify(logs=[dict(r) for r in rows], total=total)

# ─── Settings ─────────────────────────────────────────────────────────────────

@app.route('/api/settings', methods=['GET'])
@jwt_required()
def get_settings():
    user, ws = current_user_and_workspace()
    settings = json.loads(ws['settings'] or '{}')
    settings.update({
        'workspace_name': ws['name'],
        'telnyx_phone_number': os.environ.get('TELNYX_PHONE_NUMBER', ''),
        'assistant_id': os.environ.get('TELNYX_ASSISTANT_ID', ''),
        'batch_size': int(os.environ.get('BATCH_SIZE', 2)),
        'batch_delay': int(os.environ.get('BATCH_DELAY_SECONDS', 20)),
        'call_countries': os.environ.get('CALL_LEAD_COUNTRIES', 'US,IN'),
        'business_name': os.environ.get('BUSINESS_NAME', 'LeadPulse'),
    })
    return jsonify(settings)

@app.route('/api/settings', methods=['PUT'])
@jwt_required()
def update_settings():
    user, ws = current_user_and_workspace()
    if user['role'] not in ['owner', 'admin']:
        return jsonify(error="Insufficient permissions"), 403
    data = request.get_json() or {}
    db = get_db()
    if 'workspace_name' in data:
        db.execute("UPDATE workspaces SET name=? WHERE id=?", (data['workspace_name'], ws['id']))
    settings = json.loads(ws['settings'] or '{}')
    for k in ['default_timezone', 'default_country_code']:
        if k in data:
            settings[k] = data[k]
    db.execute("UPDATE workspaces SET settings=? WHERE id=?", (json.dumps(settings), ws['id']))
    db.commit()
    db.close()
    return jsonify(message="Settings updated")

# ─── Live Call Center / Hang-up / Sync ────────────────────────────────────────

@app.route('/api/calls/live', methods=['GET'])
@jwt_required()
def live_calls():
    user, ws = current_user_and_workspace()
    db = get_db()
    active = db.execute(
        """SELECT * FROM calls WHERE workspace_id=? AND status IN ('scheduled','queued','ringing','in_progress','answered')
           ORDER BY created_at DESC LIMIT 50""",
        (ws['id'],)
    ).fetchall()
    recent = db.execute(
        "SELECT * FROM calls WHERE workspace_id=? ORDER BY created_at DESC LIMIT 25",
        (ws['id'],)
    ).fetchall()
    db.close()
    allowed, slot_reason = is_within_calling_slots(ws['id'])
    return jsonify(
        active=[dict(r) for r in active],
        recent=[dict(r) for r in recent],
        calling_window={'allowed': allowed, 'reason': slot_reason}
    )

@app.route('/api/calls/<call_id>/hangup', methods=['POST'])
@jwt_required()
def hangup_call(call_id):
    user, ws = current_user_and_workspace()
    db = get_db()
    call = db.execute("SELECT * FROM calls WHERE id=? AND workspace_id=?", (call_id, ws['id'])).fetchone()
    if not call:
        db.close()
        return jsonify(error="Call not found"), 404
    cancelled = False
    error = None
    if call['event_id'] and call['status'] in ('scheduled', 'queued'):
        try:
            client = get_telnyx_client()
            client.ai.assistants.scheduled_events.delete(
                assistant_id=call['assistant_id'] or os.environ.get('TELNYX_ASSISTANT_ID'),
                event_id=call['event_id']
            )
            cancelled = True
        except Exception as e:
            error = str(e)
    db.execute(
        "UPDATE calls SET status='cancelled', ended_at=?, outcome='cancelled' WHERE id=?",
        (now_iso(), call_id)
    )
    db.commit()
    db.close()
    audit(ws['id'], user['id'], 'hangup_call', 'call', call_id, {'cancelled_event': cancelled})
    return jsonify(message="Call cancelled", event_cancelled=cancelled, provider_error=error)

@app.route('/api/calls/sync', methods=['POST'])
@jwt_required()
def sync_calls_from_telnyx():
    """Pull recent Telnyx conversations and attach transcripts to matching local calls."""
    user, ws = current_user_and_workspace()
    ensure_extra_tables()
    synced = 0
    conversations_out = []
    try:
        client = get_telnyx_client()
        conversations = client.ai.conversations.list()
        db = get_db()
        for conv in (conversations.data or [])[:40]:
            conv_id = conv.id
            created = getattr(conv, 'created_at', None)
            transcript_parts = []
            try:
                msgs = client.ai.conversations.messages.list(conversation_id=conv_id)
                for m in (msgs.data or []):
                    role = getattr(m, 'role', 'speaker')
                    text = getattr(m, 'content', '') or ''
                    if text:
                        transcript_parts.append(f"{role}: {text}")
            except Exception:
                pass
            transcript = '\n'.join(transcript_parts) if transcript_parts else None
            conversations_out.append({
                'id': conv_id,
                'created_at': str(created) if created else None,
                'has_transcript': bool(transcript),
                'message_count': len(transcript_parts),
            })
            # Match by approximate time window to recent calls without transcript
            if transcript:
                updated = db.execute(
                    """UPDATE calls SET transcript=?, conversation_id=?, status=CASE WHEN status IN ('scheduled','queued') THEN 'completed' ELSE status END
                       WHERE workspace_id=? AND (conversation_id=? OR (transcript IS NULL AND created_at IS NOT NULL))
                       AND id = (
                         SELECT id FROM calls WHERE workspace_id=? AND transcript IS NULL
                         ORDER BY ABS(julianday(created_at) - julianday(?)) ASC LIMIT 1
                       )""",
                    (transcript, conv_id, ws['id'], conv_id, ws['id'],
                     str(created) if created else now_iso())
                )
                if updated.rowcount:
                    synced += 1
        db.commit()
        db.close()
    except Exception as e:
        return jsonify(error=str(e), synced=synced), 502
    audit(ws['id'], user['id'], 'sync_calls', details={'synced': synced})
    return jsonify(synced=synced, conversations=conversations_out)

@app.route('/api/calls/<call_id>/transcript', methods=['GET'])
@jwt_required()
def get_call_transcript(call_id):
    user, ws = current_user_and_workspace()
    db = get_db()
    call = db.execute("SELECT * FROM calls WHERE id=? AND workspace_id=?", (call_id, ws['id'])).fetchone()
    db.close()
    if not call:
        return jsonify(error="Not found"), 404
    segments = []
    raw = call['transcript'] or ''
    for line in raw.split('\n'):
        if not line.strip():
            continue
        if ':' in line:
            role, text = line.split(':', 1)
            segments.append({'role': role.strip().lower(), 'text': text.strip()})
        else:
            segments.append({'role': 'unknown', 'text': line.strip()})
    return jsonify(
        call_id=call_id,
        conversation_id=call['conversation_id'] if 'conversation_id' in call.keys() else None,
        recording_url=call['recording_url'],
        transcript=raw or None,
        segments=segments,
        available=bool(raw)
    )

@app.route('/api/leads/<lead_id>', methods=['GET'])
@jwt_required()
def get_lead(lead_id):
    if lead_id in ('import', 'template'):
        return jsonify(error="Not found"), 404
    user, ws = current_user_and_workspace()
    db = get_db()
    lead = db.execute("SELECT * FROM leads WHERE id=? AND workspace_id=?", (lead_id, ws['id'])).fetchone()
    if not lead:
        db.close()
        return jsonify(error="Not found"), 404
    calls = db.execute(
        "SELECT * FROM calls WHERE lead_id=? ORDER BY created_at DESC LIMIT 50", (lead_id,)
    ).fetchall()
    db.close()
    return jsonify(lead=dict(lead), calls=[dict(c) for c in calls])

@app.route('/api/slots/status', methods=['GET'])
@jwt_required()
def slots_status():
    user, ws = current_user_and_workspace()
    allowed, reason = is_within_calling_slots(ws['id'])
    return jsonify(allowed=allowed, reason=reason)

# ─── Plans & Billing ──────────────────────────────────────────────────────────

PLANS = [
    {'id': 'monthly', 'name': 'Monthly', 'duration_months': 1, 'price': 2999, 'currency': 'INR',
     'features': ['Unlimited Leads', 'Unlimited Campaigns', '1 AI Agent', 'Call Recordings', 'Email Support']},
    {'id': 'biannual', 'name': 'Six Months', 'duration_months': 6, 'price': 14999, 'currency': 'INR',
     'features': ['Unlimited Leads', 'Unlimited Campaigns', '3 AI Agents', 'Call Recordings', 'Priority Support', '17% Savings']},
    {'id': 'annual', 'name': 'Annual', 'duration_months': 12, 'price': 24999, 'currency': 'INR',
     'features': ['Unlimited Leads', 'Unlimited Campaigns', '5 AI Agents', 'Advanced Analytics', 'Dedicated Support', '31% Savings']},
    {'id': 'biennial', 'name': 'Two Year', 'duration_months': 24, 'price': 39999, 'currency': 'INR',
     'features': ['Unlimited Leads', 'Unlimited Campaigns', 'Unlimited Agents', 'White Label', 'SLA Support', '45% Savings']},
]

def _plan_by_id(plan_id):
    return next((p for p in PLANS if p['id'] == plan_id), None)

@app.route('/api/plans', methods=['GET'])
@jwt_required()
def get_plans():
    user, ws = current_user_and_workspace()
    ensure_extra_tables()
    razorpay_ready = bool(os.environ.get('RAZORPAY_KEY_ID') and os.environ.get('RAZORPAY_KEY_SECRET'))
    return jsonify(
        plans=PLANS,
        current_plan=ws['plan'],
        expires_at=ws['plan_expires_at'],
        entitled=plan_entitled(ws),
        payment_provider='razorpay' if razorpay_ready else 'manual',
        razorpay_key_id=os.environ.get('RAZORPAY_KEY_ID') if razorpay_ready else None
    )

@app.route('/api/billing/orders', methods=['POST'])
@jwt_required()
def create_billing_order():
    user, ws = current_user_and_workspace()
    if user['role'] not in ['owner', 'admin']:
        return jsonify(error="Only owners and admins can manage billing"), 403
    ensure_extra_tables()
    data = request.get_json() or {}
    plan = _plan_by_id(data.get('plan_id'))
    if not plan:
        return jsonify(error="Invalid plan"), 400

    sub_id = str(uuid.uuid4())
    now = now_iso()
    provider = 'manual'
    provider_order_id = None
    checkout = None

    key_id = os.environ.get('RAZORPAY_KEY_ID')
    key_secret = os.environ.get('RAZORPAY_KEY_SECRET')
    if key_id and key_secret:
        try:
            import requests as req
            import base64
            auth = base64.b64encode(f"{key_id}:{key_secret}".encode()).decode()
            amount_paise = int(plan['price']) * 100
            r = req.post(
                'https://api.razorpay.com/v1/orders',
                headers={'Authorization': f'Basic {auth}', 'Content-Type': 'application/json'},
                json={
                    'amount': amount_paise,
                    'currency': plan['currency'],
                    'receipt': sub_id[:32],
                    'notes': {'workspace_id': ws['id'], 'plan_id': plan['id'], 'subscription_id': sub_id}
                },
                timeout=15
            )
            if r.status_code in (200, 201):
                order = r.json()
                provider = 'razorpay'
                provider_order_id = order.get('id')
                checkout = {
                    'order_id': provider_order_id,
                    'amount': amount_paise,
                    'currency': plan['currency'],
                    'key_id': key_id,
                    'name': 'LeadPulse.ai',
                    'description': f"{plan['name']} plan",
                }
            else:
                return jsonify(error=f"Razorpay order failed: {r.text}"), 502
        except Exception as e:
            return jsonify(error=str(e)), 502

    db = get_db()
    db.execute(
        """INSERT INTO subscriptions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (sub_id, ws['id'], plan['id'], 'pending', plan['price'], plan['currency'],
         provider, provider_order_id, None, None, None, now, now)
    )
    db.execute(
        "INSERT INTO billing_events VALUES (?,?,?,?,?,?)",
        (str(uuid.uuid4()), ws['id'], sub_id, 'order_created',
         json.dumps({'plan_id': plan['id'], 'provider': provider}), now)
    )
    db.commit()
    db.close()
    audit(ws['id'], user['id'], 'create_billing_order', 'subscription', sub_id, {'plan': plan['id']})
    return jsonify(
        subscription_id=sub_id,
        provider=provider,
        checkout=checkout,
        message='Razorpay checkout ready' if checkout else 'Manual order created — complete payment with account manager or verify with payment_id'
    ), 201

@app.route('/api/billing/verify', methods=['POST'])
@jwt_required()
def verify_billing():
    """Verify payment and activate subscription. Supports Razorpay signature or manual admin activation."""
    user, ws = current_user_and_workspace()
    if user['role'] not in ['owner', 'admin']:
        return jsonify(error="Insufficient permissions"), 403
    ensure_extra_tables()
    data = request.get_json() or {}
    sub_id = data.get('subscription_id')
    db = get_db()
    sub = db.execute(
        "SELECT * FROM subscriptions WHERE id=? AND workspace_id=?", (sub_id, ws['id'])
    ).fetchone()
    if not sub:
        db.close()
        return jsonify(error="Subscription not found"), 404
    if sub['status'] == 'active':
        db.close()
        return jsonify(message="Already active", status='active')

    plan = _plan_by_id(sub['plan_id'])
    if not plan:
        db.close()
        return jsonify(error="Plan missing"), 400

    payment_id = data.get('razorpay_payment_id') or data.get('payment_id')
    order_id = data.get('razorpay_order_id') or sub['provider_order_id']
    signature = data.get('razorpay_signature')
    verified = False

    if sub['provider'] == 'razorpay' and payment_id and signature and order_id:
        import hmac as hmac_mod
        secret = os.environ.get('RAZORPAY_KEY_SECRET', '')
        payload = f"{order_id}|{payment_id}".encode()
        expected = hmac_mod.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        verified = hmac_mod.compare_digest(expected, signature)
        if not verified:
            db.close()
            return jsonify(error="Invalid payment signature"), 400
    elif data.get('manual_activate') and user['role'] == 'owner':
        # Owner-only manual activation when Razorpay is not configured
        verified = True
        payment_id = payment_id or f"manual_{uuid.uuid4().hex[:12]}"
    else:
        db.close()
        return jsonify(error="Payment verification requires Razorpay signature or owner manual_activate"), 400

    starts = datetime.now(timezone.utc)
    expires = starts + timedelta(days=30 * plan['duration_months'])
    db.execute(
        """UPDATE subscriptions SET status='active', provider_payment_id=?, started_at=?, expires_at=?, updated_at=?
           WHERE id=?""",
        (payment_id, starts.isoformat(), expires.isoformat(), now_iso(), sub_id)
    )
    db.execute(
        "UPDATE workspaces SET plan=?, plan_expires_at=? WHERE id=?",
        (plan['id'], expires.isoformat(), ws['id'])
    )
    db.execute(
        "INSERT INTO billing_events VALUES (?,?,?,?,?,?)",
        (str(uuid.uuid4()), ws['id'], sub_id, 'payment_verified',
         json.dumps({'payment_id': payment_id, 'verified': verified}), now_iso())
    )
    db.commit()
    db.close()
    audit(ws['id'], user['id'], 'activate_subscription', 'subscription', sub_id, {'plan': plan['id']})
    return jsonify(status='active', plan=plan['id'], expires_at=expires.isoformat())

@app.route('/api/billing/webhook/razorpay', methods=['POST'])
def razorpay_webhook():
    """Idempotent Razorpay webhook — verifies signature when secret is set."""
    ensure_extra_tables()
    raw = request.get_data()
    webhook_secret = os.environ.get('RAZORPAY_WEBHOOK_SECRET', '')
    if webhook_secret:
        import hmac as hmac_mod
        sig = request.headers.get('X-Razorpay-Signature', '')
        expected = hmac_mod.new(webhook_secret.encode(), raw, hashlib.sha256).hexdigest()
        if not hmac_mod.compare_digest(expected, sig):
            return jsonify(error="Invalid webhook signature"), 400
    payload = request.get_json(silent=True) or {}
    event = payload.get('event', 'unknown')
    entity = (((payload.get('payload') or {}).get('payment') or {}).get('entity') or {})
    order_id = entity.get('order_id')
    payment_id = entity.get('id')
    if not order_id:
        return jsonify(status='ignored'), 200

    db = get_db()
    sub = db.execute(
        "SELECT * FROM subscriptions WHERE provider_order_id=?", (order_id,)
    ).fetchone()
    if not sub:
        db.close()
        return jsonify(status='unknown_order'), 200
    # Idempotent: skip if already active with same payment
    if sub['status'] == 'active' and sub['provider_payment_id'] == payment_id:
        db.close()
        return jsonify(status='already_processed'), 200

    if event in ('payment.captured', 'order.paid') and entity.get('status') == 'captured':
        plan = _plan_by_id(sub['plan_id'])
        if plan:
            starts = datetime.now(timezone.utc)
            expires = starts + timedelta(days=30 * plan['duration_months'])
            db.execute(
                """UPDATE subscriptions SET status='active', provider_payment_id=?, started_at=?, expires_at=?, updated_at=?
                   WHERE id=?""",
                (payment_id, starts.isoformat(), expires.isoformat(), now_iso(), sub['id'])
            )
            db.execute(
                "UPDATE workspaces SET plan=?, plan_expires_at=? WHERE id=?",
                (plan['id'], expires.isoformat(), sub['workspace_id'])
            )
    db.execute(
        "INSERT INTO billing_events VALUES (?,?,?,?,?,?)",
        (str(uuid.uuid4()), sub['workspace_id'], sub['id'], f'webhook:{event}',
         json.dumps(payload)[:4000], now_iso())
    )
    db.commit()
    db.close()
    return jsonify(status='ok'), 200

@app.route('/api/billing/history', methods=['GET'])
@jwt_required()
def billing_history():
    user, ws = current_user_and_workspace()
    ensure_extra_tables()
    db = get_db()
    subs = db.execute(
        "SELECT * FROM subscriptions WHERE workspace_id=? ORDER BY created_at DESC LIMIT 50",
        (ws['id'],)
    ).fetchall()
    events = db.execute(
        "SELECT id, subscription_id, event_type, created_at FROM billing_events WHERE workspace_id=? ORDER BY created_at DESC LIMIT 50",
        (ws['id'],)
    ).fetchall()
    db.close()
    return jsonify(subscriptions=[dict(s) for s in subs], events=[dict(e) for e in events])

# ─── Config & Health ──────────────────────────────────────────────────────────

@app.route('/api/health', methods=['GET'])
def health():
    api_key_set = bool(os.environ.get('TELNYX_API_KEY'))
    assistant_set = bool(os.environ.get('TELNYX_ASSISTANT_ID'))
    phone_set = bool(os.environ.get('TELNYX_PHONE_NUMBER'))
    razorpay = bool(os.environ.get('RAZORPAY_KEY_ID') and os.environ.get('RAZORPAY_KEY_SECRET'))
    return jsonify(status='ok', telnyx_api_key=api_key_set,
                   assistant_configured=assistant_set, phone_configured=phone_set,
                   razorpay_configured=razorpay, version='2.0.0')

# ─── Frontend catch-all ───────────────────────────────────────────────────────

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_frontend(path):
    if path and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, 'index.html')

# ─── Run ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    init_db()
    print("\nLeadPulse.ai Calling Platform")
    print("=" * 40)
    print(f"   Web UI  : http://localhost:5000")
    print(f"   API     : http://localhost:5000/api")
    print(f"   Login   : admin@leadpulse.ai / admin123")
    print("=" * 40 + "\n")
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)
