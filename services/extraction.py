import os
import json
import httpx
import logging

log = logging.getLogger("agent")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL   = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")

_SYSTEM_PROMPT = """\
You are a data extraction assistant for a hotel voice AI. Given a call transcript between a hotel assistant (Maya) and a guest, extract structured information.

Return ONLY valid JSON with exactly these fields (use null if not mentioned or unclear):
{
  "guest_name":       string or null,
  "checkin_date":     "YYYY-MM-DD" or null,
  "checkout_date":    "YYYY-MM-DD" or null,
  "nights":           integer or null,
  "room_type":        string or null,
  "airport_pickup":   true/false/null,
  "extra_bed":        true/false/null,
  "booking_intent":   true or false,
  "booking_confirmed": true or false,
  "event":            true or false,
  "event_type":       string or null,
  "event_date":       "YYYY-MM-DD" or null,
  "event_guests":     integer or null,
  "language":         "hi"/"en"/"mr" or "en",
  "call_summary":     "one concise sentence summary of the call",
  "special_requests": [
    {
      "type":        "airport_pickup" | "cab" | "extra_bed" | "early_checkin" | "late_checkout" | "restaurant" | "laundry" | "room_service" | "event" | "other",
      "details":     "exact details of what the guest asked",
      "date_needed": "YYYY-MM-DD" or null
    }
  ]
}

Rules:
- booking_intent = true only if guest provided name + at least one date + room type (all three present)
- booking_confirmed = true only if the guest explicitly confirmed they want to book — e.g. said "yes book it", "confirm", "haan book karo", "please book", "go ahead", "yes please". Asking about a room or giving dates alone is NOT a confirmation. Must be a clear yes/agreement to proceed with the booking.
- event = true if guest asked about birthday party, wedding, conference, or any function/event
- Dates: convert spoken/Hindi dates to YYYY-MM-DD. Assume year 2026 if not stated.
  Examples: "sattarah August" → "2026-08-17", "15th November" → "2026-11-15", "सोलह जून" → "2026-06-16"
- room_type: use exact names if mentioned — Deluxe, Premium Deluxe, Junior Suite, Executive Suite, Presidential Suite
- airport_pickup: true if guest asked about or confirmed airport pickup, false if declined, null if not mentioned
- extra_bed: true if guest asked about or confirmed extra bed, null if not mentioned
- language: dominant language spoken by the guest ("hi" for Hindi, "mr" for Marathi, "en" for English)
- special_requests: list EVERY specific service request the guest made. If airport_pickup=true add it here too. If event=true add it here too. Empty array [] if no requests.
- Return ONLY the JSON object — no markdown, no explanation, no extra text
"""


async def extract_from_transcript(conversation_history: list) -> dict:
    """Run LLM extraction on the full conversation. Returns structured dict."""
    if not conversation_history:
        return {}

    transcript = "\n".join(
        f"{'Guest' if m['role'] == 'user' else 'Maya'}: {m['content']}"
        for m in conversation_history
    )

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": OPENROUTER_MODEL,
                    "messages": [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user",   "content": f"Extract from this call transcript:\n\n{transcript}"},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0,
                },
            )
            resp.raise_for_status()
            rjson   = resp.json()
            content = rjson["choices"][0]["message"]["content"]
            extracted = json.loads(content)
            log.info(f"[EXTRACT] {json.dumps(extracted, ensure_ascii=False)}")

            # Log token usage
            usage = rjson.get("usage", {})
            extracted["_usage"] = {
                "model":         OPENROUTER_MODEL,
                "input_tokens":  usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
            }
            return extracted
    except Exception as e:
        log.error(f"[EXTRACT] Failed: {e}")
        return {}


async def run_post_call_pipeline(conversation_history: list, call_meta: dict):
    """
    Full post-call pipeline — runs as a background task after WebSocket closes.
    1. Extract structured data from transcript
    2. Save call, guest, booking, event to Supabase
    3. Send WhatsApp confirmation if booking or event detected
    """
    from services.database import (save_call, upsert_guest, save_booking,
                                   save_event, save_request, mark_whatsapp_sent,
                                   log_whatsapp, update_djubo_booking_id,
                                   update_guest_djubo_tracker)
    from services.whatsapp import send_booking_confirmation, send_event_confirmation, send_text_message
    from services.djubo import book_room

    log.info("[PIPELINE] Post-call pipeline started")

    extracted = await extract_from_transcript(conversation_history)
    if not extracted:
        log.warning("[PIPELINE] Extraction returned empty — skipping")
        return

    # Log OpenRouter extraction cost (gpt-4o-mini: $0.15/1M in, $0.60/1M out)
    _usage = extracted.pop("_usage", {})
    if _usage:
        _in_tok  = _usage.get("input_tokens", 0)
        _out_tok = _usage.get("output_tokens", 0)
        _or_cost = (_in_tok * 0.15 + _out_tok * 0.60) / 1_000_000
        from services.database import log_usage as _log_usage
        _log_usage(
            call_sid      = call_meta.get("call_sid", ""),
            service       = "openrouter",
            model         = _usage.get("model", "openai/gpt-4o-mini"),
            input_tokens  = _in_tok,
            output_tokens = _out_tok,
            cost_usd      = _or_cost,
        )

    phone = call_meta.get("phone_number", "")

    # 1. Save call record
    save_call(
        call_sid      = call_meta.get("call_sid", ""),
        phone_number  = phone,
        direction     = call_meta.get("direction", "inbound"),
        language      = extracted.get("language") or call_meta.get("language", "en"),
        started_at    = call_meta.get("started_at", ""),
        ended_at      = call_meta.get("ended_at", ""),
        transcript    = conversation_history,
        recording_url = call_meta.get("recording_url"),
    )

    # Decision summary — makes every downstream skip/trigger traceable in logs
    log.info(
        "[PIPELINE] flags — booking_intent=%s booking_confirmed=%s event=%s guest_name=%s phone=%s room_type=%s",
        extracted.get("booking_intent"), extracted.get("booking_confirmed"),
        extracted.get("event"), extracted.get("guest_name"), bool(phone), extracted.get("room_type"),
    )

    # 2. Upsert guest
    guest_id = None
    if extracted.get("guest_name") and phone:
        guest_id = upsert_guest(name=extracted["guest_name"], phone=phone)
    else:
        log.warning(
            "[PIPELINE] Guest not saved — %s. No guest_id ⇒ booking & WhatsApp will be skipped.",
            "no guest_name captured" if not extracted.get("guest_name") else "no phone number",
        )

    # 3. Save booking + Djubo + WhatsApp confirmation
    # booking_confirmed = guest explicitly said "yes book it" (stricter than booking_intent)
    if extracted.get("booking_confirmed") and guest_id and extracted.get("room_type"):
        log.info("[PIPELINE] Booking flow TRIGGERED → saving booking + Djubo + WhatsApp")
        booking_id = save_booking(
            call_sid       = call_meta.get("call_sid", ""),
            guest_id       = guest_id,
            room_type      = extracted.get("room_type"),
            checkin_date   = extracted.get("checkin_date"),
            checkout_date  = extracted.get("checkout_date"),
            nights         = extracted.get("nights"),
            airport_pickup = extracted.get("airport_pickup"),
            extra_bed      = extracted.get("extra_bed"),
        )

        # PayU payment-first flow: bill + 50% payment link → payment → Djubo + confirmation.
        # Only when PayU creds are configured; otherwise the legacy book-immediately flow runs.
        payment_started = False
        from payments.payu_client import is_configured as _payu_configured
        if (booking_id and _payu_configured() and phone and phone != "unknown"
                and extracted.get("checkin_date") and extracted.get("checkout_date")):
            from payments.payment_flow import start_payment_flow
            payment_started = await start_payment_flow(
                booking_id     = booking_id,
                guest_id       = guest_id,
                guest_name     = extracted.get("guest_name") or "Guest",
                phone          = phone,
                room_type      = extracted.get("room_type", ""),
                checkin        = extracted["checkin_date"],
                checkout       = extracted["checkout_date"],
                nights         = extracted.get("nights"),
                airport_pickup = bool(extracted.get("airport_pickup")),
            )
            if payment_started:
                log.info("[PIPELINE] PayU flow ACTIVE — Djubo booking + confirmation deferred until 50% payment")

        # ── Djubo PMS booking — legacy immediate flow — TEMPORARILY DISABLED ────
        # Disabled alongside the PayU post-payment flow so NO booking writes
        # reach Djubo from any code path (safe to test with prod or QA creds).
        #
        # To re-enable: uncomment the block below and remove the two log lines.
        #
        # reservation = None
        # if not payment_started and booking_id and extracted.get("checkin_date") and extracted.get("checkout_date"):
        #     name_parts = (extracted.get("guest_name") or "Guest").split(maxsplit=1)
        #     reservation = await book_room(
        #         first_name = name_parts[0],
        #         last_name  = name_parts[1] if len(name_parts) > 1 else "",
        #         phone      = phone,
        #         email      = "",
        #         checkin    = extracted["checkin_date"],
        #         checkout   = extracted["checkout_date"],
        #         room_type  = extracted.get("room_type", ""),
        #         special_requests = "Airport pickup requested." if extracted.get("airport_pickup") else "",
        #     )
        #     if reservation:
        #         update_djubo_booking_id(booking_id, reservation.get("reservation_id", ""))
        #         tracker = reservation.get("djubo_guest_tracker_id")
        #         if tracker and guest_id:
        reservation = None
        log.info("[PIPELINE] Djubo PMS booking SKIPPED (disabled) — re-enable in extraction.py")

        # WhatsApp confirmation — skip if phone is unknown (VoBiz didn't pass caller number)
        if payment_started:
            pass  # PayU flow already sent the bill+link message; confirmation comes after payment
        elif booking_id and phone and phone != "unknown":
            log.info(f"[PIPELINE] Sending booking WhatsApp → {phone}")
            guest_name = extracted.get("guest_name", "Guest")
            room_type  = extracted.get("room_type", "")
            checkin    = extracted.get("checkin_date", "")
            checkout   = extracted.get("checkout_date", "")
            nights     = extracted.get("nights")
            # Billing block — only when Djubo returned a real total for this booking
            total = (reservation or {}).get("total_amount") or 0
            if total > 0:
                per_night = round(total / nights) if nights else None
                billing = (
                    f"💰 *Billing Details:*\n"
                    + (f"🏷 Rate: ₹{per_night:,}/night × {nights} nights\n" if per_night else "")
                    + f"💵 Total: ₹{total:,}\n"
                    f"💳 Payment: Pay at hotel — no advance needed\n\n"
                )
                closing = "Feel free to call us anytime!"
            else:
                billing = ""
                closing = ("Our team will reach out to confirm rates shortly. "
                           "Feel free to call us anytime!")
            msg = (
                f"Hi {guest_name}! 🏨 Thank you for choosing Lotus Sutra Goa.\n\n"
                f"Your booking is confirmed:\n"
                f"🛏 Room: {room_type}\n"
                f"📅 Check-in: {checkin}\n"
                f"📅 Check-out: {checkout}\n"
                f"🌙 Nights: {nights if nights else 'TBD'}\n\n"
                f"{billing}"
                f"📍 Arambol, Goa\n\n"
                f"{closing}"
            )
            success = await send_text_message(phone, msg)
            status = "sent" if success else "failed"
            log_whatsapp(booking_id, phone, "booking_confirmation", status)
            if success:
                mark_whatsapp_sent(booking_id)
                log.info(f"[PIPELINE] Booking WhatsApp SENT → {phone}")
            else:
                log.warning("[PIPELINE] Booking WhatsApp FAILED — check Meta token / phone_number_id (see [WA] error above)")
        else:
            log.warning("[PIPELINE] Booking WhatsApp skipped — %s",
                        "booking not saved" if not booking_id else "no phone number")
    else:
        # Explain exactly why the booking (and its WhatsApp) did not trigger
        if not extracted.get("booking_confirmed"):
            reason = "booking_confirmed=false (guest did not explicitly confirm)"
        elif not guest_id:
            reason = "no guest_id (guest name/phone missing)"
        else:
            reason = "no room_type captured"
        log.info(f"[PIPELINE] Booking flow SKIPPED — {reason}")

    # 4. Save event + send WhatsApp event confirmation
    if extracted.get("event") and guest_id:
        log.info("[PIPELINE] Event flow TRIGGERED → saving event + WhatsApp")
        event_id = save_event(
            call_sid   = call_meta.get("call_sid", ""),
            guest_id   = guest_id,
            event_type = extracted.get("event_type"),
            event_date = extracted.get("event_date"),
            num_guests = extracted.get("event_guests"),
        )
        if event_id and phone:
            log.info(f"[PIPELINE] Sending event WhatsApp → {phone}")
            ok = await send_event_confirmation(
                phone      = phone,
                guest_name = extracted.get("guest_name", "Guest"),
                event_type = extracted.get("event_type"),
                event_date = extracted.get("event_date"),
                num_guests = extracted.get("event_guests"),
            )
            # Note: whatsapp_logs.booking_id is FK→bookings, so we don't persist
            # an event row there — app log is the record for event messages.
            log.info("[PIPELINE] Event WhatsApp %s → %s", "SENT" if ok else "FAILED", phone)
        else:
            log.warning("[PIPELINE] Event WhatsApp skipped — %s",
                        "event not saved" if not event_id else "no phone number")
    elif extracted.get("event") and not guest_id:
        log.info("[PIPELINE] Event flow SKIPPED — no guest_id (guest name/phone missing)")

    # 5. Save special requests
    special_requests = extracted.get("special_requests") or []
    if special_requests:
        log.info(f"[PIPELINE] Saving {len(special_requests)} special request(s)")
        for req in special_requests:
            if not isinstance(req, dict):
                continue
            save_request(
                call_sid     = call_meta.get("call_sid", ""),
                guest_id     = guest_id,
                guest_name   = extracted.get("guest_name"),
                request_type = req.get("type", "other"),
                details      = req.get("details"),
                date_needed  = req.get("date_needed"),
            )

    log.info("[PIPELINE] Post-call pipeline complete")
