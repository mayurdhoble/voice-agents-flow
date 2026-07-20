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
  "guest_name":     string or null,
  "checkin_date":   "YYYY-MM-DD" or null,
  "checkout_date":  "YYYY-MM-DD" or null,
  "nights":         integer or null,
  "room_type":      string or null,
  "airport_pickup": true/false/null,
  "extra_bed":      true/false/null,
  "booking_intent": true or false,
  "event":          true or false,
  "event_type":     string or null,
  "event_date":     "YYYY-MM-DD" or null,
  "event_guests":   integer or null,
  "language":       "hi"/"en"/"mr" or "en",
  "call_summary":   "one concise sentence summary of the call"
}

Rules:
- booking_intent = true only if guest provided name + at least one date + room type (all three present)
- event = true if guest asked about birthday party, wedding, conference, or any function/event
- Dates: convert spoken/Hindi dates to YYYY-MM-DD. Assume year 2026 if not stated.
  Examples: "sattarah August" → "2026-08-17", "15th November" → "2026-11-15", "सोलह जून" → "2026-06-16"
- room_type: use exact names if mentioned — Deluxe, Premium Deluxe, Junior Suite, Executive Suite, Presidential Suite
- airport_pickup: true if guest asked about or confirmed airport pickup, false if declined, null if not mentioned
- extra_bed: true if guest asked about or confirmed extra bed, null if not mentioned
- language: dominant language spoken by the guest ("hi" for Hindi, "mr" for Marathi, "en" for English)
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
                                   save_event, mark_whatsapp_sent, log_whatsapp,
                                   update_djubo_booking_id, update_guest_djubo_tracker)
    from services.whatsapp import send_booking_confirmation, send_event_confirmation
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

    # 2. Upsert guest
    guest_id = None
    if extracted.get("guest_name") and phone:
        guest_id = upsert_guest(name=extracted["guest_name"], phone=phone)

    # 3. Save booking + Djubo + WhatsApp confirmation
    if extracted.get("booking_intent") and guest_id and extracted.get("room_type"):
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

        # Djubo — create real booking in PMS
        if booking_id and extracted.get("checkin_date") and extracted.get("checkout_date"):
            name_parts = (extracted.get("guest_name") or "Guest").split(maxsplit=1)
            reservation = await book_room(
                first_name = name_parts[0],
                last_name  = name_parts[1] if len(name_parts) > 1 else "",
                phone      = phone,
                email      = "",
                checkin    = extracted["checkin_date"],
                checkout   = extracted["checkout_date"],
                room_type  = extracted.get("room_type", ""),
                special_requests = "Airport pickup requested." if extracted.get("airport_pickup") else "",
            )
            if reservation:
                update_djubo_booking_id(booking_id, reservation.get("reservation_id", ""))
                tracker = reservation.get("djubo_guest_tracker_id")
                if tracker and guest_id:
                    update_guest_djubo_tracker(guest_id, tracker)

                # Verify the booking was created correctly in Djubo PMS
                res_id = reservation.get("reservation_id", "")
                ref_id = reservation.get("reference_id", "")
                if res_id and ref_id and tracker:
                    from services.djubo import verify_booking
                    verification = await verify_booking(res_id, ref_id, int(tracker))
                    if verification:
                        log.info(f"[DJUBO] Booking verified: status={verification.get('status')}")
                    else:
                        log.warning("[DJUBO] Booking verification returned no data")

        # WhatsApp confirmation
        if booking_id and phone:
            success = await send_booking_confirmation(
                phone      = phone,
                guest_name = extracted.get("guest_name", "Guest"),
                room_type  = extracted.get("room_type", ""),
                checkin    = extracted.get("checkin_date", ""),
                checkout   = extracted.get("checkout_date", ""),
                nights     = extracted.get("nights"),
            )
            status = "sent" if success else "failed"
            log_whatsapp(booking_id, phone, "booking_confirmation", status)
            if success:
                mark_whatsapp_sent(booking_id)

    # 4. Save event + send WhatsApp event confirmation
    if extracted.get("event") and guest_id:
        event_id = save_event(
            call_sid   = call_meta.get("call_sid", ""),
            guest_id   = guest_id,
            event_type = extracted.get("event_type"),
            event_date = extracted.get("event_date"),
            num_guests = extracted.get("event_guests"),
        )
        if event_id and phone:
            await send_event_confirmation(
                phone      = phone,
                guest_name = extracted.get("guest_name", "Guest"),
                event_type = extracted.get("event_type"),
                event_date = extracted.get("event_date"),
                num_guests = extracted.get("event_guests"),
            )

    log.info("[PIPELINE] Post-call pipeline complete")
