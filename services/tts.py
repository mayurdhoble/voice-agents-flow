import os
import re
import base64
import audioop
import struct
import httpx

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")

# Persistent client — reuses TCP connections to Sarvam (saves ~100ms per call)
_http = httpx.AsyncClient(timeout=15)

# ── Phrase cache ──────────────────────────────────────────────────────────────
# Pre-generated mulaw audio for short acknowledgment phrases that the LLM
# frequently emits as standalone first sentences. Cache hit = 0ms vs ~800ms TTS.
# Key: lowercased text stripped of punctuation.
_PHRASE_CACHE: dict[str, bytes] = {}

# (phrase, language) pairs to pre-warm at startup.
# Keep to standalone sentences the LLM actually produces.
_WARMUP_PHRASES: list[tuple[str, str]] = [
    # Hindi acknowledgments
    ("बिल्कुल!", "hi"),
    ("ज़रूर!", "hi"),
    ("अच्छा!", "hi"),
    ("ठीक है!", "hi"),
    ("समझ गई!", "hi"),
    ("बहुत अच्छा!", "hi"),
    ("बढ़िया!", "hi"),
    ("परफेक्ट!", "hi"),
    ("बिल्कुल।", "hi"),
    ("नमस्ते!", "hi"),
    ("धन्यवाद!", "hi"),
    # Marathi
    ("बिल्कुल!", "mr"),
    ("ठीक आहे!", "mr"),
    # English acknowledgments
    ("Perfect!", "en"),
    ("Lovely!", "en"),
    ("Great!", "en"),
    ("Wonderful!", "en"),
    ("Sure!", "en"),
    ("Absolutely!", "en"),
    ("Of course!", "en"),
    ("Got it!", "en"),
    ("Happy to help!", "en"),
    ("Thank you!", "en"),
    ("Noted!", "en"),
    ("Certainly!", "en"),
]


def _cache_key(text: str) -> str:
    """Normalize text to a stable cache key."""
    return re.sub(r"[!.,?।\s]+", "", text).lower()


async def prewarm_phrase_cache() -> int:
    """Pre-generate TTS for common acknowledgment phrases. Returns count cached."""
    cached = 0
    for phrase, lang in _WARMUP_PHRASES:
        key = _cache_key(phrase)
        if key in _PHRASE_CACHE:
            continue
        try:
            audio = await _sarvam_tts(phrase, lang)
            _PHRASE_CACHE[key] = audio
            cached += 1
        except Exception:
            pass
    return cached

SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"
DEEPGRAM_TTS_URL = "https://api.deepgram.com/v1/speak"

# Sarvam language codes and best speaker per language
SARVAM_VOICE_MAP = {
    "hi": {"target_language_code": "hi-IN", "speaker": "manisha"},
    "mr": {"target_language_code": "mr-IN", "speaker": "manisha"},
    "en": {"target_language_code": "en-IN", "speaker": "manisha"},
    "ta": {"target_language_code": "ta-IN", "speaker": "manisha"},
    "te": {"target_language_code": "te-IN", "speaker": "manisha"},
    "kn": {"target_language_code": "kn-IN", "speaker": "manisha"},
    "bn": {"target_language_code": "bn-IN", "speaker": "manisha"},
    "gu": {"target_language_code": "gu-IN", "speaker": "manisha"},
}

# Characters that need cleaning before sending to TTS
_CURLY_SINGLE = "‘’"   # left/right single quote
_CURLY_DOUBLE = "“”"   # left/right double quote
_DASHES = "–—"         # en/em dash
_ELLIPSIS = "…"             # horizontal ellipsis

_CLEANUP = [
    (r"[*_~`]", ""),
    ("[" + _CURLY_SINGLE + "]", "'"),
    ("[" + _CURLY_DOUBLE + "]", '"'),
    ("[" + _DASHES + "]", ", "),
    (_ELLIPSIS, "..."),
    (r"&amp;", "and"),
    (r"\s{2,}", " "),
    # Fix LLM name-splitting: "M ayur" -> "Mayur", "A run" -> "Arun"
    (r"\b([A-Z]) ([a-z]{2,})\b", r"\1\2"),
    # Fix LLM streaming artifact: "Iassist" "Ican" "Ididn't" -> "I assist" etc.
    # Require 2+ chars so "Is"/"It"/"In" are NOT split into "I s"/"I t"/"I n".
    (r"\bI([a-z]{2,})", r"I \1"),
    # Fix Hindi+English merge: "खूबसूरतheated" -> "खूबसूरत heated"
    (r"([ऀ-ॿ])([A-Za-z])", r"\1 \2"),
    (r"([A-Za-z])([ऀ-ॿ])", r"\1 \2"),
]


def clean_for_tts(text: str) -> str:
    text = text.encode("utf-8").decode("utf-8")
    for pattern, replacement in _CLEANUP:
        text = re.sub(pattern, replacement, text)
    return text.strip()


def _wav_to_pcm(wav_bytes: bytes) -> bytes:
    """Strip WAV header and return raw PCM16 bytes."""
    idx = wav_bytes.find(b"data")
    if idx == -1:
        return wav_bytes
    return wav_bytes[idx + 8:]


async def text_to_mulaw(text: str, language: str = "en") -> bytes:
    text = clean_for_tts(text)
    # Cache hit: skip HTTP call entirely (~800ms saved for short acknowledgments)
    key = _cache_key(text)
    if key in _PHRASE_CACHE:
        return _PHRASE_CACHE[key]
    if SARVAM_API_KEY:
        return await _sarvam_tts(text, language)
    return await _deepgram_tts(text)


async def _sarvam_tts(text: str, language: str) -> bytes:
    voice = SARVAM_VOICE_MAP.get(language, SARVAM_VOICE_MAP["en"])

    payload = {
        "inputs": [text],
        "target_language_code": voice["target_language_code"],
        "speaker": voice["speaker"],
        "speech_sample_rate": 8000,
        "enable_preprocessing": False,
        "model": "bulbul:v2",
    }

    response = await _http.post(
        SARVAM_TTS_URL,
        headers={
            "api-subscription-key": SARVAM_API_KEY,
            "Content-Type": "application/json",
        },
        json=payload,
    )
    response.raise_for_status()
    data = response.json()

    wav_bytes = base64.b64decode(data["audios"][0])
    pcm_bytes = _wav_to_pcm(wav_bytes)
    return audioop.lin2ulaw(pcm_bytes, 2)


async def _deepgram_tts(text: str) -> bytes:
    params = {
        "model": "aura-luna-en",
        "encoding": "linear16",
        "sample_rate": 8000,
        "container": "none",
    }
    headers = {
        "Authorization": f"Token {DEEPGRAM_API_KEY}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            DEEPGRAM_TTS_URL,
            headers=headers,
            json={"text": text},
            params=params,
        )
        response.raise_for_status()
        return audioop.lin2ulaw(response.content, 2)
