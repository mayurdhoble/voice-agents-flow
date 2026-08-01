"""
PayU India client — payment link creation + webhook verification.

Env vars (add to .env / Railway):
  PAYU_MERCHANT_KEY   merchant key (test or production)
  PAYU_MERCHANT_SALT  merchant salt (test or production)
  PAYU_BASE_URL       default https://test.payu.in — set https://info.payu.in for production
  PAYU_TEST_MODE      default "true" — simulates payment success ~2 min after link is sent
                      (no real webhook needed while testing)

Uses PayU's classic invoice API (create_invoice) which returns a hosted payment
link the guest can open on their phone and pay via UPI / card / netbanking.
"""
import os
import json
import uuid
import hashlib
import logging

import httpx

log = logging.getLogger("agent")

PAYU_KEY  = os.getenv("PAYU_MERCHANT_KEY", "")
PAYU_SALT = os.getenv("PAYU_MERCHANT_SALT", "")
PAYU_BASE = os.getenv("PAYU_BASE_URL", "https://test.payu.in").rstrip("/")
TEST_MODE = os.getenv("PAYU_TEST_MODE", "true").strip().lower() in ("1", "true", "yes")

# Simulated-payment delay in test mode (seconds)
TEST_MODE_CONFIRM_DELAY = int(os.getenv("PAYU_TEST_CONFIRM_DELAY", "120"))


def is_configured() -> bool:
    return bool(PAYU_KEY and PAYU_SALT)


def new_txn_id() -> str:
    """PayU txnid: unique, alphanumeric, max 25 chars."""
    return "LS" + uuid.uuid4().hex[:18]


def _api_hash(command: str, var1: str) -> str:
    """Hash for PayU merchant web-service calls: sha512(key|command|var1|salt)."""
    raw = f"{PAYU_KEY}|{command}|{var1}|{PAYU_SALT}"
    return hashlib.sha512(raw.encode()).hexdigest()


async def create_payment_link(amount: int, txnid: str, guest_name: str,
                              phone: str, description: str) -> str | None:
    """Create a PayU hosted payment link (invoice) for the given amount in INR.
    Returns the payment URL, or None on failure."""
    if not is_configured():
        log.warning("[PAYU] Not configured — PAYU_MERCHANT_KEY / PAYU_MERCHANT_SALT missing")
        return None

    name_parts = (guest_name or "Guest").split(maxsplit=1)
    digits = phone.replace("+", "").replace(" ", "").replace("-", "").strip()
    clean_phone = digits[-10:] if len(digits) > 10 else digits

    var1 = json.dumps({
        "amount":       str(amount),
        "txnid":        txnid,
        "productinfo":  description[:100],
        "firstname":    name_parts[0],
        "lastname":     name_parts[1] if len(name_parts) > 1 else "",
        "phone":        clean_phone,
        "email":        os.getenv("HOTEL_EMAIL", "info@lotussutragoa.com"),
        "address1":     "Lotus Sutra, Arambol, Goa",
        "city":         "Goa",
        "state":        "Goa",
        "country":      "India",
        "zipcode":      "403524",
        "send_email_now": "0",
        "send_sms":       "0",
    })

    payload = {
        "key":     PAYU_KEY,
        "command": "create_invoice",
        "var1":    var1,
        "hash":    _api_hash("create_invoice", var1),
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{PAYU_BASE}/merchant/postservice.php?form=2", data=payload
            )
            if not resp.is_success:
                log.error(f"[PAYU] create_invoice HTTP {resp.status_code}: {resp.text[:300]}")
                return None
            data = resp.json()
            log.info(f"[PAYU] create_invoice response: {data}")
            # Success response carries the hosted payment URL.
            # PayU is inconsistent about casing: {'Status': 'Success', 'URL': ...}
            # on success but {'status': 0, 'msg': ...} on failure.
            lc = {k.lower(): v for k, v in data.items()}
            url = lc.get("url") or ""
            status_val = str(lc.get("status", "")).lower()
            if status_val in ("1", "success") and url:
                log.info(f"[PAYU] Payment link created: txnid={txnid} amount=₹{amount} → {url}")
                return url
            log.error(f"[PAYU] create_invoice failed: {data}")
            return None
    except Exception as e:
        log.error(f"[PAYU] create_invoice error: {e}")
        return None


def verify_webhook_hash(params: dict) -> bool:
    """Verify PayU's reverse hash on the success/failure webhook:
    sha512(salt|status||||||udf5..udf1|email|firstname|productinfo|amount|txnid|key)"""
    posted = (params.get("hash") or "").lower()
    if not posted:
        return False
    seq = "|".join([
        PAYU_SALT,
        params.get("status", ""),
        "", "", "", "", "",                    # empty additional-charge fields
        params.get("udf5", ""), params.get("udf4", ""), params.get("udf3", ""),
        params.get("udf2", ""), params.get("udf1", ""),
        params.get("email", ""), params.get("firstname", ""),
        params.get("productinfo", ""), params.get("amount", ""),
        params.get("txnid", ""), PAYU_KEY,
    ])
    calc = hashlib.sha512(seq.encode()).hexdigest()
    if calc != posted:
        log.warning(f"[PAYU] Webhook hash mismatch for txnid={params.get('txnid', '')}")
    return calc == posted
