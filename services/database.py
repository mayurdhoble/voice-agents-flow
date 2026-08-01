import os
import logging
from datetime import datetime, timezone

log = logging.getLogger("agent")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    if not SUPABASE_URL or not SUPABASE_KEY:
        log.warning("[DB] SUPABASE_URL / SUPABASE_KEY not set — DB disabled")
        return None
    try:
        from supabase import create_client
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
        log.info("[DB] Supabase client initialised")
    except Exception as e:
        log.error(f"[DB] Failed to init Supabase client: {e}")
    return _client


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── calls ────────────────────────────────────────────────────────────────────

def save_call(call_sid: str, phone_number: str, direction: str, language: str,
              started_at: str, ended_at: str, transcript: list,
              recording_url: str | None = None) -> str | None:
    db = _get_client()
    if not db:
        return None
    try:
        row = {
            "call_sid":     call_sid,
            "phone_number": phone_number,
            "direction":    direction,
            "language":     language,
            "started_at":   started_at,
            "ended_at":     ended_at,
            "transcript":   transcript,
        }
        if recording_url:
            row["recording_url"] = recording_url
        result = db.table("calls").insert(row).execute()
        row_id = result.data[0]["id"]
        log.info(f"[DB] call saved → {row_id}")
        return row_id
    except Exception as e:
        log.error(f"[DB] save_call: {e}")
        return None


# ─── guests ───────────────────────────────────────────────────────────────────

def upsert_guest(name: str, phone: str) -> str | None:
    db = _get_client()
    if not db:
        return None
    try:
        # Match on name+phone together — phone alone is unreliable when it's
        # "unknown" (VoBiz doesn't always send the caller number), which would
        # collapse every caller into the same guest row.
        query = db.table("guests").select("id").eq("name", name)
        if phone and phone != "unknown":
            query = query.eq("phone", phone)
        existing = query.execute()
        if existing.data:
            guest_id = existing.data[0]["id"]
            if phone and phone != "unknown":
                db.table("guests").update({
                    "phone":      phone,
                    "updated_at": _now(),
                }).eq("id", guest_id).execute()
            log.info(f"[DB] guest updated → {guest_id}")
            return guest_id
        result = db.table("guests").insert({"name": name, "phone": phone}).execute()
        guest_id = result.data[0]["id"]
        log.info(f"[DB] guest created → {guest_id}")
        return guest_id
    except Exception as e:
        log.error(f"[DB] upsert_guest: {e}")
        return None


# ─── bookings ─────────────────────────────────────────────────────────────────

def save_booking(call_sid: str, guest_id: str, room_type: str,
                 checkin_date: str | None, checkout_date: str | None,
                 nights: int | None, airport_pickup: bool | None,
                 extra_bed: bool | None) -> str | None:
    db = _get_client()
    if not db:
        return None
    try:
        result = db.table("bookings").insert({
            "call_sid":      call_sid,
            "guest_id":      guest_id,
            "room_type":     room_type,
            "checkin_date":  checkin_date,
            "checkout_date": checkout_date,
            "nights":        nights,
            "airport_pickup": airport_pickup or False,
            "extra_bed":      extra_bed or False,
            "status":         "pending",
            "whatsapp_sent":  False,
        }).execute()
        booking_id = result.data[0]["id"]
        log.info(f"[DB] booking saved → {booking_id}")
        return booking_id
    except Exception as e:
        log.error(f"[DB] save_booking: {e}")
        return None


# ─── events ───────────────────────────────────────────────────────────────────

def save_event(call_sid: str, guest_id: str, event_type: str | None,
               event_date: str | None, num_guests: int | None) -> str | None:
    db = _get_client()
    if not db:
        return None
    try:
        result = db.table("events").insert({
            "call_sid":   call_sid,
            "guest_id":   guest_id,
            "event_type": event_type,
            "event_date": event_date,
            "num_guests": num_guests,
            "status":     "inquiry",
        }).execute()
        event_id = result.data[0]["id"]
        log.info(f"[DB] event saved → {event_id}")
        return event_id
    except Exception as e:
        log.error(f"[DB] save_event: {e}")
        return None


# ─── requests ─────────────────────────────────────────────────────────────────

def save_request(call_sid: str, guest_id: str | None, guest_name: str | None,
                 request_type: str, details: str | None,
                 date_needed: str | None = None) -> str | None:
    db = _get_client()
    if not db:
        return None
    try:
        result = db.table("requests").insert({
            "call_sid":     call_sid,
            "guest_id":     guest_id,
            "guest_name":   guest_name,
            "request_type": request_type,
            "details":      details,
            "date_needed":  date_needed,
            "status":       "new",
        }).execute()
        req_id = result.data[0]["id"]
        log.info(f"[DB] request saved → {req_id} ({request_type})")
        return req_id
    except Exception as e:
        log.error(f"[DB] save_request: {e}")
        return None


def update_request_status(request_id: str, status: str) -> None:
    db = _get_client()
    if not db:
        return
    try:
        db.table("requests").update({
            "status":     status,
            "updated_at": _now(),
        }).eq("id", request_id).execute()
        log.info(f"[DB] request {request_id} → status={status}")
    except Exception as e:
        log.error(f"[DB] update_request_status: {e}")


# ─── bookings — status helpers ────────────────────────────────────────────────

def update_djubo_booking_id(booking_id: str, djubo_reservation_id: str) -> None:
    db = _get_client()
    if not db:
        return
    try:
        db.table("bookings").update({
            "djubo_booking_id": djubo_reservation_id,
            "status": "confirmed",
        }).eq("id", booking_id).execute()
        log.info(f"[DB] booking {booking_id} → djubo_id={djubo_reservation_id}, status=confirmed")
    except Exception as e:
        log.error(f"[DB] update_djubo_booking_id: {e}")


def update_guest_djubo_tracker(guest_id: str, tracker_id: int) -> None:
    db = _get_client()
    if not db:
        return
    try:
        db.table("guests").update({
            "djubo_tracker_id": str(tracker_id),
            "updated_at": _now(),
        }).eq("id", guest_id).execute()
        log.info(f"[DB] guest {guest_id} → djubo_tracker_id={tracker_id}")
    except Exception as e:
        log.error(f"[DB] update_guest_djubo_tracker: {e}")


def mark_whatsapp_sent(booking_id: str) -> None:
    db = _get_client()
    if not db:
        return
    try:
        db.table("bookings").update({"whatsapp_sent": True}).eq("id", booking_id).execute()
        log.info(f"[DB] booking {booking_id} → whatsapp_sent=True")
    except Exception as e:
        log.error(f"[DB] mark_whatsapp_sent: {e}")


# ─── whatsapp_logs ────────────────────────────────────────────────────────────

# ─── dashboard read queries ───────────────────────────────────────────────────

def get_stats() -> dict:
    db = _get_client()
    if not db:
        return {"calls": 0, "bookings": 0, "events": 0, "whatsapp_sent": 0, "guests": 0}
    try:
        calls    = db.table("calls").select("id", count="exact").execute().count or 0
        bookings = db.table("bookings").select("id", count="exact").execute().count or 0
        events   = db.table("events").select("id", count="exact").execute().count or 0
        whatsapp = db.table("bookings").select("id", count="exact").eq("whatsapp_sent", True).execute().count or 0
        guests   = db.table("guests").select("id", count="exact").execute().count or 0
        return {"calls": calls, "bookings": bookings, "events": events,
                "whatsapp_sent": whatsapp, "guests": guests}
    except Exception as e:
        log.error(f"[DB] get_stats: {e}")
        return {}


def get_calls(limit: int = 50, offset: int = 0) -> list:
    db = _get_client()
    if not db:
        return []
    try:
        return db.table("calls").select(
            "id, call_sid, phone_number, direction, language, started_at, ended_at, created_at"
        ).order("created_at", desc=True).range(offset, offset + limit - 1).execute().data
    except Exception as e:
        log.error(f"[DB] get_calls: {e}")
        return []


def get_call(call_sid: str) -> dict | None:
    db = _get_client()
    if not db:
        return None
    try:
        rows = db.table("calls").select("*").eq("call_sid", call_sid).execute().data
        return rows[0] if rows else None
    except Exception as e:
        log.error(f"[DB] get_call: {e}")
        return None


def get_bookings(limit: int = 50, offset: int = 0) -> list:
    db = _get_client()
    if not db:
        return []
    try:
        return db.table("bookings").select(
            "*, guests(name, phone)"
        ).order("created_at", desc=True).range(offset, offset + limit - 1).execute().data
    except Exception as e:
        log.error(f"[DB] get_bookings: {e}")
        return []


def get_events(limit: int = 50, offset: int = 0) -> list:
    db = _get_client()
    if not db:
        return []
    try:
        return db.table("events").select(
            "*, guests(name, phone)"
        ).order("created_at", desc=True).range(offset, offset + limit - 1).execute().data
    except Exception as e:
        log.error(f"[DB] get_events: {e}")
        return []


def get_guest_by_phone(phone: str) -> dict | None:
    """Lookup guest + their last booking by phone. Used at call start for returning guest recognition."""
    db = _get_client()
    if not db:
        return None
    try:
        clean = phone.replace("+91", "").replace("+", "").lstrip("91") if len(phone) > 10 else phone
        variants = [phone, f"+91{clean}", f"91{clean}", clean]
        for variant in variants:
            rows = db.table("guests").select(
                "id, name, phone, djubo_tracker_id"
            ).eq("phone", variant).execute().data
            if rows:
                guest = rows[0]
                bookings = db.table("bookings").select(
                    "checkin_date, checkout_date, room_type, status"
                ).eq("guest_id", guest["id"]).order("created_at", desc=True).limit(1).execute().data
                guest["last_booking"] = bookings[0] if bookings else None
                log.info(f"[DB] returning guest found: {guest['name']} (phone={variant})")
                return guest
        return None
    except Exception as e:
        log.error(f"[DB] get_guest_by_phone: {e}")
        return None


def get_guests(limit: int = 50, offset: int = 0) -> list:
    db = _get_client()
    if not db:
        return []
    try:
        return db.table("guests").select(
            "*"
        ).order("created_at", desc=True).range(offset, offset + limit - 1).execute().data
    except Exception as e:
        log.error(f"[DB] get_guests: {e}")
        return []


# ─── usage_logs ───────────────────────────────────────────────────────────────

def log_usage(
    call_sid: str,
    service: str,
    model: str,
    audio_in_seconds: float | None = None,
    audio_out_seconds: float | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    duration_seconds: float | None = None,
    cost_usd: float | None = None,
) -> None:
    db = _get_client()
    if not db:
        return
    try:
        db.table("usage_logs").insert({
            "call_sid":          call_sid,
            "service":           service,
            "model":             model,
            "audio_in_seconds":  audio_in_seconds,
            "audio_out_seconds": audio_out_seconds,
            "input_tokens":      input_tokens,
            "output_tokens":     output_tokens,
            "duration_seconds":  duration_seconds,
            "cost_usd":          round(cost_usd, 8) if cost_usd is not None else None,
            "created_at":        _now(),
        }).execute()
        log.info(f"[DB] usage_log saved → {service} | ${cost_usd:.6f}" if cost_usd else f"[DB] usage_log saved → {service}")
    except Exception as e:
        log.error(f"[DB] log_usage: {e}")


# ─── whatsapp_logs ────────────────────────────────────────────────────────────

# ─── whatsapp_sessions (bot conversations) ───────────────────────────────────

def get_whatsapp_session(phone: str) -> dict | None:
    db = _get_client()
    if not db:
        return None
    try:
        result = db.table("whatsapp_sessions").select("*").eq("phone", phone).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        log.error(f"[DB] get_whatsapp_session: {e}")
        return None


def save_whatsapp_session(phone: str, session: dict) -> None:
    db = _get_client()
    if not db:
        return
    try:
        row = {
            "phone":           phone,
            "guest_name":      session.get("guest_name"),
            "conversation":    session.get("conversation", []),
            "booking_done":    session.get("booking_done", False),
            "last_message_at": session.get("last_message_at") or _now(),
        }
        existing = db.table("whatsapp_sessions").select("id").eq("phone", phone).execute()
        if existing.data:
            db.table("whatsapp_sessions").update(row).eq("phone", phone).execute()
        else:
            db.table("whatsapp_sessions").insert(row).execute()
        log.info(f"[DB] whatsapp_session saved → {phone}")
    except Exception as e:
        log.error(f"[DB] save_whatsapp_session: {e}")


def get_recent_call_transcript(phone: str) -> list | None:
    """Return transcript of the most recent call from this phone number, or None."""
    db = _get_client()
    if not db:
        return None
    try:
        # Normalise: strip leading country code so 917820951897 matches 7820951897
        digits = phone.replace("+", "").replace(" ", "").strip()
        short  = digits[-10:] if len(digits) > 10 else digits
        result = (
            db.table("calls")
            .select("transcript")
            .ilike("phone_number", f"%{short}")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if result.data and result.data[0].get("transcript"):
            return result.data[0]["transcript"]
        return None
    except Exception as e:
        log.error(f"[DB] get_recent_call_transcript: {e}")
        return None


def check_duplicate_booking(phone: str, checkin: str, checkout: str) -> bool:
    """Return True if a booking already exists for this phone + overlapping dates."""
    db = _get_client()
    if not db:
        return False
    try:
        digits = phone.replace("+", "").replace(" ", "").strip()
        short  = digits[-10:] if len(digits) > 10 else digits
        guests = (
            db.table("guests").select("id")
            .ilike("phone", f"%{short}")
            .execute()
        )
        if not guests.data:
            return False
        guest_ids = [g["id"] for g in guests.data]
        for gid in guest_ids:
            result = (
                db.table("bookings").select("id")
                .eq("guest_id", gid)
                .eq("checkin_date", checkin)
                .execute()
            )
            if result.data:
                return True
        return False
    except Exception as e:
        log.error(f"[DB] check_duplicate_booking: {e}")
        return False


def log_whatsapp(booking_id: str, phone: str, template: str, status: str) -> None:
    db = _get_client()
    if not db:
        return
    try:
        db.table("whatsapp_logs").insert({
            "booking_id":    booking_id,
            "phone":         phone,
            "template_name": template,
            "status":        status,
            "sent_at":       _now(),
        }).execute()
        log.info(f"[DB] whatsapp_log saved → {status}")
    except Exception as e:
        log.error(f"[DB] log_whatsapp: {e}")


# ─── Payments ─────────────────────────────────────────────────────────────────

def save_payment(booking_id: str, txnid: str, phone: str,
                 amount_due: int, amount_total: int, balance: int,
                 payment_link: str) -> bool:
    """Persist a new pending payment record. Returns True on success."""
    db = _get_client()
    if not db:
        return False
    try:
        db.table("payments").insert({
            "booking_id":   booking_id,
            "txnid":        txnid,
            "phone":        phone,
            "amount_due":   amount_due,
            "amount_total": amount_total,
            "balance":      balance,
            "payment_link": payment_link,
            "status":       "pending",
            "created_at":   _now(),
        }).execute()
        log.info(f"[DB] payment saved → txnid={txnid} due=₹{amount_due:,} status=pending")
        return True
    except Exception as e:
        log.error(f"[DB] save_payment: {e}")
        return False


def get_payment_by_txnid(txnid: str) -> dict | None:
    """Fetch a payment record by txnid — used to recover context after redeploy."""
    db = _get_client()
    if not db:
        return None
    try:
        rows = db.table("payments").select("*").eq("txnid", txnid).execute().data
        return rows[0] if rows else None
    except Exception as e:
        log.error(f"[DB] get_payment_by_txnid: {e}")
        return None


def update_payment_paid(txnid: str, amount_paid: int) -> None:
    """Mark a payment as paid with the actual amount received from PayU."""
    db = _get_client()
    if not db:
        return
    try:
        db.table("payments").update({
            "status":       "paid",
            "amount_paid":  amount_paid,
            "paid_at":      _now(),
        }).eq("txnid", txnid).execute()
        log.info(f"[DB] payment txnid={txnid} → status=paid amount_paid=₹{amount_paid:,}")
    except Exception as e:
        log.error(f"[DB] update_payment_paid: {e}")
