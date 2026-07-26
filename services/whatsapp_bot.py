"""
WhatsApp bot — hotel Q&A + full booking flow via text messages.
Uses Gemini 2.5 Flash via OpenRouter.
"""
import os
import json
import httpx
import logging
from datetime import datetime, timezone

log = logging.getLogger("agent")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
WA_BOT_MODEL       = os.getenv("WA_BOT_MODEL", "google/gemini-2.5-flash")

_SYSTEM_PROMPT = """\
You are Maya, the virtual front-desk host for Lotus Sutra Goa — a boutique beach hotel in Arambol, Goa. You are replying via WhatsApp text. Be warm, helpful, and concise.

[Style]
Plain text only — no markdown asterisks, no bullet symbols, no headers. Line breaks are fine.
Keep replies short: 1–3 sentences unless full detail is needed.
Warm, friendly, Indian-English tone. Switch instantly to Hindi/Hinglish if guest writes in Hindi.
ALWAYS answer the guest's question first before asking for missing booking info.
Ask only ONE question at a time when collecting booking details.
Never repeat information already confirmed in this conversation.

[Booking flow — collect only what is missing, in this order]
name → check-in date → check-out date → number of guests → room preference → meal plan (CP = breakfast included / EP = room only)
Never re-ask for details already provided. If the guest already gave some info in a prior call (see transcript below), skip those questions.

[Room types]
Standard Queen, Superior Twin, Superior Queen, Standard Triple, Superior Triple, Standard Twin.
Guidance only if guest is unsure: Standard rooms are cozy, Superior rooms have better amenities and balcony. Sea view cottages are most popular and limited.

[Pricing]
Quote pricing only when guest asks. Never bring it up unprompted.
If live rates are available in context, quote them directly. Otherwise ask for dates first.

[Booking confirmation — critical]
booking_confirmed = true ONLY when the guest explicitly says yes / confirm / book it / haan karo / go ahead AFTER you have presented all collected details back to them for review.
Showing interest or giving dates alone is NOT a confirmation.

[Duplicate booking]
If you are told a booking already exists for these dates, inform the guest politely — do not create another one.

[Hotel facts]
Boutique beach property, Lotus Sutra, Arambol, Goa. Restaurant, pool. Arambol Beach 5-minute walk.
Check-in: 2 PM. Checkout: 11 AM.
Restaurant Sunshine Russ, 8 AM–midnight. Indian, continental, Chinese, Israeli, Italian.
Pool: 9 AM–7 PM. Complimentary amenities for in-house guests: pool, table tennis, badminton, carrom, boxing bag, basketball.
Pets welcome; refundable security deposit at check-in.
No airport pickup — reliable cab contact can be shared. Mopa airport ~30 km, ~45 mins.
Extra bed (Premium rooms only): adults Rs 1500/night, children Rs 1100/night.
Cancellation policy: non-refundable.
For unknown details: "Our team will confirm that when they reach out."

[Output format — ALWAYS return valid JSON, nothing else]
{
  "reply": "your plain-text WhatsApp reply here",
  "booking_confirmed": false,
  "collected": {
    "name": null,
    "checkin": null,
    "checkout": null,
    "guests": null,
    "room_type": null,
    "meal_plan": null
  }
}
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def process_whatsapp_message(phone: str, incoming_text: str) -> str:
    """
    Process one incoming WhatsApp message. Returns the reply text to send back.
    Updates session in DB; triggers booking pipeline on confirmation.
    """
    from services.database import (
        get_whatsapp_session, save_whatsapp_session, get_recent_call_transcript,
    )

    # Load existing session
    session = get_whatsapp_session(phone) or {
        "phone": phone,
        "guest_name": None,
        "conversation": [],
        "booking_done": False,
    }

    # Pull most recent call transcript for this phone number
    transcript_context = ""
    call_transcript = get_recent_call_transcript(phone)
    if call_transcript:
        lines = []
        for turn in call_transcript:
            role = "Guest" if turn.get("role") == "user" else "Maya"
            content = turn.get("content", "")
            if content.strip():
                lines.append(f"{role}: {content.strip()}")
        if lines:
            transcript_context = (
                "\n\n[Previous phone call transcript with this guest — use as context. "
                "Do not re-ask for information already confirmed here:]\n"
                + "\n".join(lines)
            )

    system = _SYSTEM_PROMPT + transcript_context

    # Add duplicate-booking notice if already booked
    if session.get("booking_done"):
        system += "\n\n[Note: This guest already has a confirmed booking from this WhatsApp conversation. Answer questions but do not create another booking.]"

    # Build LLM message list
    history = session.get("conversation", [])
    messages = [{"role": "system", "content": system}]
    for msg in history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": incoming_text})

    # Call LLM
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": WA_BOT_MODEL,
                    "messages": messages,
                    "response_format": {"type": "json_object"},
                    "temperature": 0.3,
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            log.info(f"[WA-BOT] LLM response for {phone}: {json.dumps(parsed, ensure_ascii=False)[:200]}")
    except Exception as e:
        log.error(f"[WA-BOT] LLM error for {phone}: {e}")
        return "Sorry, I'm having a little trouble right now. Please call us directly — we'd love to help!"

    reply_text        = parsed.get("reply", "").strip()
    booking_confirmed = parsed.get("booking_confirmed", False)
    collected         = parsed.get("collected") or {}

    if not reply_text:
        reply_text = "Sorry, something went wrong. Please try again or call us directly!"

    # Update conversation history with timestamps
    ts = _now_iso()
    history.append({"role": "user",      "content": incoming_text, "ts": ts})
    history.append({"role": "assistant", "content": reply_text,    "ts": ts})

    # Merge newly collected fields into session (don't overwrite existing with null)
    stored = session.get("collected") or {}
    for key, val in collected.items():
        if val is not None:
            stored[key] = val
    session["collected"] = stored

    # Update guest name if we now know it
    if stored.get("name"):
        session["guest_name"] = stored["name"]

    # Handle booking confirmation
    if booking_confirmed and not session.get("booking_done"):
        done = await _confirm_booking(phone, stored, session)
        session["booking_done"] = done

    session["conversation"]    = history
    session["last_message_at"] = ts
    save_whatsapp_session(phone, session)

    return reply_text


async def _confirm_booking(phone: str, collected: dict, session: dict) -> bool:
    """Create booking in Supabase + Djubo + send WhatsApp confirmation template."""
    from services.database import (
        upsert_guest, save_booking, log_whatsapp, mark_whatsapp_sent,
        update_djubo_booking_id, update_guest_djubo_tracker, check_duplicate_booking,
    )
    from services.djubo import book_room
    from services.whatsapp import send_booking_confirmation

    name      = collected.get("name") or session.get("guest_name") or "Guest"
    checkin   = collected.get("checkin")
    checkout  = collected.get("checkout")
    room_type = collected.get("room_type") or "Standard Queen"

    if not checkin or not checkout:
        log.warning(f"[WA-BOT] Booking confirmed for {phone} but missing dates — skipping")
        return False

    # Compute nights
    try:
        from datetime import date
        nights = (date.fromisoformat(checkout) - date.fromisoformat(checkin)).days
    except Exception:
        nights = None

    # Duplicate check — same phone + overlapping dates
    if check_duplicate_booking(phone, checkin, checkout):
        log.info(f"[WA-BOT] Duplicate booking for {phone} {checkin}–{checkout} — skipping Djubo")
        return True

    # Guest + booking in Supabase
    guest_id   = upsert_guest(name=name, phone=phone)
    booking_id = save_booking(
        call_sid       = f"wa_{phone}",
        guest_id       = guest_id,
        room_type      = room_type,
        checkin_date   = checkin,
        checkout_date  = checkout,
        nights         = nights,
        airport_pickup = None,
        extra_bed      = None,
    )
    if not booking_id:
        return False

    # Djubo
    name_parts  = name.split(maxsplit=1)
    reservation = await book_room(
        first_name = name_parts[0],
        last_name  = name_parts[1] if len(name_parts) > 1 else name_parts[0],
        phone      = phone,
        email      = "",
        checkin    = checkin,
        checkout   = checkout,
        room_type  = room_type,
    )
    if reservation:
        update_djubo_booking_id(booking_id, reservation.get("reservation_id", ""))
        tracker = reservation.get("djubo_guest_tracker_id")
        if tracker and guest_id:
            update_guest_djubo_tracker(guest_id, tracker)

    # WhatsApp confirmation template
    ok = await send_booking_confirmation(
        phone      = phone,
        guest_name = name,
        room_type  = room_type,
        checkin    = checkin,
        checkout   = checkout,
        nights     = nights,
    )
    log_whatsapp(booking_id, phone, "booking_confirmation", "sent" if ok else "failed")
    if ok:
        mark_whatsapp_sent(booking_id)
        log.info(f"[WA-BOT] Booking confirmed + WhatsApp sent → {phone}")
    else:
        log.warning(f"[WA-BOT] Booking confirmed but WhatsApp template failed → {phone}")

    return True
