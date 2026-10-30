"""Post-call pipeline for Hotel Gem Park, Ooty.

After every call:
  1. A reviewer agent reads the whole conversation and decides whether the
     reservations team should call the guest back.
  2. The call — transcript, recording, verdict and costs — is saved to gp_calls,
     which the client and admin panels read.
  3. The caller gets a short WhatsApp thanking them, with the hotel's details.

Nothing here touches the Lotus Sutra tables (calls, guests, bookings,
usage_logs), so the two hotels' data never mix.
"""
import os
import json
import time
import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx

log = logging.getLogger("agent")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
REVIEW_MODEL       = os.getenv("GEMPARK_REVIEW_MODEL", os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini"))
WA_TEMPLATE        = os.getenv("GEMPARK_WA_TEMPLATE", "gempark_call_thanks")
SEND_WHATSAPP      = os.getenv("GEMPARK_SEND_WHATSAPP", "true").lower() == "true"

_IST = timezone(timedelta(hours=5, minutes=30))

# VoBiz redials /vobiz-answer-gemini after a hangup and on stream drops, so one
# guest can produce several sessions in a minute. Thank them once, not per session.
_WA_DEDUPE_S = 30 * 60
_wa_last_sent: dict[str, float] = {}

_REVIEW_PROMPT = """\
You review phone calls between Nora, the AI host at Hotel Gem Park in Ooty, and a caller. \
Nora only answers questions; she never takes bookings. A person from the reservations team \
calls back the callers worth calling.

Decide whether the reservations team should call this caller back, and summarise the call for them.

Return ONLY valid JSON with exactly these fields:
{
  "call_back":         true or false,
  "lead_temperature":  "hot" | "warm" | "cold",
  "intent":            "room_booking" | "event" | "dining" | "information" | "other",
  "callback_promised": true or false,
  "guest_name":        string or null,
  "dates_mentioned":   string or null,
  "guests":            integer or null,
  "room_interest":     string or null,
  "interest_summary":  "one line: what the caller wants",
  "call_summary":      "one or two sentences summarising the call",
  "reason":            "one line: why the team should or should not call back",
  "language":          "ta" | "en" | "hi" | "kn" | "ml" | "te" | "other"
}

Rules:
- hot: the caller clearly wants to book a stay or an event, or asked about rates, availability or offers
- warm: genuinely interested — asking detailed questions about rooms, suites, dining or events — but no clear plan yet
- cold: general enquiry, directions, wrong number, job seeker, vendor, silence, or they only wanted a phone number
- call_back is true for hot and warm, false for cold
- callback_promised is true if Nora told the caller that our team will reach out, call back or contact them
- Use null for anything not mentioned. Never invent details.
- Return ONLY the JSON object — no markdown, no explanation.
"""


def _transcript(history: list[dict]) -> str:
    return "\n".join(
        f"{'Guest' if m['role'] == 'user' else 'Nora'}: {m['content']}" for m in history
    )


def _nora_promised_callback(history: list[dict]) -> bool:
    """Deterministic check, independent of the reviewer: did Nora tell the guest
    the team would reach out? If she did, that promise has to be kept."""
    phrases = ("reach out", "call you back", "get in touch", "contact you",
               "when they call", "will call you")
    return any(
        m["role"] == "assistant" and any(p in m["content"].lower() for p in phrases)
        for m in history
    )


async def review_call(history: list[dict]) -> dict:
    """Second agent: verdict on whether to call this guest back."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type":  "application/json",
                },
                json={
                    "model": REVIEW_MODEL,
                    "messages": [
                        {"role": "system", "content": _REVIEW_PROMPT},
                        {"role": "user",   "content": f"Review this call:\n\n{_transcript(history)}"},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0,
                },
            )
            resp.raise_for_status()
            verdict = json.loads(resp.json()["choices"][0]["message"]["content"])
            log.info(f"[GP-REVIEW] {json.dumps(verdict, ensure_ascii=False)}")
            return verdict
    except Exception as e:
        log.error(f"[GP-REVIEW] Failed: {e}")
        return {}


def _save_call_blocking(row: dict) -> None:
    from services.database import _get_client
    db = _get_client()
    if not db:
        log.warning("[GP-DB] Supabase not configured — call not saved")
        return
    db.table("gp_calls").insert(row).execute()
    log.info(f"[GP-DB] Call saved → {row.get('call_sid')} | call_back={row.get('call_back')}")


async def _send_thanks(phone: str, call_date: str) -> bool:
    from services.whatsapp import _send_template
    return await _send_template(phone, WA_TEMPLATE, [{"type": "text", "text": call_date}])


async def run_gempark_pipeline(history: list[dict], call_meta: dict) -> None:
    """Review → save → WhatsApp. Runs detached after the call has ended."""
    phone = (call_meta.get("phone_number") or "").strip()

    # A session where the guest never spoke is a VoBiz redial or a dead line —
    # nothing to review, and nobody to thank.
    if not any(m["role"] == "user" for m in history):
        log.info(f"[GP-PIPELINE] Skipped — guest never spoke (phone={phone or 'unknown'})")
        return

    log.info("[GP-PIPELINE] Post-call review started")
    verdict = await review_call(history)

    promised = bool(verdict.get("callback_promised")) or _nora_promised_callback(history)
    if verdict:
        call_back = bool(verdict.get("call_back")) or promised
        reason    = verdict.get("reason")
        if promised and not verdict.get("call_back"):
            reason = "Nora promised the guest a callback. " + (reason or "")
    else:
        # Review failed — flag for a human rather than silently dropping a lead.
        call_back = True
        reason    = "Automatic review failed — please listen to the recording."

    whatsapp_sent = False
    valid_phone = sum(c.isdigit() for c in phone) >= 10
    if SEND_WHATSAPP and valid_phone:
        last = _wa_last_sent.get(phone, 0.0)
        if time.time() - last < _WA_DEDUPE_S:
            log.info(f"[GP-WA] Skipped — already thanked {phone} recently")
        else:
            call_date = datetime.now(_IST).strftime("%d %B %Y").lstrip("0")
            whatsapp_sent = await _send_thanks(phone, call_date)
            if whatsapp_sent:
                _wa_last_sent[phone] = time.time()
    elif not valid_phone:
        log.warning(f"[GP-WA] Skipped — no usable caller number ({phone or 'unknown'})")

    row = {
        "call_sid":          call_meta.get("call_sid"),
        "phone_number":      phone or None,
        "started_at":        call_meta.get("started_at"),
        "ended_at":          call_meta.get("ended_at"),
        "duration_seconds":  call_meta.get("duration_seconds"),
        "recording_url":     call_meta.get("recording_url"),
        "transcript":        history,
        "call_back":         call_back,
        "lead_temperature":  verdict.get("lead_temperature") or "unknown",
        "intent":            verdict.get("intent"),
        "callback_promised": promised,
        "guest_name":        verdict.get("guest_name"),
        "dates_mentioned":   verdict.get("dates_mentioned"),
        "guests":            verdict.get("guests"),
        "room_interest":     verdict.get("room_interest"),
        "interest_summary":  verdict.get("interest_summary"),
        "call_summary":      verdict.get("call_summary"),
        "reason":            reason,
        "language":          verdict.get("language"),
        "callback_status":   "pending" if call_back else "not_needed",
        "whatsapp_sent":     whatsapp_sent,
        "gemini_cost_usd":   call_meta.get("gemini_cost_usd"),
        "vobiz_cost_usd":    call_meta.get("vobiz_cost_usd"),
    }
    try:
        await asyncio.to_thread(_save_call_blocking, row)
    except Exception as e:
        log.error(f"[GP-DB] Save failed: {e}")

    log.info(
        f"[GP-PIPELINE] Done — call_back={call_back} "
        f"({row['lead_temperature']}) whatsapp_sent={whatsapp_sent}"
    )
