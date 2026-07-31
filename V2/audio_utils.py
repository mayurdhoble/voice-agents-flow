"""
Audio format conversion utilities.

Twilio Media Streams → mulaw 8kHz mono (base64 encoded)
Gemini Live input  → PCM 16-bit 16kHz mono (raw bytes)
Gemini Live output → PCM 16-bit 24kHz mono (raw bytes)
"""

import audioop
import base64


def twilio_to_gemini(payload: str) -> bytes:
    """Convert Twilio base64 mulaw 8kHz → PCM 16-bit 16kHz bytes for Gemini."""
    mulaw_bytes = base64.b64decode(payload)
    # mulaw → linear PCM 16-bit at 8kHz
    pcm_8k = audioop.ulaw2lin(mulaw_bytes, 2)
    # upsample 8kHz → 16kHz
    pcm_16k, _ = audioop.ratecv(pcm_8k, 2, 1, 8000, 16000, None)
    return pcm_16k


def gemini_to_twilio(pcm_bytes: bytes, from_rate: int = 24000) -> str:
    """Convert Gemini PCM output → base64 mulaw 8kHz for Twilio."""
    # downsample to 8kHz
    pcm_8k, _ = audioop.ratecv(pcm_bytes, 2, 1, from_rate, 8000, None)
    # linear PCM → mulaw
    mulaw_bytes = audioop.lin2ulaw(pcm_8k, 2)
    return base64.b64encode(mulaw_bytes).decode("utf-8")
