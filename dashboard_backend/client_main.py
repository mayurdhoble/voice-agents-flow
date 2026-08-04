"""
Client (hotel owner) portal API — a scoped, business-focused view.

Deliberately DOES NOT expose cost/usage, WhatsApp delivery logs, or any system
internals that live in the admin panel (main.py). The hotel sees only what helps
them run the business: calls, conversations, bookings, guests, events, and the
"needs attention" bookings that require a manual follow-up.

Run:  uvicorn client_main:app --port 8003
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

# Load .env — parent dir (local dev) then current dir (Docker)
_parent_env = os.path.join(os.path.dirname(__file__), "..", ".env")
load_dotenv(_parent_env if os.path.exists(_parent_env) else ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Client credentials are separate from the admin panel's.
CLIENT_USER = os.getenv("CLIENT_USERNAME", "hotel")
_ENV_PASS   = os.getenv("CLIENT_PASSWORD", "hotel")
HOTEL_NAME  = os.getenv("HOTEL_NAME", "Lotus Sutra Goa")

# In-memory current password — loaded from Supabase portal_settings on startup,
# falls back to env var. Updated in-memory + Supabase on change-password.
_current_password: str = _ENV_PASS

JWT_SECRET = os.getenv("CLIENT_JWT_SECRET", os.getenv("DASHBOARD_JWT_SECRET", secrets.token_hex(32)))
JWT_ALGO = "HS256"
JWT_EXPIRY_HOURS = 24

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
bearer_scheme = HTTPBearer(auto_error=False)

app = FastAPI(title="Hotel Voice Agent — Client Portal API")


@app.on_event("startup")
def _load_saved_password():
    """Load persisted password from Supabase on startup (overrides env var if set)."""
    global _current_password
    try:
        row = (
            supabase.table("portal_settings")
            .select("value")
            .eq("key", "client_password")
            .maybe_single()
            .execute()
        )
        if row.data and row.data.get("value"):
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
    return {"status": "ok", "portal": "client", "hotel": HOTEL_NAME}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str
    password: str

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


def _make_token() -> str:
    payload = {
        "sub": CLIENT_USER,
        "role": "client",
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
    if body.username != CLIENT_USER or body.password != _current_password:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"token": _make_token(), "hotel": HOTEL_NAME}


@app.get("/api/me")
def me(creds: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    _verify_token(creds)
    return {"username": CLIENT_USER, "hotel": HOTEL_NAME, "role": "client"}


@app.post("/api/change-password")
def change_password(body: ChangePasswordRequest, creds: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    global _current_password
    _verify_token(creds)
    if body.current_password != _current_password:
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if len(body.new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters")
    # Persist to Supabase so it survives server restarts
    try:
        supabase.table("portal_settings").upsert(
            {"key": "client_password", "value": body.new_password},
            on_conflict="key"
        ).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save password: {e}")
    _current_password = body.new_password
    return {"ok": True}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _count(table: str, **eq) -> int:
    q = supabase.table(table).select("id", count="exact")
    for k, v in eq.items():
        q = q.eq(k, v)
    return q.execute().count or 0


def _booking_issues(b: dict) -> list[str]:
    """Reasons a booking needs manual attention (used by the Needs-Attention view)."""
    issues = []
    if (b.get("status") or "pending") == "pending":
        issues.append("Not yet confirmed")
    if not b.get("djubo_booking_id"):
        issues.append("Not synced to PMS")
    if not b.get("whatsapp_sent"):
        issues.append("Guest not messaged")
    if not b.get("checkin_date") or not b.get("checkout_date"):
        issues.append("Missing dates")
    return issues


# ---------------------------------------------------------------------------
# /api/overview  — headline KPIs for the home page
# ---------------------------------------------------------------------------

@app.get("/api/overview")
def overview():
    now = datetime.now(timezone.utc)
    week_ago  = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    total_calls    = _count("calls")
    total_guests   = _count("guests")
    total_bookings = _count("bookings")
    total_events   = _count("events")
    confirmed      = _count("bookings", status="confirmed")
    pending        = _count("bookings", status="pending")
    cancelled      = _count("bookings", status="cancelled")

    # calls this week / month
    calls = supabase.table("calls").select("created_at").execute().data or []
    calls_week = calls_month = 0
    for c in calls:
        raw = c.get("created_at")
        if not raw:
            continue
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            continue
        if dt >= month_ago:
            calls_month += 1
        if dt >= week_ago:
            calls_week += 1

    # nights booked (a real proxy for business value — no price stored yet)
    bnights = supabase.table("bookings").select("nights").execute().data or []
    total_nights = sum((b.get("nights") or 0) for b in bnights)

    conversion = round((total_bookings / total_calls) * 100) if total_calls else 0
    needs_attention = pending  # bookings not yet confirmed

    return {
        "hotel": HOTEL_NAME,
        "total_calls": total_calls,
        "total_guests": total_guests,
        "total_bookings": total_bookings,
        "total_events": total_events,
        "confirmed_bookings": confirmed,
        "pending_bookings": pending,
        "cancelled_bookings": cancelled,
        "needs_attention": needs_attention,
        "calls_this_week": calls_week,
        "calls_this_month": calls_month,
        "conversion_rate": conversion,
        "total_nights_booked": total_nights,
    }


# ---------------------------------------------------------------------------
# /api/insights  — charts (trends, languages, rooms, peak hours) — NO costs
# ---------------------------------------------------------------------------

@app.get("/api/insights")
def insights():
    now = datetime.now(timezone.utc)
    thirty = now - timedelta(days=30)

    calls = supabase.table("calls").select("created_at, language").execute().data or []
    bookings = supabase.table("bookings").select("room_type, status").execute().data or []

    day_counts: dict[str, int] = {}
    for i in range(30):
        day_counts[(thirty + timedelta(days=i)).strftime("%Y-%m-%d")] = 0
    hour_counts: dict[int, int] = defaultdict(int)
    lang_counts: dict[str, int] = defaultdict(int)

    for c in calls:
        raw = c.get("created_at")
        lang_counts[c.get("language") or "unknown"] += 1
        if not raw:
            continue
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            continue
        day = dt.strftime("%Y-%m-%d")
        if day in day_counts:
            day_counts[day] += 1
        hour_counts[dt.hour] += 1

    room_counts: dict[str, int] = defaultdict(int)
    status_counts: dict[str, int] = defaultdict(int)
    for b in bookings:
        room_counts[b.get("room_type") or "unknown"] += 1
        status_counts[b.get("status") or "unknown"] += 1

    return {
        "calls_trend":   [{"date": d, "count": day_counts[d]} for d in sorted(day_counts)],
        "peak_hours":    [{"hour": f"{h:02d}:00", "count": hour_counts.get(h, 0)} for h in range(24)],
        "language_dist": [{"language": k, "count": v} for k, v in lang_counts.items()],
        "room_types":    [{"room_type": k, "count": v} for k, v in room_counts.items()],
        "booking_status":[{"status": k, "count": v} for k, v in status_counts.items()],
    }


# ---------------------------------------------------------------------------
# /api/calls  (+ detail with transcript & recording)
# ---------------------------------------------------------------------------

@app.get("/api/calls")
def get_calls(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: str = Query(None),
    language: str = Query(None),
):
    offset = (page - 1) * limit

    def _f(q):
        if search:
            q = q.ilike("phone_number", f"%{search}%")
        if language:
            q = q.eq("language", language)
        return q

    total = _f(supabase.table("calls").select("id", count="exact")).execute().count or 0
    rows = _f(
        supabase.table("calls").select(
            "id, call_sid, phone_number, direction, language, started_at, ended_at, created_at, recording_url"
        ).order("created_at", desc=True).range(offset, offset + limit - 1)
    ).execute().data or []

    pages = max(1, -(-total // limit))
    return {"data": rows, "total": total, "page": page, "pages": pages}


@app.get("/api/calls/{call_sid}")
def get_call(call_sid: str):
    r = supabase.table("calls").select("*").eq("call_sid", call_sid).single().execute()
    return r.data


# ---------------------------------------------------------------------------
# /api/bookings
# ---------------------------------------------------------------------------

@app.get("/api/bookings")
def get_bookings(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: str = Query(None),
    status: str = Query(None),
):
    offset = (page - 1) * limit

    def _f(q):
        if search:
            q = q.ilike("room_type", f"%{search}%")
        if status:
            q = q.eq("status", status)
        return q

    total = _f(supabase.table("bookings").select("id", count="exact")).execute().count or 0
    rows = _f(
        supabase.table("bookings").select("*, guests(name, phone)")
        .order("created_at", desc=True).range(offset, offset + limit - 1)
    ).execute().data or []

    pages = max(1, -(-total // limit))
    return {"data": rows, "total": total, "page": page, "pages": pages}


# ---------------------------------------------------------------------------
# /api/needs-attention  — bookings requiring a manual follow-up
# ---------------------------------------------------------------------------

@app.get("/api/needs-attention")
def needs_attention(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    offset = (page - 1) * limit

    base = supabase.table("bookings").select("*, guests(name, phone)").eq("status", "pending")
    total = supabase.table("bookings").select("id", count="exact").eq("status", "pending").execute().count or 0
    rows = base.order("created_at", desc=True).range(offset, offset + limit - 1).execute().data or []

    for b in rows:
        b["issues"] = _booking_issues(b)

    pages = max(1, -(-total // limit))
    return {"data": rows, "total": total, "page": page, "pages": pages}


# ---------------------------------------------------------------------------
# /api/guests
# ---------------------------------------------------------------------------

@app.get("/api/guests")
def get_guests(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: str = Query(None),
):
    offset = (page - 1) * limit

    def _f(q):
        if search:
            q = q.ilike("name", f"%{search}%")
        return q

    total = _f(supabase.table("guests").select("id", count="exact")).execute().count or 0
    rows = _f(
        supabase.table("guests").select("*").order("created_at", desc=True).range(offset, offset + limit - 1)
    ).execute().data or []

    pages = max(1, -(-total // limit))
    return {"data": rows, "total": total, "page": page, "pages": pages}


# ---------------------------------------------------------------------------
# /api/events
# ---------------------------------------------------------------------------

@app.get("/api/events")
def get_events(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: str = Query(None),
    status: str = Query(None),
):
    offset = (page - 1) * limit

    def _f(q):
        if search:
            q = q.ilike("event_type", f"%{search}%")
        if status:
            q = q.eq("status", status)
        return q

    total = _f(supabase.table("events").select("id", count="exact")).execute().count or 0
    rows = _f(
        supabase.table("events").select("*, guests(name, phone)")
        .order("created_at", desc=True).range(offset, offset + limit - 1)
    ).execute().data or []

    pages = max(1, -(-total // limit))
    return {"data": rows, "total": total, "page": page, "pages": pages}


# ---------------------------------------------------------------------------
# /api/requests  — special service requests extracted from calls
# ---------------------------------------------------------------------------

@app.get("/api/requests")
def get_requests(
    _=Depends(_verify_token),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    request_type: str = Query(None),
    status: str = Query(None),
):
    offset = (page - 1) * limit

    def _f(q):
        if request_type:
            q = q.eq("request_type", request_type)
        if status:
            q = q.eq("status", status)
        return q

    total = _f(supabase.table("requests").select("id", count="exact")).execute().count or 0
    rows = _f(
        supabase.table("requests").select("*")
        .order("created_at", desc=True).range(offset, offset + limit - 1)
    ).execute().data or []

    pages = max(1, -(-total // limit))
    return {"data": rows, "total": total, "page": page, "pages": pages}


@app.patch("/api/requests/{request_id}")
def update_request(request_id: str, body: dict, _=Depends(_verify_token)):
    status = body.get("status")
    if status not in ("new", "acknowledged", "handled"):
        raise HTTPException(status_code=400, detail="Invalid status")
    supabase.table("requests").update({
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", request_id).execute()
    return {"ok": True}


# ---------------------------------------------------------------------------
# /api/whatsapp  — template messages sent to guests
# ---------------------------------------------------------------------------

@app.get("/api/whatsapp")
def get_whatsapp(
    _=Depends(_verify_token),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: str = Query(None),
):
    offset = (page - 1) * limit

    def _f(q):
        if status:
            q = q.eq("status", status)
        return q

    total = _f(supabase.table("whatsapp_logs").select("id", count="exact")).execute().count or 0
    rows = _f(
        supabase.table("whatsapp_logs").select("*, bookings(room_type, guests(name, phone))")
        .order("sent_at", desc=True).range(offset, offset + limit - 1)
    ).execute().data or []

    pages = max(1, -(-total // limit))
    return {"data": rows, "total": total, "page": page, "pages": pages}


# /api/whatsapp/conversations  — bot chat sessions per guest
# ---------------------------------------------------------------------------

@app.get("/api/whatsapp/conversations")
def get_wa_conversations(
    _=Depends(_verify_token),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    offset = (page - 1) * limit
    total = (
        supabase.table("whatsapp_sessions").select("id", count="exact").execute().count or 0
    )
    rows = (
        supabase.table("whatsapp_sessions")
        .select("id, phone, guest_name, booking_done, last_message_at, created_at, conversation")
        .order("last_message_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute().data or []
    )
    # Add message count and last message preview for each session
    for row in rows:
        conv = row.get("conversation") or []
        row["message_count"] = len(conv)
        last = next((m for m in reversed(conv) if m.get("role") == "assistant"), None)
        row["last_bot_message"] = last.get("content", "")[:80] if last else ""
        # Don't send full conversation in list view — save bandwidth
        del row["conversation"]

    pages = max(1, -(-total // limit))
    return {"data": rows, "total": total, "page": page, "pages": pages}


@app.get("/api/whatsapp/conversations/{phone}")
def get_wa_conversation_thread(phone: str, _=Depends(_verify_token)):
    """Full message thread for a specific phone number."""
    result = (
        supabase.table("whatsapp_sessions")
        .select("*")
        .eq("phone", phone)
        .execute()
    )
    if not result.data:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Conversation not found")
    return result.data[0]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("client_main:app", host="0.0.0.0", port=8003, reload=True)
