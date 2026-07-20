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

# Load .env — try parent dir (local dev) then current dir (Docker)
_parent_env = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(_parent_env if os.path.exists(_parent_env) else '.env')

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
DASHBOARD_USER = os.getenv("DASHBOARD_USERNAME", "admin")
DASHBOARD_PASS = os.getenv("DASHBOARD_PASSWORD", "admin")
JWT_SECRET = os.getenv("DASHBOARD_JWT_SECRET", secrets.token_hex(32))
JWT_ALGO = "HS256"
JWT_EXPIRY_HOURS = 24

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
bearer_scheme = HTTPBearer(auto_error=False)

app = FastAPI(title="Hotel Voice Agent Dashboard API")

@app.get("/health")
def health(): return {"status": "ok"}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str
    password: str


def _make_token() -> str:
    payload = {
        "sub": DASHBOARD_USER,
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
    if body.username != DASHBOARD_USER or body.password != DASHBOARD_PASS:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"token": _make_token()}


@app.get("/api/me")
def me(creds: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    _verify_token(creds)
    return {"username": DASHBOARD_USER}


# ---------------------------------------------------------------------------
# /api/stats
# ---------------------------------------------------------------------------

@app.get("/api/stats")
def get_stats():
    calls_r = supabase.table("calls").select("id", count="exact").execute()
    guests_r = supabase.table("guests").select("id", count="exact").execute()
    bookings_r = supabase.table("bookings").select("id", count="exact").execute()
    events_r = supabase.table("events").select("id", count="exact").execute()
    wa_r = supabase.table("whatsapp_logs").select("id", count="exact").execute()

    pending_r = supabase.table("bookings").select("id", count="exact").eq("status", "pending").execute()
    confirmed_r = supabase.table("bookings").select("id", count="exact").eq("status", "confirmed").execute()
    cancelled_r = supabase.table("bookings").select("id", count="exact").eq("status", "cancelled").execute()

    return {
        "calls": calls_r.count or 0,
        "guests": guests_r.count or 0,
        "bookings": bookings_r.count or 0,
        "events": events_r.count or 0,
        "whatsapp_sent": wa_r.count or 0,
        "pending_bookings": pending_r.count or 0,
        "confirmed_bookings": confirmed_r.count or 0,
        "cancelled_bookings": cancelled_r.count or 0,
    }


# ---------------------------------------------------------------------------
# /api/analytics
# ---------------------------------------------------------------------------

@app.get("/api/analytics")
def get_analytics():
    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)
    seven_days_ago = now - timedelta(days=7)

    # Fetch all calls (only fields we need)
    calls_r = supabase.table("calls").select("created_at, language, direction").execute()
    calls = calls_r.data or []

    # Fetch all bookings
    bookings_r = supabase.table("bookings").select("room_type, status, created_at").execute()
    bookings = bookings_r.data or []

    # --- Calls trend: last 30 days ---
    day_counts: dict[str, int] = defaultdict(int)
    for i in range(30):
        day = (thirty_days_ago + timedelta(days=i)).strftime("%Y-%m-%d")
        day_counts[day] = 0

    calls_this_week = 0
    calls_this_month = 0

    for c in calls:
        raw = c.get("created_at")
        if not raw:
            continue
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            continue
        day_str = dt.strftime("%Y-%m-%d")
        if dt >= thirty_days_ago:
            day_counts[day_str] = day_counts.get(day_str, 0) + 1
            calls_this_month += 1
        if dt >= seven_days_ago:
            calls_this_week += 1

    calls_trend = [{"date": d, "count": day_counts[d]} for d in sorted(day_counts.keys())]

    # --- Language distribution ---
    lang_counts: dict[str, int] = defaultdict(int)
    for c in calls:
        lang = c.get("language") or "unknown"
        lang_counts[lang] += 1
    language_dist = [{"language": k, "count": v} for k, v in lang_counts.items()]

    # --- Direction distribution ---
    dir_counts: dict[str, int] = defaultdict(int)
    for c in calls:
        d = c.get("direction") or "unknown"
        dir_counts[d] += 1
    direction_dist = [{"direction": k, "count": v} for k, v in dir_counts.items()]

    # --- Room types ---
    room_counts: dict[str, int] = defaultdict(int)
    for b in bookings:
        rt = b.get("room_type") or "unknown"
        room_counts[rt] += 1
    room_types = [{"room_type": k, "count": v} for k, v in room_counts.items()]

    # --- Booking status ---
    status_counts: dict[str, int] = defaultdict(int)
    for b in bookings:
        st = b.get("status") or "unknown"
        status_counts[st] += 1
    booking_status = [{"status": k, "count": v} for k, v in status_counts.items()]

    return {
        "calls_trend": calls_trend,
        "language_dist": language_dist,
        "direction_dist": direction_dist,
        "room_types": room_types,
        "booking_status": booking_status,
        "calls_this_week": calls_this_week,
        "calls_this_month": calls_this_month,
    }


# ---------------------------------------------------------------------------
# /api/calls
# ---------------------------------------------------------------------------

@app.get("/api/calls")
def get_calls(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: str = Query(None),
    direction: str = Query(None),
    language: str = Query(None),
):
    offset = (page - 1) * limit

    # Build base query
    def _apply_filters(q):
        if search:
            q = q.ilike("phone_number", f"%{search}%")
        if direction:
            q = q.eq("direction", direction)
        if language:
            q = q.eq("language", language)
        return q

    # Count query
    count_q = supabase.table("calls").select("id", count="exact")
    count_q = _apply_filters(count_q)
    count_r = count_q.execute()
    total = count_r.count or 0

    # Data query
    data_q = supabase.table("calls").select(
        "id, call_sid, phone_number, direction, language, started_at, ended_at, created_at, recording_url"
    ).order("created_at", desc=True).range(offset, offset + limit - 1)
    data_q = _apply_filters(data_q)
    data_r = data_q.execute()

    pages = max(1, -(-total // limit))  # ceiling division
    return {"data": data_r.data or [], "total": total, "page": page, "pages": pages}


# ---------------------------------------------------------------------------
# /api/calls/{call_sid}
# ---------------------------------------------------------------------------

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

    def _apply_filters(q):
        if search:
            q = q.ilike("room_type", f"%{search}%")
        if status:
            q = q.eq("status", status)
        return q

    count_q = supabase.table("bookings").select("id", count="exact")
    count_q = _apply_filters(count_q)
    count_r = count_q.execute()
    total = count_r.count or 0

    data_q = supabase.table("bookings").select(
        "*, guests(name, phone)"
    ).order("created_at", desc=True).range(offset, offset + limit - 1)
    data_q = _apply_filters(data_q)
    data_r = data_q.execute()

    pages = max(1, -(-total // limit))
    return {"data": data_r.data or [], "total": total, "page": page, "pages": pages}


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

    def _apply_filters(q):
        if search:
            q = q.ilike("name", f"%{search}%")
        return q

    count_q = supabase.table("guests").select("id", count="exact")
    count_q = _apply_filters(count_q)
    count_r = count_q.execute()
    total = count_r.count or 0

    data_q = supabase.table("guests").select("*").order("created_at", desc=True).range(offset, offset + limit - 1)
    data_q = _apply_filters(data_q)
    data_r = data_q.execute()

    pages = max(1, -(-total // limit))
    return {"data": data_r.data or [], "total": total, "page": page, "pages": pages}


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

    def _apply_filters(q):
        if search:
            q = q.ilike("event_type", f"%{search}%")
        if status:
            q = q.eq("status", status)
        return q

    count_q = supabase.table("events").select("id", count="exact")
    count_q = _apply_filters(count_q)
    count_r = count_q.execute()
    total = count_r.count or 0

    data_q = supabase.table("events").select(
        "*, guests(name, phone)"
    ).order("created_at", desc=True).range(offset, offset + limit - 1)
    data_q = _apply_filters(data_q)
    data_r = data_q.execute()

    pages = max(1, -(-total // limit))
    return {"data": data_r.data or [], "total": total, "page": page, "pages": pages}


# ---------------------------------------------------------------------------
# /api/whatsapp
# ---------------------------------------------------------------------------

@app.get("/api/whatsapp")
def get_whatsapp(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: str = Query(None),
):
    offset = (page - 1) * limit

    def _apply_filters(q):
        if status:
            q = q.eq("status", status)
        return q

    count_q = supabase.table("whatsapp_logs").select("id", count="exact")
    count_q = _apply_filters(count_q)
    count_r = count_q.execute()
    total = count_r.count or 0

    data_q = supabase.table("whatsapp_logs").select("*").order("sent_at", desc=True).range(offset, offset + limit - 1)
    data_q = _apply_filters(data_q)
    data_r = data_q.execute()

    pages = max(1, -(-total // limit))
    return {"data": data_r.data or [], "total": total, "page": page, "pages": pages}


# ---------------------------------------------------------------------------
# /api/usage  +  /api/usage/summary
# ---------------------------------------------------------------------------

@app.get("/api/usage")
def get_usage(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    service: str = Query(None),
):
    offset = (page - 1) * limit

    def _apply(q):
        if service:
            q = q.eq("service", service)
        return q

    count_q = supabase.table("usage_logs").select("id", count="exact")
    total   = _apply(count_q).execute().count or 0

    data_q  = supabase.table("usage_logs").select("*").order("created_at", desc=True).range(offset, offset + limit - 1)
    rows    = _apply(data_q).execute().data or []

    pages = max(1, -(-total // limit))
    return {"data": rows, "total": total, "page": page, "pages": pages}


@app.get("/api/usage/summary")
def get_usage_summary():
    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)

    rows = supabase.table("usage_logs").select(
        "service, model, cost_usd, audio_in_seconds, audio_out_seconds, "
        "input_tokens, output_tokens, duration_seconds, created_at"
    ).execute().data or []

    total_cost   = 0.0
    by_service   = defaultdict(lambda: {"cost": 0.0, "count": 0})
    daily_cost: dict[str, float] = defaultdict(float)

    # seed last 30 days
    for i in range(30):
        day = (thirty_days_ago + timedelta(days=i)).strftime("%Y-%m-%d")
        daily_cost[day] = 0.0

    total_audio_in  = 0.0
    total_audio_out = 0.0
    total_call_dur  = 0.0
    total_in_tok    = 0
    total_out_tok   = 0

    for r in rows:
        cost = r.get("cost_usd") or 0.0
        svc  = r.get("service", "unknown")
        total_cost += cost
        by_service[svc]["cost"]  += cost
        by_service[svc]["count"] += 1
        total_audio_in  += r.get("audio_in_seconds")  or 0.0
        total_audio_out += r.get("audio_out_seconds") or 0.0
        total_call_dur  += r.get("duration_seconds")  or 0.0
        total_in_tok    += r.get("input_tokens")       or 0
        total_out_tok   += r.get("output_tokens")      or 0

        raw = r.get("created_at")
        if raw:
            try:
                dt  = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                day = dt.strftime("%Y-%m-%d")
                if dt >= thirty_days_ago:
                    daily_cost[day] += cost
            except Exception:
                pass

    cost_trend = [{"date": d, "cost": round(daily_cost[d], 6)} for d in sorted(daily_cost.keys())]
    service_breakdown = [
        {"service": k, "cost": round(v["cost"], 6), "count": v["count"]}
        for k, v in by_service.items()
    ]

    return {
        "total_cost_usd":     round(total_cost, 6),
        "total_audio_in_min": round(total_audio_in / 60, 2),
        "total_audio_out_min": round(total_audio_out / 60, 2),
        "total_call_min":     round(total_call_dur / 60, 2),
        "total_input_tokens": total_in_tok,
        "total_output_tokens": total_out_tok,
        "cost_trend":         cost_trend,
        "service_breakdown":  service_breakdown,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=True)
