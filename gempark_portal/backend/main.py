"""
Hotel Gem Park, Ooty — owner portal API.

Nora (the Gem Park voice agent) answers questions only; bookings go to the
reservations team by callback. So this portal shows calls, recordings,
transcripts, the leads waiting for a callback, and the WhatsApp conversations.

Reads and writes only the gp_* tables, never the Lotus Sutra ones, and never
exposes the per-call Gemini/VoBiz costs stored on gp_calls — those stay internal.

Run:  uvicorn main:app --port 8004
"""
import os
import jwt
import secrets
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from dotenv import load_dotenv
from fastapi import FastAPI, Query, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from supabase import create_client

# Load .env — repo root (local dev) then current dir (Docker)
_root_env = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
load_dotenv(_root_env if os.path.exists(_root_env) else ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Credentials are separate from the Lotus portal and the admin panel.
PORTAL_USER = os.getenv("GP_PORTAL_USERNAME", "gempark")
_ENV_PASS   = os.getenv("GP_PORTAL_PASSWORD", "gempark")
HOTEL_NAME  = os.getenv("GP_HOTEL_NAME", "Hotel Gem Park, Ooty")

# Own key in portal_settings so a password change here never touches Lotus's.
_PASSWORD_KEY = "gp_portal_password"
_current_password: str = _ENV_PASS

JWT_SECRET = os.getenv("GP_PORTAL_JWT_SECRET", secrets.token_hex(32))
JWT_ALGO = "HS256"
JWT_EXPIRY_HOURS = 24

IST = timezone(timedelta(hours=5, minutes=30))

# Every column the portal may show. Cost columns are deliberately left out.
CALL_LIST_COLS = (
    "id, call_sid, phone_number, started_at, ended_at, duration_seconds, recording_url, "
    "call_back, lead_temperature, intent, guest_name, language, callback_status, created_at"
)
CALL_DETAIL_COLS = (
    CALL_LIST_COLS + ", transcript, callback_promised, dates_mentioned, guests, "
    "room_interest, interest_summary, call_summary, reason, contacted_at, whatsapp_sent"
)

CALLBACK_STATUSES = ("pending", "contacted", "not_needed")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
bearer_scheme = HTTPBearer(auto_error=False)

app = FastAPI(title="Hotel Gem Park — Owner Portal API")


@app.on_event("startup")
def _load_saved_password():
    """Load the persisted password from Supabase (overrides the env var if set)."""
    global _current_password
    try:
        row = (
            supabase.table("portal_settings")
            .select("value")
            .eq("key", _PASSWORD_KEY)
            .maybe_single()
            .execute()
        )
        if row and row.data and row.data.get("value"):
            _current_password = row.data["value"]
    except Exception:
        pass  # table may not exist yet — fall back to env var

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "portal": "gempark", "hotel": HOTEL_NAME}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str
    password: str

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

class CallbackUpdate(BaseModel):
    status: str


def _make_token() -> str:
    payload = {
        "sub": PORTAL_USER,
        "role": "gempark_client",
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def _verify_token(creds: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    if not creds:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        jwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALGO])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


@app.post("/api/login")
def login(body: LoginRequest):
    if body.username != PORTAL_USER or body.password != _current_password:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"token": _make_token(), "hotel": HOTEL_NAME}


@app.get("/api/me")
def me(_=Depends(_verify_token)):
    return {"username": PORTAL_USER, "hotel": HOTEL_NAME, "role": "gempark_client"}


@app.post("/api/change-password")
def change_password(body: ChangePasswordRequest, _=Depends(_verify_token)):
    global _current_password
    if body.current_password != _current_password:
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if len(body.new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters")
    # Persist to Supabase so it survives server restarts
    try:
        supabase.table("portal_settings").upsert(
            {"key": _PASSWORD_KEY, "value": body.new_password},
            on_conflict="key"
        ).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save password: {e}")
    _current_password = body.new_password
    return {"ok": True}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None


def _duration(c: dict) -> float:
    """Call length in seconds — stored value, else from start/end."""
    if c.get("duration_seconds") is not None:
        return max(0.0, float(c["duration_seconds"]))
    s, e = _parse(c.get("started_at")), _parse(c.get("ended_at"))
    return max(0.0, (e - s).total_seconds()) if s and e else 0.0


def _pages(total: int, limit: int) -> int:
    return max(1, -(-total // limit))


# ---------------------------------------------------------------------------
# /api/overview  — headline numbers for the home page
# ---------------------------------------------------------------------------

@app.get("/api/overview")
def overview(_=Depends(_verify_token)):
    now_ist   = datetime.now(IST)
    today     = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago  = now_ist - timedelta(days=7)
    month_ago = now_ist - timedelta(days=30)

    calls = supabase.table("gp_calls").select(
        "created_at, started_at, ended_at, duration_seconds, call_back, callback_status, lead_temperature"
    ).execute().data or []
    sessions = supabase.table("gp_whatsapp_sessions").select(
        "call_back, callback_status"
    ).execute().data or []

    calls_today = calls_week = calls_month = 0
    total_seconds = 0.0
    leads = defaultdict(int)
    for c in calls:
        dt = _parse(c.get("created_at"))
        if dt:
            if dt >= today:
                calls_today += 1
            if dt >= week_ago:
                calls_week += 1
            if dt >= month_ago:
                calls_month += 1
        total_seconds += _duration(c)
        leads[c.get("lead_temperature") or "unknown"] += 1

    def _waiting(rows):
        return sum(1 for r in rows if r.get("call_back") and (r.get("callback_status") or "pending") == "pending")

    def _contacted(rows):
        return sum(1 for r in rows if r.get("callback_status") == "contacted")

    total_calls = len(calls)
    return {
        "hotel": HOTEL_NAME,
        "total_calls": total_calls,
        "calls_today": calls_today,
        "calls_this_week": calls_week,
        "calls_this_month": calls_month,
        "total_minutes": round(total_seconds / 60, 1),
        "avg_call_seconds": round(total_seconds / total_calls) if total_calls else 0,
        "callbacks_pending": _waiting(calls) + _waiting(sessions),
        "callbacks_contacted": _contacted(calls) + _contacted(sessions),
        "hot_leads": leads["hot"],
        "warm_leads": leads["warm"],
        "cold_leads": leads["cold"],
        "whatsapp_conversations": len(sessions),
    }


# ---------------------------------------------------------------------------
# /api/insights  — charts (trend, peak hours, languages, intents, leads)
# ---------------------------------------------------------------------------

@app.get("/api/insights")
def insights(_=Depends(_verify_token)):
    start = datetime.now(IST) - timedelta(days=29)

    calls = supabase.table("gp_calls").select(
        "created_at, language, intent, lead_temperature"
    ).execute().data or []

    day_counts: dict[str, int] = {
        (start + timedelta(days=i)).strftime("%Y-%m-%d"): 0 for i in range(30)
    }
    hour_counts: dict[int, int] = defaultdict(int)
    lang_counts: dict[str, int] = defaultdict(int)
    intent_counts: dict[str, int] = defaultdict(int)
    lead_counts: dict[str, int] = defaultdict(int)

    for c in calls:
        lang_counts[(c.get("language") or "unknown").lower()] += 1
        intent_counts[c.get("intent") or "unknown"] += 1
        lead_counts[c.get("lead_temperature") or "unknown"] += 1
        dt = _parse(c.get("created_at"))
        if not dt:
            continue
        dt = dt.astimezone(IST)
        day = dt.strftime("%Y-%m-%d")
        if day in day_counts:
            day_counts[day] += 1
        hour_counts[dt.hour] += 1

    return {
        "calls_trend":   [{"date": d, "count": day_counts[d]} for d in sorted(day_counts)],
        "peak_hours":    [{"hour": f"{h:02d}:00", "count": hour_counts.get(h, 0)} for h in range(24)],
        "language_dist": [{"language": k, "count": v} for k, v in lang_counts.items()],
        "intent_dist":   [{"intent": k, "count": v} for k, v in intent_counts.items()],
        "lead_dist":     [{"lead": k, "count": v} for k, v in lead_counts.items()],
    }


# ---------------------------------------------------------------------------
# /api/calls  (+ detail with transcript & recording)
# ---------------------------------------------------------------------------

@app.get("/api/calls")
def get_calls(
    _=Depends(_verify_token),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: str = Query(None),
    lead: str = Query(None),
    callback: bool = Query(None),
):
    offset = (page - 1) * limit

    def _f(q):
        if search:
            s = search.replace(",", " ").strip()
            q = q.or_(f"phone_number.ilike.%{s}%,guest_name.ilike.%{s}%")
        if lead:
            q = q.eq("lead_temperature", lead)
        if callback is not None:
            q = q.eq("call_back", callback)
        return q

    total = _f(supabase.table("gp_calls").select("id", count="exact")).execute().count or 0
    rows = _f(
        supabase.table("gp_calls").select(CALL_LIST_COLS)
        .order("created_at", desc=True).range(offset, offset + limit - 1)
    ).execute().data or []

    all_calls = supabase.table("gp_calls").select(
        "started_at, ended_at, duration_seconds"
    ).execute().data or []
    secs = sum(_duration(c) for c in all_calls)

    return {"data": rows, "total": total, "page": page, "pages": _pages(total, limit),
            "total_minutes": round(secs / 60, 1)}


@app.get("/api/calls/{call_id}")
def get_call(call_id: str, _=Depends(_verify_token)):
    rows = supabase.table("gp_calls").select(CALL_DETAIL_COLS).eq("id", call_id).limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Call not found")
    return rows[0]


# ---------------------------------------------------------------------------
# /api/callbacks  — guests the reservations team should call back
# (voice leads from gp_calls + WhatsApp leads from gp_whatsapp_sessions)
# ---------------------------------------------------------------------------

@app.get("/api/callbacks")
def get_callbacks(
    _=Depends(_verify_token),
    status: str = Query("pending"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    if status not in (*CALLBACK_STATUSES, "all"):
        raise HTTPException(status_code=400, detail="Invalid status")

    cq = supabase.table("gp_calls").select(
        "id, phone_number, guest_name, lead_temperature, intent, dates_mentioned, guests, "
        "room_interest, interest_summary, reason, recording_url, callback_status, "
        "contacted_at, created_at"
    ).eq("call_back", True)
    wq = supabase.table("gp_whatsapp_sessions").select(
        "phone, interest_summary, callback_status, contacted_at, last_message_at, created_at"
    ).eq("call_back", True)
    if status != "all":
        cq, wq = cq.eq("callback_status", status), wq.eq("callback_status", status)

    items = []
    for c in cq.execute().data or []:
        items.append({**c, "source": "call", "key": c["id"],
                      "callback_status": c.get("callback_status") or "pending"})
    for w in wq.execute().data or []:
        items.append({
            "source": "whatsapp",
            "key": w["phone"],
            "phone_number": w["phone"],
            "interest_summary": w.get("interest_summary"),
            "callback_status": w.get("callback_status") or "pending",
            "contacted_at": w.get("contacted_at"),
            "created_at": w.get("last_message_at") or w.get("created_at"),
        })
    items.sort(key=lambda x: x.get("created_at") or "", reverse=True)

    total = len(items)
    offset = (page - 1) * limit
    return {"data": items[offset:offset + limit], "total": total,
            "page": page, "pages": _pages(total, limit)}


def _status_update(status: str) -> dict:
    if status not in CALLBACK_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")
    return {
        "callback_status": status,
        "contacted_at": datetime.now(timezone.utc).isoformat() if status == "contacted" else None,
    }


@app.patch("/api/callbacks/call/{call_id}")
def update_call_callback(call_id: str, body: CallbackUpdate, _=Depends(_verify_token)):
    r = supabase.table("gp_calls").update(_status_update(body.status)).eq("id", call_id).execute()
    if not r.data:
        raise HTTPException(status_code=404, detail="Call not found")
    return {"ok": True}


@app.patch("/api/callbacks/whatsapp/{phone}")
def update_whatsapp_callback(phone: str, body: CallbackUpdate, _=Depends(_verify_token)):
    r = supabase.table("gp_whatsapp_sessions").update(_status_update(body.status)).eq("phone", phone).execute()
    if not r.data:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"ok": True}


# ---------------------------------------------------------------------------
# /api/whatsapp  — bot conversations + thank-you messages after calls
# ---------------------------------------------------------------------------

@app.get("/api/whatsapp/conversations")
def get_wa_conversations(
    _=Depends(_verify_token),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    offset = (page - 1) * limit
    total = supabase.table("gp_whatsapp_sessions").select("phone", count="exact").execute().count or 0
    rows = (
        supabase.table("gp_whatsapp_sessions")
        .select("phone, call_back, callback_status, interest_summary, last_message_at, created_at, conversation")
        .order("last_message_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute().data or []
    )
    for row in rows:
        conv = row.pop("conversation", None) or []
        row["message_count"] = len(conv)
        last = next((m for m in reversed(conv) if m.get("role") == "user"), None)
        row["last_guest_message"] = (last.get("content") or "")[:80] if last else ""

    return {"data": rows, "total": total, "page": page, "pages": _pages(total, limit)}


@app.get("/api/whatsapp/conversations/{phone}")
def get_wa_conversation_thread(phone: str, _=Depends(_verify_token)):
    rows = supabase.table("gp_whatsapp_sessions").select("*").eq("phone", phone).limit(1).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return rows[0]


@app.get("/api/whatsapp/thanks")
def get_wa_thanks(
    _=Depends(_verify_token),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """Whether each caller got the WhatsApp thank-you after their call."""
    offset = (page - 1) * limit
    total = supabase.table("gp_calls").select("id", count="exact").execute().count or 0
    rows = (
        supabase.table("gp_calls")
        .select("id, phone_number, guest_name, whatsapp_sent, created_at")
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute().data or []
    )
    return {"data": rows, "total": total, "page": page, "pages": _pages(total, limit)}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8004, reload=True)
