# LeadPulse.ai — Web Platform

Lightweight dashboard for team members to run outbound AI calls without using the CLI scripts.

## Stack

- **API:** Flask + SQLite + Telnyx (`webapp/api/app.py`) — port **5000**
- **UI:** Next.js + Tailwind (`webapp/dashboard`) — port **3000** (proxies `/api/*` to Flask)

## Run locally

```bash
# 1) Backend (from repo root)
pip install -r requirements.txt
python webapp/server.py

# 2) Frontend (new terminal)
cd webapp/dashboard
npm install
npm run dev
```

Open **http://localhost:3000**  
Login: `admin@leadpulse.ai` / `admin123`

Telnyx keys stay in the root `.env` (never in the browser).

## What works

| Feature | Notes |
|--------|--------|
| Login / JWT | Roles: owner, admin, operator |
| Lead Gen overview | Animated landing dashboard |
| Test call | `POST /api/calls/test` → Telnyx scheduled event |
| Live calls | Polls every 5s; hang-up cancels scheduled events when possible |
| Leads | CRUD + CSV import + template download |
| Campaigns | Create, launch, pause, resume, stop |
| Call history | Filter + call detail / transcript |
| AI agents | List/edit via Telnyx |
| Calling slots | CRUD; enforced on test call & campaign launch |
| Usage & balance | Telnyx balance API |
| Billing | Plan catalog; Razorpay if keys set, else owner manual activate |
| Team | Invite / deactivate (owner/admin) |

## Optional env

```
JWT_SECRET_KEY=change-me
CORS_ORIGINS=http://localhost:3000
RAZORPAY_KEY_ID=
RAZORPAY_KEY_SECRET=
RAZORPAY_WEBHOOK_SECRET=
```

## Legacy UI

The older single-page UI is still served by Flask at **http://localhost:5000**. Prefer the Next.js app on port 3000.
