"""WhatsApp message templates for the PayU payment-first booking flow."""


def payment_request_message(guest_name: str, room_type: str,
                            checkin: str, checkout: str, nights: int,
                            per_night: int, total: int, advance: int,
                            balance: int, payment_link: str) -> str:
    """Message #1 — bill + payment link, sent right after the call ends."""
    return (
        f"Hi {guest_name}! 🏨 Thank you for choosing Lotus Sutra Goa.\n\n"
        f"Your booking details:\n"
        f"🛏 Room: {room_type}\n"
        f"📅 Check-in: {checkin}\n"
        f"📅 Check-out: {checkout}\n"
        f"🌙 Nights: {nights}\n\n"
        f"💰 *Billing Details:*\n"
        f"🏷 Rate: ₹{per_night:,}/night × {nights} nights\n"
        f"💵 Total: ₹{total:,}\n\n"
        f"✅ To *confirm your booking*, please pay 50% advance: *₹{advance:,}*\n\n"
        f"💳 Pay securely here:\n{payment_link}\n\n"
        f"Remaining ₹{balance:,} is payable at the front desk during check-in.\n\n"
        f"📍 Arambol, Goa — feel free to call us anytime!"
    )


def payment_confirmed_message(guest_name: str, room_type: str,
                              checkin: str, checkout: str, nights: int,
                              paid: int, balance: int) -> str:
    """Message #2 — sent immediately after the 50% payment succeeds."""
    return (
        f"✅ *Payment received — your booking is CONFIRMED!*\n\n"
        f"Hi {guest_name}, we've received your advance payment of *₹{paid:,}*.\n\n"
        f"🛏 Room: {room_type}\n"
        f"📅 Check-in: {checkin}\n"
        f"📅 Check-out: {checkout}\n"
        f"🌙 Nights: {nights}\n\n"
        f"💵 Remaining balance: ₹{balance:,} — payable at the front desk during check-in.\n\n"
        f"📍 Lotus Sutra, Arambol, Goa\n"
        f"We look forward to welcoming you! 🌴"
    )
