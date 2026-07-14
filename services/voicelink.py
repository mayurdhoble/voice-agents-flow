"""
VoiceLink REST API client — outbound calls and call control.
Docs: https://app.voicelink.co.in/documentation/docs.html

⚠️  VERIFY with VoiceLink support: exact endpoint paths and payload keys.
"""
import os
import logging
import httpx

log = logging.getLogger("agent")

VOICELINK_API_KEY    = os.getenv("VOICELINK_API_KEY", "")
VOICELINK_API_URL    = os.getenv("VOICELINK_API_URL", "https://app.voicelink.co.in/api/v1")
VOICELINK_FROM_NUMBER = os.getenv("VOICELINK_FROM_NUMBER", "")
PUBLIC_URL           = os.getenv("PUBLIC_URL", "")


def _ws_url() -> str:
    return PUBLIC_URL.replace("https://", "wss://").replace("http://", "ws://") + "/voicelink-stream"


async def make_call(to_number: str) -> dict | None:
    """
    Initiate an outbound call via VoiceLink REST API.
    ⚠️  Verify payload keys with VoiceLink docs — these are standard field names.
    """
    if not VOICELINK_API_KEY:
        log.error("[VOICELINK] VOICELINK_API_KEY not set")
        return None

    payload = {
        "api_key":      VOICELINK_API_KEY,
        "to":           to_number,
        "from":         VOICELINK_FROM_NUMBER,
        "websocket_url": _ws_url(),
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(f"{VOICELINK_API_URL}/calls/outbound", json=payload)
            resp.raise_for_status()
            data = resp.json()
            log.info(f"[VOICELINK] Call initiated → {data}")
            return data
    except Exception as e:
        log.error(f"[VOICELINK] make_call error: {e}")
        return None


async def end_call(call_id: str) -> bool:
    """Hang up an active call."""
    if not VOICELINK_API_KEY:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{VOICELINK_API_URL}/calls/{call_id}/end",
                json={"api_key": VOICELINK_API_KEY},
            )
            resp.raise_for_status()
            return True
    except Exception as e:
        log.error(f"[VOICELINK] end_call error: {e}")
        return False
