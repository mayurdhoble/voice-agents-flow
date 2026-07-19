import os
import uuid
import httpx
import logging

log = logging.getLogger("agent")

DJUBO_TOKEN        = os.getenv("DJUBO_TOKEN", "")
DJUBO_HOTEL_CODE   = os.getenv("DJUBO_HOTEL_CODE", "1")
DJUBO_TA_HOTEL_ID  = int(os.getenv("DJUBO_TA_HOTEL_ID", "0"))
DJUBO_SOURCE_ID    = os.getenv("DJUBO_SOURCE_ID", "100")
DJUBO_SUB_SOURCE   = os.getenv("DJUBO_SUB_SOURCE", "1001")

_BASE = "https://www.secure-booking-engine.com/djubo-direct"


# ─── helpers ──────────────────────────────────────────────────────────────────

def _is_configured() -> bool:
    if not DJUBO_TOKEN:
        log.warning("[DJUBO] DJUBO_TOKEN not set — Djubo disabled")
        return False
    return True


def _headers() -> dict:
    return {
        "Authorization": f"DJUBO-TOKEN {DJUBO_TOKEN}",
        "Content-Type": "application/json",
    }


def _base() -> dict:
    """Common fields required on every request."""
    return {
        "api_version": 9,
        "source_id": DJUBO_SOURCE_ID,
        "sub_source_id": DJUBO_SUB_SOURCE,
        "partner_hotel_code": DJUBO_HOTEL_CODE,
    }


# Djubo actual room names: Standard Queen, Superior Twin, Superior Queen,
#                           Standard Triple, Superior Triple, Standard Twin, misclaneous
_ROOM_ALIAS_MAP = {
    # guest/extraction term  → keywords that appear in Djubo room names
    "premium":        ["superior queen"],
    "pool":           ["superior queen"],
    "pool facing":    ["superior queen"],
    "pool-facing":    ["superior queen"],
    "sea view":       ["superior twin"],
    "seaview":        ["superior twin"],
    "sea-view":       ["superior twin"],
    "cottage":        ["superior twin"],
    "front sea":      ["superior twin"],
    "deluxe":         ["standard queen"],
    "standard":       ["standard queen"],
    "triple":         ["superior triple"],
    "family":         ["superior triple"],
    "twin":           ["superior twin"],
    "queen":          ["superior queen"],
}


def _match_room(available_room_types: dict, requested: str) -> tuple[str, dict] | tuple[None, None]:
    """
    Find best matching room type key from availability response.
    Tries substring match (case-insensitive) between guest request and Djubo room names.
    Uses _ROOM_ALIAS_MAP to translate generic/knowledge-base terms to Djubo keywords.
    Returns (room_type_key, room_type_data) or (None, None).
    """
    req = requested.lower().strip()
    all_names = {k: v.get("name", k) for k, v in available_room_types.items()}
    log.info(f"[DJUBO] Room match — requested='{requested}' | available={list(all_names.values())}")

    # 1. Direct substring match
    for key, data in available_room_types.items():
        if req in data.get("name", "").lower():
            return key, data

    # 2. Alias map: expand generic term to Djubo keywords
    djubo_keywords = []
    for alias, keywords in _ROOM_ALIAS_MAP.items():
        if alias in req:
            djubo_keywords.extend(keywords)
    # Also try raw words from the request
    djubo_keywords.extend(w for w in req.split() if len(w) > 3)

    for key, data in available_room_types.items():
        name = data.get("name", "").lower()
        if any(kw in name for kw in djubo_keywords):
            log.info(f"[DJUBO] Room alias match: '{requested}' → '{data.get('name')}'")
            return key, data

    # 3. Fallback: first available room
    if available_room_types:
        key = next(iter(available_room_types))
        log.warning(f"[DJUBO] No room match for '{requested}' — using '{available_room_types[key].get('name')}'")
        return key, available_room_types[key]
    return None, None


# ─── 1. Guest create / update ──────────────────────────────────────────────────

async def create_or_update_guest(first_name: str, last_name: str = "",
                                  phone: str = "", email: str = "",
                                  tracker_id: int = -1) -> int | None:
    """
    Create a new Djubo guest (tracker_id=-1) or update existing one.
    Returns guest_tracker_id on success, None on failure.
    """
    if not _is_configured():
        return None

    # Clean phone: strip +91 prefix if present
    clean_phone = phone.replace("+91", "").replace("+", "").replace(" ", "").strip()
    # Djubo requires last name — use "." as placeholder for single-name guests
    safe_last  = last_name.strip() if last_name.strip() else "."
    # Djubo requires a valid email — fall back to hotel email
    safe_email = email.strip() if email.strip() else os.getenv("HOTEL_EMAIL", "info@lotussutragoa.com")

    payload = {
        **_base(),
        "guestTrackerId": tracker_id,
        "firstName": first_name,
        "lastName": safe_last,
        "phone": clean_phone,
        "email": safe_email,
        "iso2": "in",
        "isd": "91",
        "title": 1,
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(f"{_BASE}/guest-populate", headers=_headers(), json=payload)
            resp.raise_for_status()
            data = resp.json()
            if "error_code" in data:
                log.error(f"[DJUBO] guest-populate error: {data}")
                return None
            gid = data.get("guest_tracker_id") or data.get("guestTrackerId")
            log.info(f"[DJUBO] Guest {'updated' if tracker_id != -1 else 'created'} → tracker_id={gid} | raw={list(data.keys())}")
            return gid
    except Exception as e:
        log.error(f"[DJUBO] create_or_update_guest: {e}")
        return None


# ─── 2. Availability check ────────────────────────────────────────────────────

async def check_availability(checkin: str, checkout: str,
                              adults: int = 1) -> dict | None:
    """
    Check room availability for given dates.
    Returns raw availability response dict, or None on failure.

    checkin / checkout: "YYYY-MM-DD"
    """
    if not _is_configured():
        return None

    availability_id = str(uuid.uuid4())
    query_key       = uuid.uuid4().hex

    payload = {
        **_base(),
        "start_date": checkin,
        "end_date":   checkout,
        "multiple_category_allowed": True,
        "party": [{"adults": adults}],
        "language": "en_US",
        "query_key": query_key,
        "currency": "INR",
        "user_country": "IN",
        "device_type": "Desktop",
        "availability_id": availability_id,
        "requested_payload": {
            "categories": {
                "room_type_details": True,
                "rate_plan_details": True,
                "room_rate_details": True,
                "hotel_details": True,
            },
            "category_modifiers": {
                "partner_booking_data": True,
                "real_time_pricing": True,
                "multiple_room_rates": True,
                "photos": False,
                "text": True,
            },
        },
        "hotels": [
            {
                "ta_hotel_id": DJUBO_TA_HOTEL_ID,
                "partner_hotel_code": DJUBO_HOTEL_CODE,
            }
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(f"{_BASE}/availability", headers=_headers(), json=payload)
            resp.raise_for_status()
            data = resp.json()
            hotel_data = data.get("hotels", {}).get(DJUBO_HOTEL_CODE, {})
            response_type = hotel_data.get("response_type", "error")
            log.info(f"[DJUBO] Availability check → {response_type}")
            if response_type == "available":
                return hotel_data.get("available", {})
            elif response_type == "unavailable":
                log.warning("[DJUBO] No rooms available for requested dates")
                return None
            else:
                log.error(f"[DJUBO] Availability error: {hotel_data}")
                return None
    except Exception as e:
        log.error(f"[DJUBO] check_availability: {e}")
        return None


# ─── 3. Booking submit (pay at hotel) ─────────────────────────────────────────

async def submit_booking(checkin: str, checkout: str,
                          first_name: str, last_name: str,
                          phone: str, email: str,
                          room_type_requested: str,
                          availability_data: dict,
                          special_requests: str = "") -> dict | None:
    """
    Submit a booking using data from check_availability().
    Uses 'pay at hotel' (no card required).
    Returns reservation dict on success, None on failure.

    availability_data: the 'available' block from check_availability()
    """
    if not _is_configured():
        return None

    room_types  = availability_data.get("room_types", {})
    room_rates  = availability_data.get("room_rates", {})

    # Match requested room type to what's available
    room_key, room_data = _match_room(room_types, room_type_requested)
    if not room_key:
        log.error("[DJUBO] No matching room type found in availability")
        return None

    # Find a rate for this room type
    matched_rate = None
    for rate_key, rate in room_rates.items():
        if str(rate.get("room_type_key")) == str(room_key):
            matched_rate = rate
            break

    if not matched_rate:
        log.error(f"[DJUBO] No rate found for room_key={room_key}")
        return None

    partner_data_val = matched_rate.get("partner_data", "")
    # Djubo expects partner_data as a string token, not a boolean
    if not isinstance(partner_data_val, str):
        partner_data_val = str(partner_data_val)
    log.info(f"[DJUBO] partner_data for room_key={room_key}: {repr(partner_data_val)}")

    # Total price from line items (pay at checkout → final_price_at_booking=0)
    total_checkout = 0
    for item in matched_rate.get("line_items", []):
        price_info = item.get("price", {}).get("currency_of_charge_price", {})
        total_checkout += price_info.get("amount", 0)

    reference_id = uuid.uuid4().hex
    clean_phone  = phone.replace("+91", "").replace("+", "").replace(" ", "").strip()
    safe_last    = last_name.strip() if last_name.strip() else "."
    safe_email   = email.strip() if email.strip() else os.getenv("HOTEL_EMAIL", "info@lotussutragoa.com")

    payload = {
        **_base(),
        "start_date": checkin,
        "end_date":   checkout,
        "reference_id": reference_id,
        "multiple_category_allowed": True,
        "ip_address": "127.0.0.1",
        "customer": {
            "first_name":    first_name,
            "last_name":     safe_last,
            "phone_number":  clean_phone,
            "email":         safe_email,
            "country":       "IN",
        },
        "rooms": [
            {
                "party": [{"adults": 1}],
                "traveler_first_name": first_name,
                "traveler_last_name":  safe_last,
            }
        ],
        "special_requests": special_requests,
        "final_price_at_booking":  {"amount": 0,              "currency": "INR"},
        "final_price_at_checkout": {"amount": total_checkout,  "currency": "INR"},
        "partner_data": {str(room_key): partner_data_val},
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(f"{_BASE}/booking_submit/", headers=_headers(), json=payload)
            if not resp.is_success:
                log.error(f"[DJUBO] submit_booking HTTP {resp.status_code}: {resp.text[:500]}")
                return None
            data = resp.json()
            status = data.get("status", "Failure")
            if status == "Success":
                reservation = data.get("reservation", {})
                log.info(f"[DJUBO] Booking submitted → {reservation.get('reservation_id')} | status={reservation.get('status')}")
                return reservation
            else:
                log.error(f"[DJUBO] Booking submit failed: {data}")
                return None
    except Exception as e:
        log.error(f"[DJUBO] submit_booking: {e}")
        return None


# ─── 4. Book room — full convenience wrapper ──────────────────────────────────

async def book_room(first_name: str, last_name: str, phone: str,
                    email: str, checkin: str, checkout: str,
                    room_type: str, special_requests: str = "") -> dict | None:
    """
    End-to-end booking: guest create → availability → submit.
    Returns reservation dict with reservation_id, or None on failure.
    """
    # Step 1: Create/update guest
    tracker_id = await create_or_update_guest(
        first_name=first_name, last_name=last_name,
        phone=phone, email=email,
    )

    # Step 2: Check availability
    availability = await check_availability(checkin=checkin, checkout=checkout)
    if not availability:
        return None

    # Step 3: Submit booking
    reservation = await submit_booking(
        checkin=checkin, checkout=checkout,
        first_name=first_name, last_name=last_name,
        phone=phone, email=email,
        room_type_requested=room_type,
        availability_data=availability,
        special_requests=special_requests,
    )

    if reservation and tracker_id:
        reservation["djubo_guest_tracker_id"] = tracker_id

    return reservation


# ─── 4b. Available room names (for LLM context injection) ────────────────────

async def get_available_room_names(checkin: str, checkout: str,
                                    adults: int = 1) -> list[str] | None:
    """
    Returns list of available room type names for given dates, e.g.:
    ["Front Sea View Cottage", "Premium Pool Facing", "Deluxe Garden View Cottage"]
    Returns None on API failure, empty list if no rooms available.
    checkin / checkout: "YYYY-MM-DD"
    """
    availability = await check_availability(checkin, checkout, adults)
    if availability is None:
        return None
    room_types = availability.get("room_types", {})
    names = [v.get("name", k) for k, v in room_types.items() if v.get("available", True)]
    log.info(f"[DJUBO] Available rooms for {checkin}→{checkout}: {names}")
    return names


# ─── 5. Verify booking ────────────────────────────────────────────────────────

async def verify_booking(reservation_id: str, reference_id: str,
                          guest_tracker_id: int) -> dict | None:
    """Fetch full booking details by reservation_id."""
    if not _is_configured():
        return None
    params = {
        "partner_hotel_code": DJUBO_HOTEL_CODE,
        "reservation_id":     reservation_id,
        "reference_id":       reference_id,
        "guest_tracker_id":   guest_tracker_id,
        "api_version":        9,
        "source_id":          DJUBO_SOURCE_ID,
        "sub_source_id":      DJUBO_SUB_SOURCE,
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{_BASE}/booking_verify/",
                                    headers=_headers(), params=params)
            resp.raise_for_status()
            data = resp.json()
            log.info(f"[DJUBO] Booking verified → {data.get('status')}")
            return data
    except Exception as e:
        log.error(f"[DJUBO] verify_booking: {e}")
        return None
