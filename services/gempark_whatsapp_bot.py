"""WhatsApp bot for Hotel Gem Park, Ooty — information only.

Mirrors the voice agent: Nora answers questions from the hotel knowledge base
and hands every booking, rate, availability or event-quote request to the
reservations team. Nothing is booked over WhatsApp.

When a guest shows booking interest, the conversation is flagged call_back in
gp_whatsapp_sessions so it surfaces on the client and admin panels next to the
voice leads in gp_calls. Reads and writes only gp_* tables.
"""
import os
import json
import asyncio
import logging
from datetime import datetime, timezone

import httpx

log = logging.getLogger("agent")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
WA_BOT_MODEL       = os.getenv("GEMPARK_WA_BOT_MODEL", os.getenv("WA_BOT_MODEL", "google/gemini-2.5-flash"))
_MAX_HISTORY       = 20   # messages sent to the model; the full thread is still stored


def _load_kb() -> str:
    path = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", "gempark_knowledge.txt"))
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


_SYSTEM_PROMPT = """\
You are Nora, the WhatsApp host for Hotel Gem Park, a premium hill-station hotel in Ooty, \
the Nilgiris. You answer guests' questions over WhatsApp text — warm, helpful and concise.

[Style]
Plain text only — no markdown, no asterisks, no bullet symbols. Line breaks are fine.
Keep replies short: 1 to 3 sentences unless the guest asks for detail.
Reply in the language the guest writes in.

[Your role]
Answer questions about the hotel from the knowledge base below. Bookings, room rates, \
availability, offers and event quotes are handled personally by our reservations team.
When the guest wants to book, or asks about rates, availability, offers or an event quote, \
reply warmly that our team member will reach out to them shortly — once per conversation.
Never quote a rate, confirm availability, or say anything is booked or reserved.
Do not ask for booking details; the team collects those when they call.
If something is not in the knowledge base, say our team will be happy to confirm it — never invent.
If the guest wants to speak to someone directly, share the front desk number +91 94899 09855.

[Output — ALWAYS return valid JSON, nothing else]
{
  "reply": "your plain-text WhatsApp reply",
  "call_back": true or false,
  "interest_summary": "one line on what the guest wants, or null"
}
call_back is true when the guest wants to book a stay or an event, or asked about rates, \
availability or offers — i.e. our team should call them.

[Hotel knowledge base]
""" + _load_kb()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_session_blocking(phone: str) -> dict | None:
    from services.database import _get_client
    db = _get_client()
    if not db:
        return None
    r = db.table("gp_whatsapp_sessions").select("*").eq("phone", phone).limit(1).execute()
    return r.data[0] if r.data else None


def _recent_call_blocking(phone: str) -> list | None:
    from services.database import _get_client
    db = _get_client()
    if not db:
        return None
    r = (db.table("gp_calls").select("transcript").eq("phone_number", phone)
           .order("created_at", desc=True).limit(1).execute())
    return r.data[0].get("transcript") if r.data else None


def _save_session_blocking(row: dict) -> None:
    from services.database import _get_client
    db = _get_client()
    if not db:
        return
    db.table("gp_whatsapp_sessions").upsert(row, on_conflict="phone").execute()


async def process_whatsapp_message(phone: str, incoming_text: str) -> str:
    """Answer one incoming WhatsApp message; returns the reply text to send."""
    try:
        session = await asyncio.to_thread(_load_session_blocking, phone) or {}
    except Exception as e:
        log.warning(f"[GP-WA-BOT] Session load failed for {phone}: {e}")
        session = {}
    history = session.get("conversation") or []

    system = _SYSTEM_PROMPT
    try:
        call = await asyncio.to_thread(_recent_call_blocking, phone)
    except Exception:
        call = None
    if call:
        lines = [f"{'Guest' if t.get('role') == 'user' else 'Nora'}: {t.get('content', '').strip()}"
                 for t in call if (t.get("content") or "").strip()]
        if lines:
            system += ("\n\n[This guest phoned the hotel earlier. Use the call as context and "
                       "do not ask again for anything they already said:]\n" + "\n".join(lines))
    if session.get("call_back"):
        system += "\n\n[Our team has already been asked to call this guest back — do not promise it again.]"

    messages = [{"role": "system", "content": system}]
    messages += [{"role": m["role"], "content": m["content"]} for m in history[-_MAX_HISTORY:]]
    messages.append({"role": "user", "content": incoming_text})

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}",
                         "Content-Type": "application/json"},
                json={"model": WA_BOT_MODEL, "messages": messages,
                      "response_format": {"type": "json_object"}, "temperature": 0.3},
            )
            resp.raise_for_status()
            parsed = json.loads(resp.json()["choices"][0]["message"]["content"])
            log.info(f"[GP-WA-BOT] {phone}: {json.dumps(parsed, ensure_ascii=False)[:200]}")
    except Exception as e:
        log.error(f"[GP-WA-BOT] LLM error for {phone}: {e}")
        return ("Sorry, I'm having a little trouble right now. Please call our front desk "
                "on +91 94899 09855 — we'd love to help!")

    reply = (parsed.get("reply") or "").strip() or (
        "Sorry, something went wrong. Please call our front desk on +91 94899 09855.")

    ts = _now_iso()
    history.append({"role": "user",      "content": incoming_text, "ts": ts})
    history.append({"role": "assistant", "content": reply,         "ts": ts})

    row = {"phone": phone, "conversation": history, "last_message_at": ts}
    if parsed.get("call_back") and not session.get("call_back"):
        row.update({"call_back": True, "callback_status": "pending",
                    "interest_summary": parsed.get("interest_summary")})
        log.info(f"[GP-WA-BOT] Lead flagged for callback → {phone}")
    try:
        await asyncio.to_thread(_save_session_blocking, row)
    except Exception as e:
        log.error(f"[GP-WA-BOT] Session save failed for {phone}: {e}")

    return reply
