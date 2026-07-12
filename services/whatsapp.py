import os
import httpx
import logging

log = logging.getLogger("agent")

META_WHATSAPP_TOKEN   = os.getenv("META_WHATSAPP_TOKEN", "")
META_PHONE_NUMBER_ID  = os.getenv("META_PHONE_NUMBER_ID", "")
META_BOOKING_TEMPLATE = os.getenv("META_BOOKING_TEMPLATE", "booking_confirmation")
META_EVENT_TEMPLATE   = os.getenv("META_EVENT_TEMPLATE",  "event_inquiry")
META_TEMPLATE_LANG    = os.getenv("META_TEMPLATE_LANG",   "en")

_BASE_URL = "https://graph.facebook.com/v19.0"


def _clean_phone(phone: str) -> str:
    """Strip + and spaces — WhatsApp API expects digits only."""
    return phone.replace("+", "").replace(" ", "").strip()


def _is_configured() -> bool:
    if not META_WHATSAPP_TOKEN or not META_PHONE_NUMBER_ID:
        log.warning("[WA] META_WHATSAPP_TOKEN or META_PHONE_NUMBER_ID not set — WhatsApp disabled")
        return False
    return True


async def _send_template(to_phone: str, template_name: str, parameters: list[dict]) -> bool:
    """
    Send a WhatsApp template message via Meta Cloud API.

    parameters: list of body parameter dicts, e.g.:
        [{"type": "text", "text": "Mayur"}, {"type": "text", "text": "Junior Suite"}]

    Template must be pre-approved in Meta Business Suite.
    """
    if not _is_configured():
        return False

    url = f"{_BASE_URL}/{META_PHONE_NUMBER_ID}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": _clean_phone(to_phone),
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": META_TEMPLATE_LANG},
            "components": [
                {
                    "type": "body",
                    "parameters": parameters,
                }
            ],
        },
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {META_WHATSAPP_TOKEN}",
                    "Content-Type":  "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            msg_id = data.get("messages", [{}])[0].get("id", "")
            log.info(f"[WA] Sent template '{template_name}' to {to_phone} → msg_id={msg_id}")
            return True
    except httpx.HTTPStatusError as e:
        log.error(f"[WA] HTTP error {e.response.status_code}: {e.response.text}")
        return False
    except Exception as e:
        log.error(f"[WA] Error sending template: {e}")
        return False


async def send_booking_confirmation(phone: str, guest_name: str, room_type: str,
                                    checkin: str, checkout: str, nights: int | None) -> bool:
    """
    Send booking confirmation to guest after call.

    Required Meta template name: booking_confirmation  (or set META_BOOKING_TEMPLATE)
    Expected template body (create this in Meta Business Suite):

        Hi {{1}}! 🏨 Thank you for choosing *The Grand Orchid Hotel*.

        Here's your booking summary:
        🛏 Room: {{2}}
        📅 Check-in: {{3}}
        📅 Check-out: {{4}}
        🌙 Nights: {{5}}

        📍 Location: Koregaon Park, Pune
        https://maps.google.com/?q=The+Grand+Orchid+Hotel+Koregaon+Park+Pune

        Our reservations team will confirm your booking and share rates shortly.
        Feel free to call us anytime!

    Variables: {{1}}=name, {{2}}=room, {{3}}=checkin, {{4}}=checkout, {{5}}=nights
    """
    parameters = [
        {"type": "text", "text": guest_name or "Guest"},
        {"type": "text", "text": room_type or "Room"},
        {"type": "text", "text": checkin   or "TBD"},
        {"type": "text", "text": checkout  or "TBD"},
        {"type": "text", "text": str(nights) if nights else "TBD"},
    ]
    return await _send_template(phone, META_BOOKING_TEMPLATE, parameters)


async def send_event_confirmation(phone: str, guest_name: str, event_type: str | None,
                                  event_date: str | None, num_guests: int | None) -> bool:
    """
    Send event inquiry confirmation to guest after call.

    Required Meta template name: event_inquiry  (or set META_EVENT_TEMPLATE)
    Expected template body (create this in Meta Business Suite):

        Hi {{1}}! 🎉 Thank you for reaching out to *The Grand Orchid Hotel*.

        We've noted your event enquiry:
        🎊 Event: {{2}}
        📅 Date: {{3}}
        👥 Guests: {{4}}

        Our events team will get in touch with you to discuss the arrangements,
        venue details, and catering options.

        Looking forward to making your event special! 🌟

    Variables: {{1}}=name, {{2}}=event_type, {{3}}=event_date, {{4}}=num_guests
    """
    parameters = [
        {"type": "text", "text": guest_name or "Guest"},
        {"type": "text", "text": event_type or "Event"},
        {"type": "text", "text": event_date or "TBD"},
        {"type": "text", "text": str(num_guests) if num_guests else "TBD"},
    ]
    return await _send_template(phone, META_EVENT_TEMPLATE, parameters)
