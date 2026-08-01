"""
Payment-first booking orchestration.

Flow:
  1. Call ends with guest consent → start_payment_flow()
       - fetch live Djubo pricing for the room/dates
       - create PayU payment link for 50% advance
       - WhatsApp message #1: bill + payment link
  2. Payment succeeds → handle_payment_success()
       - real:      PayU webhook hits /payu-webhook in main.py
       - test mode: auto-fires ~2 min after message #1 (PAYU_TEST_MODE=true)
       - creates the Djubo booking (deferred until now — booking is only
         confirmed after the 50% payment)
       - WhatsApp message #2: payment received, booking confirmed

Pending payments are held in memory keyed by txnid — fine for testing;
a server restart between link and payment loses the pending record
(the webhook will log "unknown txnid" and skip).
"""
import asyncio
import logging

from services.djubo import get_room_pricing, book_room
from services.whatsapp import send_text_message
from services.database import (
    update_djubo_booking_id, update_guest_djubo_tracker,
    log_whatsapp, mark_whatsapp_sent,
)
from payments.payu_client import (
    create_payment_link, new_txn_id, TEST_MODE, TEST_MODE_CONFIRM_DELAY,
)
from payments.templates import payment_request_message, payment_confirmed_message

log = logging.getLogger("agent")

# txnid → booking context awaiting payment
_PENDING: dict[str, dict] = {}


def _match_per_night(pricing: dict[str, int], room_type: str) -> int | None:
    """Match the extracted room type against Djubo pricing keys (lowercased names).
    Mirrors djubo._match_room: substring → alias keywords → raw words → first room.
    Always returns a rate when pricing is non-empty, same as the legacy booking flow
    (which books a fallback room), so payment and booking stay consistent."""
    from services.djubo import _ROOM_ALIAS_MAP
    want = (room_type or "").strip().lower()

    # 1. Direct substring match (either direction)
    if want:
        if want in pricing:
            return pricing[want]
        for name, price in pricing.items():
            if want in name or name in want:
                return price

        # 2. Alias map + raw words from the request
        keywords = []
        for alias, kws in _ROOM_ALIAS_MAP.items():
            if alias in want:
                keywords.extend(kws)
        keywords.extend(w for w in want.split() if len(w) > 3)
        for name, price in pricing.items():
            if any(kw in name for kw in keywords):
                log.info(f"[PAYU-FLOW] Room alias match: '{room_type}' → '{name}'")
                return price

    # 3. Fallback: first room in pricing — same behavior as legacy Djubo booking
    if pricing:
        name = next(iter(pricing))
        log.warning(f"[PAYU-FLOW] No room match for '{room_type}' — using '{name}' rate")
        return pricing[name]
    return None


async def start_payment_flow(booking_id: str, guest_id: str | None,
                             guest_name: str, phone: str, room_type: str,
                             checkin: str, checkout: str, nights: int | None,
                             airport_pickup: bool = False) -> bool:
    """Send bill + PayU link for 50% advance. Returns True if the payment flow
    is now in charge (caller must NOT run the legacy book-immediately flow)."""
    from datetime import date as _date
    if not nights:
        try:
            nights = max(1, (_date.fromisoformat(checkout) - _date.fromisoformat(checkin)).days)
        except Exception:
            nights = 1

    pricing = await get_room_pricing(checkin, checkout)
    if not pricing:
        log.warning("[PAYU-FLOW] No Djubo pricing available — falling back to legacy flow")
        return False
    per_night = _match_per_night(pricing, room_type)
    if not per_night:
        log.warning(f"[PAYU-FLOW] Room '{room_type}' not matched in pricing {list(pricing)} — legacy flow")
        return False

    total   = per_night * nights
    advance = round(total / 2)
    balance = total - advance

    txnid = new_txn_id()
    link = await create_payment_link(
        amount=advance, txnid=txnid, guest_name=guest_name, phone=phone,
        description=f"Lotus Sutra Goa — 50% advance | {room_type} | {checkin} to {checkout}",
    )
    if not link:
        log.warning("[PAYU-FLOW] Payment link creation failed — falling back to legacy flow")
        return False

    msg = payment_request_message(
        guest_name=guest_name, room_type=room_type,
        checkin=checkin, checkout=checkout, nights=nights,
        per_night=per_night, total=total, advance=advance,
        balance=balance, payment_link=link,
    )
    sent = await send_text_message(phone, msg)
    log_whatsapp(booking_id, phone, "payment_request", "sent" if sent else "failed")
    if not sent:
        log.warning("[PAYU-FLOW] Payment-request WhatsApp failed — falling back to legacy flow")
        return False
    log.info(f"[PAYU-FLOW] Bill + payment link sent → {phone} | txnid={txnid} advance=₹{advance:,}")

    _PENDING[txnid] = {
        "booking_id": booking_id, "guest_id": guest_id,
        "guest_name": guest_name, "phone": phone, "room_type": room_type,
        "checkin": checkin, "checkout": checkout, "nights": nights,
        "advance": advance, "balance": balance,
        "airport_pickup": airport_pickup,
    }

    if TEST_MODE:
        log.info(f"[PAYU-FLOW] TEST MODE — simulating payment success in {TEST_MODE_CONFIRM_DELAY}s")
        asyncio.create_task(_auto_confirm_after_delay(txnid))
    return True


async def _auto_confirm_after_delay(txnid: str):
    await asyncio.sleep(TEST_MODE_CONFIRM_DELAY)
    if txnid in _PENDING:
        log.info(f"[PAYU-FLOW] TEST MODE — auto-confirming payment for txnid={txnid}")
        await handle_payment_success(txnid)


async def handle_payment_success(txnid: str, paid_amount: float | None = None):
    """Payment received → create the Djubo booking + send confirmation WhatsApp."""
    info = _PENDING.pop(txnid, None)
    if not info:
        log.warning(f"[PAYU-FLOW] Payment success for unknown/already-handled txnid={txnid} — ignoring")
        return
    paid = round(paid_amount) if paid_amount else info["advance"]
    log.info(f"[PAYU-FLOW] Payment SUCCESS txnid={txnid} paid=₹{paid:,} → creating Djubo booking")

    # Djubo booking — deferred until payment, this is the real confirmation
    name_parts = (info["guest_name"] or "Guest").split(maxsplit=1)
    reservation = await book_room(
        first_name = name_parts[0],
        last_name  = name_parts[1] if len(name_parts) > 1 else "",
        phone      = info["phone"],
        email      = "",
        checkin    = info["checkin"],
        checkout   = info["checkout"],
        room_type  = info["room_type"],
        special_requests = (
            f"50% advance paid via PayU (txnid {txnid}): ₹{paid:,}. "
            + ("Airport pickup requested." if info.get("airport_pickup") else "")
        ).strip(),
    )
    if reservation:
        update_djubo_booking_id(info["booking_id"], reservation.get("reservation_id", ""))
        tracker = reservation.get("djubo_guest_tracker_id")
        if tracker and info.get("guest_id"):
            update_guest_djubo_tracker(info["guest_id"], tracker)
    else:
        log.error(f"[PAYU-FLOW] Djubo booking FAILED after payment txnid={txnid} — "
                  "guest paid but PMS booking missing, needs manual follow-up")

    msg = payment_confirmed_message(
        guest_name=info["guest_name"], room_type=info["room_type"],
        checkin=info["checkin"], checkout=info["checkout"], nights=info["nights"],
        paid=paid, balance=info["balance"],
    )
    sent = await send_text_message(info["phone"], msg)
    log_whatsapp(info["booking_id"], info["phone"], "payment_confirmed", "sent" if sent else "failed")
    if sent:
        mark_whatsapp_sent(info["booking_id"])
        log.info(f"[PAYU-FLOW] Confirmation WhatsApp SENT → {info['phone']}")


async def handle_payment_failure(txnid: str, reason: str = ""):
    """Payment failed/cancelled — keep pending so the guest can retry the same link."""
    if txnid in _PENDING:
        log.warning(f"[PAYU-FLOW] Payment FAILED txnid={txnid} ({reason}) — link remains payable")
    else:
        log.warning(f"[PAYU-FLOW] Payment failure for unknown txnid={txnid} ({reason})")
