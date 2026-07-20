import os
import sys
import json
import base64
import asyncio
import logging
import time
import audioop
import re
import calendar
from datetime import datetime, date, timezone, timedelta
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from services.stt_livekit import SileroVADSTT, SileroVADOnly
from services.llm import generate_response_stream, needs_rag, start_rag_task
from services.tts import text_to_mulaw, clean_for_tts, prewarm_phrase_cache
from services.extraction import run_post_call_pipeline
from services.database import get_guest_by_phone
from services.djubo import get_available_room_names, get_room_pricing
from services.gemini_live import GeminiLiveSession

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    handlers=[
        logging.StreamHandler(open(sys.stdout.fileno(), mode='w', encoding='utf-8', errors='replace', closefd=False)),
        logging.FileHandler("debug.log", encoding="utf-8"),
    ]
)
log = logging.getLogger("agent")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from api.routes import router as api_router
app.include_router(api_router)

PUBLIC_URL = os.getenv("PUBLIC_URL", "")
TELEPHONY  = os.getenv("TELEPHONY", "voicelink")


# Hindi number words → integer (for date parsing)
_HI_NUMS: dict[str, int] = {
    "एक":1,"दो":2,"तीन":3,"चार":4,"पाँच":5,"पांच":5,
    "छह":6,"छः":6,"सात":7,"आठ":8,"नौ":9,"दस":10,
    "ग्यारह":11,"बारह":12,"तेरह":13,"चौदह":14,"पंद्रह":15,
    "सोलह":16,"सत्रह":17,"अठारह":18,"उन्नीस":19,"बीस":20,
    "इक्कीस":21,"बाईस":22,"तेईस":23,"चौबीस":24,"पच्चीस":25,
    "छब्बीस":26,"सत्ताईस":27,"अट्ठाईस":28,"उनतीस":29,"तीस":30,"इकतीस":31,
}

# Hindi month names for date extraction
_HI_MONTHS_MAP: dict[str, str] = {
    "जनवरी":"January","फरवरी":"February","मार्च":"March","अप्रैल":"April",
    "मई":"May","जून":"June","जुलाई":"July","अगस्त":"August",
    "सितंबर":"September","अक्टूबर":"October","नवंबर":"November","दिसंबर":"December",
}
_HI_MONTHS = "|".join(_HI_MONTHS_MAP.keys())
# Captures "पंद्रह अगस्त", "बीस जुलाई", "दो अगस्त" etc. — \S+ avoids [ऀ-ॿ] range issues
_HI_DATE = r"(\S+\s+(?:" + _HI_MONTHS + r"))"


def _parse_date_to_iso(date_str: str) -> str | None:
    """Convert human-readable date (English or Hindi) to YYYY-MM-DD.
    Translates Hindi number words first since dateparser can't handle them."""
    import dateparser as _dp
    raw = date_str.strip().rstrip("।., ")
    # Try Hindi word → English date (e.g. "पंद्रह अगस्त" → "15 August")
    parts = raw.split()
    if len(parts) >= 2:
        day_word = parts[0]
        month_word = parts[-1]
        day = _HI_NUMS.get(day_word)
        month = _HI_MONTHS_MAP.get(month_word)
        if day and month:
            en_str = f"{day} {month}"
            try:
                p = _dp.parse(en_str, settings={"PREFER_DATES_FROM": "future", "DATE_ORDER": "DMY"})
                if p:
                    return p.strftime("%Y-%m-%d")
            except Exception:
                pass
    # Fallback: let dateparser try directly (works for English dates)
    try:
        p = _dp.parse(raw, languages=["hi", "en"], settings={"PREFER_DATES_FROM": "future", "DATE_ORDER": "DMY"})
        if p:
            return p.strftime("%Y-%m-%d")
    except Exception:
        pass
    return None

# English date capture — stops at punctuation/conjunctions
_EN_DATE = r"((?:[A-Za-z0-9]+[,\s\-/]*){1,6}?)(?=\s*(?:and|to|till|through|\.|\,|\?|$))"

_CHECKIN_PATS = [
    # Hindi patterns (match LLM replies like "चेक-इन पंद्रह अगस्त।")
    r"चेक-इन\s+" + _HI_DATE,
    r"चेक.इन\s+(?:की\s+तारीख\s+)?(?:है\s+|होगा\s+)?" + _HI_DATE,
    # English patterns
    r"check[- ]?in\s*(?:date\s*)?(?:is|:|-|on|will be|would be)\s*(?:on\s+)?(?:the\s+)?" + _EN_DATE,
    r"arriving\s+(?:on\s+)?(?:the\s+)?" + _EN_DATE,
]
_CHECKOUT_PATS = [
    # Hindi patterns
    r"चेक-आउट\s+" + _HI_DATE,
    r"चेक.आउट\s+(?:की\s+तारीख\s+)?(?:है\s+|होगा\s+)?" + _HI_DATE,
    # English patterns
    r"check[- ]?out\s*(?:date\s*)?(?:is|:|-|on|will be|would be)\s*(?:on\s+)?(?:the\s+)?" + _EN_DATE,
    r"checking\s+out\s+(?:on\s+)?(?:the\s+)?" + _EN_DATE,
]


def _extract_iso_dates(history: list[dict]) -> tuple[str | None, str | None]:
    """Extract confirmed check-in and check-out as ISO dates from conversation history.
    Scans assistant messages for both English and Hindi date confirmations."""
    import re
    checkin_raw = checkout_raw = None

    def _first_match(text, patterns):
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                raw = m.group(1).strip().rstrip("।., ")
                if len(raw) >= 3:
                    return raw
        return None

    for msg in reversed(history):
        if msg["role"] != "assistant":
            continue
        t = msg["content"]
        if not checkin_raw:
            checkin_raw = _first_match(t, _CHECKIN_PATS)
        if not checkout_raw:
            checkout_raw = _first_match(t, _CHECKOUT_PATS)
        if checkin_raw and checkout_raw:
            break

    checkin  = _parse_date_to_iso(checkin_raw)  if checkin_raw  else None
    checkout = _parse_date_to_iso(checkout_raw) if checkout_raw else None
    return checkin, checkout

GREETING = "Thank you for calling Lotus Sutra, Goa. This is Maya — how may I assist you today?"

# Month detection for far-future availability refresh
_MONTH_PATTERN = re.compile(
    r'\b(january|february|march|april|may|june|july|august|september|october|november|december|'
    r'jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)\b',
    re.IGNORECASE,
)
_MONTH_NUMS: dict[str, int] = {
    "january":1,"jan":1,"february":2,"feb":2,"march":3,"mar":3,
    "april":4,"apr":4,"may":5,"june":6,"jun":6,"july":7,"jul":7,
    "august":8,"aug":8,"september":9,"sep":9,"october":10,"oct":10,
    "november":11,"nov":11,"december":12,"dec":12,
}

# Pre-cached greeting audio (generated at startup to eliminate first-call TTS latency)
_GREETING_AUDIO_EN: bytes | None = None
_GEMINI_GREETING_AUDIO: bytes | None = None   # Kore voice — consistent with rest of call


async def _generate_gemini_greeting() -> bytes | None:
    """Connect a temporary Gemini Live session, speak the greeting, cache the audio."""
    try:
        from google import genai as _genai
        from google.genai import types as _gt
        import audioop as _ao

        _client = _genai.Client(
            api_key=os.getenv("GOOGLE_API_KEY"),
            http_options={"api_version": "v1alpha"},
        )
        _voice = os.getenv("GEMINI_LIVE_VOICE", "Kore")
        _model = os.getenv("GEMINI_LIVE_MODEL", "gemini-2.0-flash-live-001")

        _config = _gt.LiveConnectConfig(
            generation_config=_gt.GenerationConfig(response_modalities=["AUDIO"]),
            speech_config=_gt.SpeechConfig(
                voice_config=_gt.VoiceConfig(
                    prebuilt_voice_config=_gt.PrebuiltVoiceConfig(voice_name=_voice)
                )
            ),
        )

        pcm_chunks: list[bytes] = []

        async with _client.aio.live.connect(model=_model, config=_config) as session:
            await session.send_client_content(
                turns=_gt.Content(
                    role="user",
                    parts=[_gt.Part(text=(
                        f"Say exactly this greeting and nothing else: \"{GREETING}\""
                    ))],
                ),
                turn_complete=True,
            )
            async for msg in session.receive():
                sc = msg.server_content
                if not sc:
                    continue
                if sc.model_turn:
                    for part in sc.model_turn.parts:
                        if part.inline_data and part.inline_data.data:
                            pcm_chunks.append(part.inline_data.data)
                if sc.turn_complete:
                    break

        if not pcm_chunks:
            return None

        # Convert PCM 24kHz → mulaw 8kHz (same as live call audio path)
        combined = b"".join(pcm_chunks)
        pcm_8k, _ = _ao.ratecv(combined, 2, 1, 24000, 8000, None)
        mulaw = _ao.lin2ulaw(pcm_8k, 2)
        return mulaw

    except Exception as e:
        log.warning(f"[PREWARM] Gemini greeting generation failed: {e}")
        return None


@app.on_event("startup")
async def _prewarm():
    global _GREETING_AUDIO_EN, _GEMINI_GREETING_AUDIO

    # Generate Gemini Kore greeting (preferred — consistent voice throughout call)
    _GEMINI_GREETING_AUDIO = await _generate_gemini_greeting()
    if _GEMINI_GREETING_AUDIO:
        log.info(f"[PREWARM] Gemini greeting cached: {len(_GEMINI_GREETING_AUDIO)}b (Kore voice)")
    else:
        log.warning("[PREWARM] Gemini greeting failed — will fall back to Sarvam")

    # Sarvam greeting as fallback
    try:
        _GREETING_AUDIO_EN = await text_to_mulaw(GREETING, "en")
        log.info(f"[PREWARM] Sarvam greeting cached: {len(_GREETING_AUDIO_EN)}b (fallback)")
    except Exception as e:
        log.warning(f"[PREWARM] Sarvam greeting cache failed: {e}")

    try:
        n = await prewarm_phrase_cache()
        log.info(f"[PREWARM] Phrase cache: {n} phrases ready")
    except Exception as e:
        log.warning(f"[PREWARM] Phrase cache failed: {e}")

# ─── Farewell / noise sets (shared by both handlers) ─────────────────────────

_FAREWELL_WORDS = {
    "bye", "goodbye", "cut the call", "end the call", "end it",
    "wrap up", "that's all", "thats all", "i want to end", "want to end",
    "disconnect", "call cut", "band karo", "rakh do", "rakho",
    "समाप्त करा", "कॉल कट", "बंद करा", "कट करता", "कट करते",
    "कॉल काटता", "कॉल काटते", "बंद कर", "रखो", "रख दो",
    "बस हो गया", "धन्यवाद बस", "बस इतना काफी", "नाही लागत",
    "बस एवढं", "ठीक आहे बस", "end करते", "end karte", "call end",
    "बस थैंक यू", "bas thank", "बस खत्म", "यहीं तक", "इतना काफी",
}

_FAREWELL_IN_REPLY = {
    "thank you for calling", "we look forward to welcoming",
    "have a great day", "goodbye", "धन्यवाद for calling",
    "में कॉल करने के लिए धन्यवाद", "स्वागत करने के लिए तैयार",
    "arambol में आपका स्वागत",
}

_NOISE = {
    "uh", "um", "hmm", "hm", "ah", "oh", "uh-huh", "mhm", "so", "pan", "mudko",
    "ya", "ya edit", "या एडिट", "na", "na sar",
    "hello", "hi", "hey", "namaste", "नमस्ते", "नमस्कार", "নমস্কার", "vanakkam", "haan",
    # Hindi greetings / filler that STT picks up as standalone tokens
    "हेलो", "हैलो", "हाँ", "हां", "ओके", "ओह", "अच्छा", "ठीक",
    # Short Tamil/Telugu noise from garbled STT
    "மு", "எஸ்", "ஆம்",
}

_EXPLICIT_LANG_REQUESTS = {
    "en": ["speak in english", "speak english", "english only", "talk in english",
           "reply in english", "can you speak english", "switch to english",
           "in english please", "english mein bolo", "english me bolo"],
    "hi": ["hindi mein bolo", "hindi me bolo", "speak in hindi", "talk in hindi",
           "hindi boliye", "hindi bol", "switch to hindi"],
    "mr": ["marathi madhe bola", "marathi mein bolo", "speak in marathi",
           "talk in marathi", "marathi bolte", "marathi me bolo"],
}

_SILENCE_REPROMPTS = {
    "en": ("Are you still there?", "No problem — feel free to call us back anytime. Goodbye!"),
    "hi": ("क्या आप अभी भी लाइन पर हैं?", "ठीक है, जब चाहें कॉल करें। धन्यवाद!"),
    "mr": ("तुम्ही अजून लाइनवर आहात का?", "ठीक आहे, जेव्हा हवं तेव्हा कॉल करा. धन्यवाद!"),
    "te": ("మీరు ఇంకా లైన్‌లో ఉన్నారా?", "సరే, ఎప్పుడైనా కాల్ చేయండి. ధన్యవాదాలు!"),
    "ta": ("நீங்கள் இன்னும் இணைந்திருக்கிறீர்களா?", "சரி, எப்போது வேண்டுமானாலும் அழைக்கலாம். நன்றி!"),
}


def _mulaw_to_alaw(mulaw_bytes: bytes) -> bytes:
    """Convert mulaw (our TTS output) → ALAW (VoiceLink expects)."""
    pcm = audioop.ulaw2lin(mulaw_bytes, 2)
    return audioop.lin2alaw(pcm, 2)


def _alaw_to_mulaw(alaw_bytes: bytes) -> bytes:
    """Convert ALAW (VoiceLink sends) → mulaw (our VAD/STT expects)."""
    pcm = audioop.alaw2lin(alaw_bytes, 2)
    return audioop.lin2ulaw(pcm, 2)


def _is_farewell(text: str) -> bool:
    return any(w in text.strip().lower() for w in _FAREWELL_WORDS)


def _detect_explicit_lang(text: str):
    t = text.lower().strip()
    for lang, phrases in _EXPLICIT_LANG_REQUESTS.items():
        for phrase in phrases:
            if phrase in t:
                return lang
    return None


def _pick_tts_lang(sentence: str, stt_lang: str, speak_lang: str) -> str:
    alpha = sum(1 for c in sentence if c.isalpha())
    if alpha == 0:
        return speak_lang
    dev = sum(1 for c in sentence if 'ऀ' <= c <= 'ॿ')
    asc = sum(1 for c in sentence if c.isascii() and c.isalpha())
    if dev / alpha > 0.5:
        return stt_lang if stt_lang in ("hi", "mr") else "hi"
    if asc / alpha > 0.7:
        return "en"
    return speak_lang


# ─── 1. Twilio webhook ────────────────────────────────────────────────────────

@app.api_route("/incoming-call", methods=["GET", "POST"])
async def incoming_call(request: Request):
    log.info("[TWILIO] /incoming-call hit")
    form = await request.form()
    caller_phone = form.get("From") or form.get("To") or "unknown"
    call_sid     = form.get("CallSid", "")
    direction    = "inbound" if form.get("Direction", "inbound") == "inbound" else "outbound"
    ws_url = PUBLIC_URL.replace("https://", "wss://").replace("http://", "ws://")
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{ws_url}/media-stream">
            <Parameter name="caller_phone" value="{caller_phone}"/>
            <Parameter name="call_sid"     value="{call_sid}"/>
            <Parameter name="direction"    value="{direction}"/>
        </Stream>
    </Connect>
</Response>"""
    log.info(f"[TWILIO] TwiML → {ws_url}/media-stream | caller={caller_phone}")
    return Response(content=twiml, media_type="application/xml")


# ─── 2. VoiceLink webhook ─────────────────────────────────────────────────────
# VoiceLink POSTs JSON when a call arrives. We respond with our WebSocket URL.
# ⚠️  Verify exact request/response field names with VoiceLink support.

@app.api_route("/voicelink-webhook", methods=["GET", "POST"])
async def voicelink_webhook(request: Request):
    log.info("[VOICELINK] /voicelink-webhook hit")
    try:
        body = await request.json()
    except Exception:
        body = {}
    caller_phone = body.get("from") or body.get("caller") or "unknown"
    call_id      = body.get("call_id") or body.get("session_id") or ""
    direction    = body.get("direction", "inbound")
    ws_url = PUBLIC_URL.replace("https://", "wss://").replace("http://", "ws://")
    log.info(f"[VOICELINK] Call from {caller_phone} | id={call_id}")
    # ⚠️  VoiceLink may expect a different response structure — verify with their docs
    return {"websocket_url": f"{ws_url}/voicelink-stream", "call_id": call_id}


# ─── 3. Twilio WebSocket (/media-stream) ─────────────────────────────────────

@app.websocket("/media-stream")
async def media_stream(websocket: WebSocket):
    await websocket.accept()
    log.info("[TWILIO-WS] Connected")

    stream_sid       = None
    conversation_history = []
    transcript_queue = asyncio.Queue()
    session_language = "en"
    farewell_sent    = False
    aria_speaking    = False
    _silence_task    = None
    _call_active     = True
    _english_turn_count     = 0
    _non_english_turn_count = 0
    _last_non_english_lang  = "en"
    _last_reply_generated_at = 0.0
    _call_meta = {"call_sid": "", "phone_number": "", "direction": "inbound",
                  "started_at": datetime.now(tz=None).isoformat()}

    async def _send_audio(audio_bytes: bytes):
        if not stream_sid or not audio_bytes:
            return
        await websocket.send_json({
            "event": "media",
            "streamSid": stream_sid,
            "media": {"payload": base64.b64encode(audio_bytes).decode()}
        })

    async def speak(text: str, language: str = "en"):
        if not stream_sid:
            return
        try:
            audio = await text_to_mulaw(text, language)
            await _send_audio(audio)
            log.info(f"[TWILIO-SPEAK] [{language}] {len(audio)}b — {text[:50]}")
        except Exception as e:
            log.error(f"[TWILIO-SPEAK] {e}")

    async def _silence_reprompt(attempt: int):
        await asyncio.sleep(30)
        if farewell_sent or aria_speaking or not _call_active:
            return
        prompts = _SILENCE_REPROMPTS.get(session_language, _SILENCE_REPROMPTS["en"])
        if attempt == 1:
            await speak(prompts[0], session_language)
            nonlocal _silence_task
            _silence_task = asyncio.create_task(_silence_reprompt(2))
        else:
            await speak(prompts[1], session_language)

    def _cancel_silence_timer():
        nonlocal _silence_task
        if _silence_task and not _silence_task.done():
            _silence_task.cancel()
            _silence_task = None

    def _reset_silence_timer():
        nonlocal _silence_task
        if _silence_task and not _silence_task.done():
            _silence_task.cancel()
        _silence_task = asyncio.create_task(_silence_reprompt(1))

    async def on_speech_start():
        _cancel_silence_timer()

    async def on_transcript(text: str, language: str = "en"):
        if aria_speaking:
            return
        cleaned = text.strip()
        if not cleaned or len(cleaned) < 3:
            return
        if cleaned.lower().rstrip("।.!?,") in _NOISE:
            return
        if len(cleaned.split()) == 1 and len(cleaned) < 5:
            return
        _cancel_silence_timer()
        await transcript_queue.put((cleaned, language, time.monotonic()))

    async def process_queue():
        nonlocal session_language, farewell_sent, aria_speaking
        nonlocal _english_turn_count, _non_english_turn_count, _last_non_english_lang, _last_reply_generated_at
        while True:
            text, stt_language, queued_at = await transcript_queue.get()
            try:
                if not _call_active:
                    continue
                while not transcript_queue.empty():
                    stale_text, stale_lang, stale_at = transcript_queue.get_nowait()
                    transcript_queue.task_done()
                    stt_language, text, queued_at = stale_lang, stale_text, stale_at

                if len(text.split()) <= 2 and not _is_farewell(text) and queued_at < _last_reply_generated_at:
                    continue
                if farewell_sent and _is_farewell(text):
                    continue

                explicit_lang = _detect_explicit_lang(text)
                if explicit_lang:
                    session_language = explicit_lang
                    _english_turn_count = 10 if explicit_lang == "en" else 0
                    _non_english_turn_count = 0 if explicit_lang == "en" else 10
                    _last_non_english_lang = explicit_lang
                elif stt_language != "en":
                    _english_turn_count = 0
                    if stt_language == _last_non_english_lang:
                        _non_english_turn_count += 1
                    else:
                        _non_english_turn_count = 1
                        _last_non_english_lang = stt_language
                    if _non_english_turn_count >= 2:
                        session_language = stt_language
                else:
                    _non_english_turn_count = 0
                    _last_non_english_lang = "en"
                    _english_turn_count += 1
                    if _english_turn_count >= 2:
                        session_language = "en"
                speak_language = session_language

                conversation_history.append({"role": "user", "content": text})
                _llm_start_at = time.monotonic()

                rag_task = start_rag_task(text) if needs_rag(text) else None

                sentences, tts_tasks, first_sentence = [], [], True
                async for sentence in generate_response_stream(
                    text, conversation_history, speak_language, rag_task=rag_task
                ):
                    clean = clean_for_tts(sentence)
                    if not clean:
                        continue
                    sentences.append(clean)
                    lang = _pick_tts_lang(clean, stt_language, speak_language)
                    log.info(f"[LLM] [{lang}] {clean[:80]}")
                    tts_tasks.append((lang, asyncio.create_task(text_to_mulaw(clean, lang))))
                    if first_sentence:
                        first_sentence = False
                        _last_reply_generated_at = time.monotonic()
                        while not transcript_queue.empty():
                            s_text, s_lang, s_at = transcript_queue.get_nowait()
                            transcript_queue.task_done()
                            if s_at < _llm_start_at:
                                await transcript_queue.put((s_text, s_lang, s_at))

                reply = " ".join(sentences) or "Could you say that again?"
                if not sentences:
                    tts_tasks = [(speak_language, asyncio.create_task(text_to_mulaw(reply, speak_language)))]
                    _last_reply_generated_at = time.monotonic()

                log.info(f"[LLM-FULL] {reply}")
                conversation_history.append({"role": "assistant", "content": reply})

                if _is_farewell(text) or any(w in reply.lower() for w in _FAREWELL_IN_REPLY):
                    farewell_sent = True

                aria_speaking = True
                for lang, task in tts_tasks:
                    try:
                        await _send_audio(await task)
                    except Exception as e:
                        log.error(f"[TTS] {e}")
                aria_speaking = False

                if not farewell_sent and _call_active:
                    _reset_silence_timer()
            except Exception as e:
                log.error(f"[QUEUE] {e}")
                aria_speaking = False
            finally:
                transcript_queue.task_done()

    stt = SileroVADSTT(on_transcript=on_transcript, on_speech_start=on_speech_start)
    await stt.start()
    _queue_task = asyncio.create_task(process_queue())

    try:
        async for message in websocket.iter_text():
            data = json.loads(message)
            event = data.get("event")

            if event == "start":
                stream_sid = data["start"]["streamSid"]
                params = data["start"].get("customParameters", {})
                _call_meta["call_sid"]     = params.get("call_sid", stream_sid)
                _call_meta["phone_number"] = params.get("caller_phone", "unknown")
                _call_meta["direction"]    = params.get("direction", "inbound")
                _call_meta["started_at"]   = datetime.now(tz=None).isoformat()
                log.info(f"[TWILIO-WS] Start: {stream_sid} | caller={_call_meta['phone_number']}")
                if _GREETING_AUDIO_EN:
                    asyncio.create_task(_send_audio(_GREETING_AUDIO_EN))
                else:
                    asyncio.create_task(speak(GREETING))

            elif event == "media":
                await stt.send_audio(base64.b64decode(data["media"]["payload"]))

            elif event == "stop":
                log.info("[TWILIO-WS] Stop")
                break

    except Exception as e:
        log.error(f"[TWILIO-WS] {e}")
    finally:
        _call_active = False
        _cancel_silence_timer()
        _queue_task.cancel()
        await stt.stop()
        log.info("[TWILIO-WS] Disconnected")
        if conversation_history:
            _call_meta["ended_at"] = datetime.now(tz=None).isoformat()
            _call_meta["language"] = session_language
            asyncio.create_task(run_post_call_pipeline(conversation_history, _call_meta))


# ─── 4. VoiceLink WebSocket (/voicelink-stream) ───────────────────────────────
# VoiceLink connects here after the webhook response.
# ⚠️  Event names below follow common VoiceLink patterns — verify with their docs.
#     Common alternatives: "call.started" / "audio" / "call.ended"

@app.websocket("/voicelink-stream")
async def voicelink_stream(websocket: WebSocket):
    await websocket.accept()
    log.info("[VL-WS] VoiceLink connected")

    call_id          = None
    conversation_history = []
    transcript_queue = asyncio.Queue()
    session_language = "en"
    farewell_sent    = False
    aria_speaking    = False
    _silence_task    = None
    _call_active     = True
    _english_turn_count     = 0
    _non_english_turn_count = 0
    _last_non_english_lang  = "en"   # must see same language twice in a row to switch
    _last_reply_generated_at = 0.0
    _call_meta = {"call_sid": "", "phone_number": "", "direction": "inbound",
                  "started_at": datetime.now(tz=None).isoformat()}

    async def _send_audio(audio_bytes: bytes):
        """Convert mulaw TTS output → ALAW and send to VoiceLink."""
        if not audio_bytes:
            return
        alaw_bytes = _mulaw_to_alaw(audio_bytes)
        await websocket.send_json({
            "event": "media",
            "media": {"payload": base64.b64encode(alaw_bytes).decode()}
        })

    async def speak(text: str, language: str = "en"):
        try:
            audio = await text_to_mulaw(text, language)
            await _send_audio(audio)
            log.info(f"[VL-SPEAK] [{language}] {len(audio)}b — {text[:50]}")
        except Exception as e:
            log.error(f"[VL-SPEAK] {e}")

    async def _silence_reprompt(attempt: int):
        await asyncio.sleep(30)
        if farewell_sent or aria_speaking or not _call_active:
            return
        prompts = _SILENCE_REPROMPTS.get(session_language, _SILENCE_REPROMPTS["en"])
        if attempt == 1:
            await speak(prompts[0], session_language)
            nonlocal _silence_task
            _silence_task = asyncio.create_task(_silence_reprompt(2))
        else:
            await speak(prompts[1], session_language)

    def _cancel_silence_timer():
        nonlocal _silence_task
        if _silence_task and not _silence_task.done():
            _silence_task.cancel()
            _silence_task = None

    def _reset_silence_timer():
        nonlocal _silence_task
        if _silence_task and not _silence_task.done():
            _silence_task.cancel()
        _silence_task = asyncio.create_task(_silence_reprompt(1))

    async def on_speech_start():
        _cancel_silence_timer()

    async def on_transcript(text: str, language: str = "en"):
        if aria_speaking:
            return
        cleaned = text.strip()
        if not cleaned or len(cleaned) < 3:
            return
        if cleaned.lower().rstrip("।.!?,") in _NOISE:
            return
        if len(cleaned.split()) == 1 and len(cleaned) < 5:
            return
        _cancel_silence_timer()
        await transcript_queue.put((cleaned, language, time.monotonic()))

    async def process_queue():
        nonlocal session_language, farewell_sent, aria_speaking
        nonlocal _english_turn_count, _non_english_turn_count, _last_non_english_lang, _last_reply_generated_at
        while True:
            text, stt_language, queued_at = await transcript_queue.get()
            try:
                if not _call_active:
                    continue
                while not transcript_queue.empty():
                    stale_text, stale_lang, stale_at = transcript_queue.get_nowait()
                    transcript_queue.task_done()
                    stt_language, text, queued_at = stale_lang, stale_text, stale_at

                if len(text.split()) <= 2 and not _is_farewell(text) and queued_at < _last_reply_generated_at:
                    continue
                if farewell_sent and _is_farewell(text):
                    continue

                explicit_lang = _detect_explicit_lang(text)
                if explicit_lang:
                    session_language = explicit_lang
                    _english_turn_count = 10 if explicit_lang == "en" else 0
                    _non_english_turn_count = 0 if explicit_lang == "en" else 10
                    _last_non_english_lang = explicit_lang
                elif stt_language != "en":
                    _english_turn_count = 0
                    if stt_language == _last_non_english_lang:
                        _non_english_turn_count += 1
                    else:
                        _non_english_turn_count = 1
                        _last_non_english_lang = stt_language
                    if _non_english_turn_count >= 2:
                        session_language = stt_language
                else:
                    _non_english_turn_count = 0
                    _last_non_english_lang = "en"
                    _english_turn_count += 1
                    if _english_turn_count >= 2:
                        session_language = "en"
                speak_language = session_language

                conversation_history.append({"role": "user", "content": text})
                _llm_start_at = time.monotonic()

                rag_task = start_rag_task(text) if needs_rag(text) else None

                sentences, tts_tasks, first_sentence = [], [], True
                async for sentence in generate_response_stream(
                    text, conversation_history, speak_language, rag_task=rag_task
                ):
                    clean = clean_for_tts(sentence)
                    if not clean:
                        continue
                    sentences.append(clean)
                    lang = _pick_tts_lang(clean, stt_language, speak_language)
                    log.info(f"[VL-LLM] [{lang}] {clean[:80]}")
                    tts_tasks.append((lang, asyncio.create_task(text_to_mulaw(clean, lang))))
                    if first_sentence:
                        first_sentence = False
                        _last_reply_generated_at = time.monotonic()
                        while not transcript_queue.empty():
                            s_text, s_lang, s_at = transcript_queue.get_nowait()
                            transcript_queue.task_done()
                            if s_at < _llm_start_at:
                                await transcript_queue.put((s_text, s_lang, s_at))

                reply = " ".join(sentences) or "Could you say that again?"
                if not sentences:
                    tts_tasks = [(speak_language, asyncio.create_task(text_to_mulaw(reply, speak_language)))]
                    _last_reply_generated_at = time.monotonic()

                log.info(f"[VL-LLM-FULL] {reply}")
                conversation_history.append({"role": "assistant", "content": reply})

                if _is_farewell(text) or any(w in reply.lower() for w in _FAREWELL_IN_REPLY):
                    farewell_sent = True

                aria_speaking = True
                for lang, task in tts_tasks:
                    try:
                        await _send_audio(await task)
                    except Exception as e:
                        log.error(f"[VL-TTS] {e}")
                aria_speaking = False

                if not farewell_sent and _call_active:
                    _reset_silence_timer()
            except Exception as e:
                log.error(f"[VL-QUEUE] {e}")
                aria_speaking = False
            finally:
                transcript_queue.task_done()

    stt = SileroVADSTT(on_transcript=on_transcript, on_speech_start=on_speech_start)
    _stt_ready = asyncio.Event()

    async def _start_stt():
        await stt.start()
        _stt_ready.set()

    asyncio.create_task(_start_stt())
    _queue_task = asyncio.create_task(process_queue())

    try:
        async for message in websocket.iter_text():
            log.info(f"[VL-RAW] {message[:300]}")
            data = json.loads(message)
            event = data.get("event") or data.get("type") or ""

            if event == "connected":
                log.info("[VL-WS] Handshake connected")

            elif event == "start":
                start_data = data.get("start", {})
                call_id = data.get("stream_sid") or start_data.get("stream_sid") or ""
                _call_meta["call_sid"]     = start_data.get("call_sid", call_id)
                _call_meta["phone_number"] = start_data.get("from", "unknown")
                _call_meta["direction"]    = "inbound"
                _call_meta["started_at"]   = datetime.now(tz=None).isoformat()
                custom = start_data.get("custom_parameters", {})
                log.info(f"[VL-WS] Stream started: {call_id} | from={_call_meta['phone_number']} | custom={custom}")
                if _GREETING_AUDIO_EN:
                    asyncio.create_task(_send_audio(_GREETING_AUDIO_EN))
                else:
                    asyncio.create_task(speak(GREETING))

            elif event == "media":
                if _stt_ready.is_set():
                    raw = data.get("media", {}).get("payload", "")
                    if raw:
                        alaw_bytes = base64.b64decode(raw)
                        mulaw_bytes = _alaw_to_mulaw(alaw_bytes)
                        await stt.send_audio(mulaw_bytes)

            elif event == "stop":
                log.info("[VL-WS] Stream stopped")
                break

    except Exception as e:
        log.error(f"[VL-WS] {e}")
    finally:
        _call_active = False
        _cancel_silence_timer()
        _queue_task.cancel()
        await stt.stop()
        log.info("[VL-WS] Disconnected")
        if conversation_history:
            _call_meta["ended_at"] = datetime.now(tz=None).isoformat()
            _call_meta["language"] = session_language
            asyncio.create_task(run_post_call_pipeline(conversation_history, _call_meta))


# ─── 5. VoBiz Answer URL (/vobiz-answer) ─────────────────────────────────────
# VoBiz hits this URL when a call arrives. We return XML that tells VoBiz
# to open a bidirectional WebSocket stream to /vobiz-stream.

@app.api_route("/vobiz-answer", methods=["GET", "POST"])
async def vobiz_answer(request: Request):
    # VoBiz POSTs From/To in the answer request body
    try:
        form = await request.form()
        caller_from = form.get("From", "") or form.get("from", "")
        caller_to   = form.get("To",   "") or form.get("to",   "")
    except Exception:
        caller_from = caller_to = ""

    ws_url     = PUBLIC_URL.replace("https://", "wss://").replace("http://", "ws://")
    stream_url = f"{ws_url}/vobiz-stream"
    status_url = f"{PUBLIC_URL}/vobiz-status"

    # Pass caller phone via extraHeaders into WebSocket start event
    extra      = f"from={caller_from},to={caller_to}" if caller_from else ""
    extra_attr = f' extraHeaders="{extra}"' if extra else ""

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f'<Stream bidirectional="true" keepCallAlive="true"'
        f' contentType="audio/x-mulaw;rate=8000"'
        f' statusCallbackUrl="{status_url}"'
        f'{extra_attr}>{stream_url}</Stream>'
        "</Response>"
    )
    log.info(f"[VB] /vobiz-answer from={caller_from} to={caller_to} → {stream_url}")
    return Response(content=xml, media_type="application/xml")


@app.api_route("/vobiz-status", methods=["GET", "POST"])
async def vobiz_status(request: Request):
    try:
        form = await request.form()
        body = dict(form)
    except Exception:
        try:
            body = await request.json()
        except Exception:
            body = {}
    event = body.get("Event", "")
    log.info(f"[VB-STATUS] {event} | from={body.get('From','')} to={body.get('To','')} call={body.get('CallUUID','')}")
    return Response(content="OK", media_type="text/plain")


# ─── 6. VoBiz WebSocket (/vobiz-stream) ──────────────────────────────────────

@app.websocket("/vobiz-stream")
async def vobiz_stream(websocket: WebSocket):
    await websocket.accept()
    log.info("[VB-WS] VoBiz connected")

    stream_id        = None
    call_id          = None
    conversation_history = []
    transcript_queue = asyncio.Queue()
    session_language = "en"
    farewell_sent    = False
    aria_speaking    = False
    _silence_task    = None
    _call_active     = True
    _english_turn_count     = 0
    _non_english_turn_count = 0
    _last_non_english_lang  = "en"
    _last_reply_generated_at = 0.0
    _inbound_encoding  = "audio/x-mulaw"
    _returning_guest   = None        # set after phone lookup at call start
    _available_rooms   = None        # set after Djubo availability check (None=not yet checked, []=none available)
    _availability_done = False       # triggers background availability check once dates are known
    _djubo_task        = None        # background asyncio.Task for availability check
    _call_meta = {"call_sid": "", "phone_number": "", "direction": "inbound",
                  "started_at": datetime.now(tz=None).isoformat()}

    async def _send_audio(audio_bytes: bytes):
        """Send mulaw audio to VoBiz via playAudio event."""
        if not stream_id or not audio_bytes:
            return
        await websocket.send_json({
            "event": "playAudio",
            "streamId": stream_id,
            "media": {
                "contentType": "audio/x-mulaw",
                "sampleRate": 8000,
                "payload": base64.b64encode(audio_bytes).decode()
            }
        })

    async def speak(text: str, language: str = "en"):
        try:
            audio = await text_to_mulaw(text, language)
            await _send_audio(audio)
            log.info(f"[VB-SPEAK] [{language}] {len(audio)}b — {text[:50]}")
        except Exception as e:
            log.error(f"[VB-SPEAK] {e}")

    async def _silence_reprompt(attempt: int):
        await asyncio.sleep(30)
        if farewell_sent or aria_speaking or not _call_active:
            return
        prompts = _SILENCE_REPROMPTS.get(session_language, _SILENCE_REPROMPTS["en"])
        if attempt == 1:
            await speak(prompts[0], session_language)
            nonlocal _silence_task
            _silence_task = asyncio.create_task(_silence_reprompt(2))
        else:
            await speak(prompts[1], session_language)

    def _cancel_silence_timer():
        nonlocal _silence_task
        if _silence_task and not _silence_task.done():
            _silence_task.cancel()
            _silence_task = None

    def _reset_silence_timer():
        nonlocal _silence_task
        if _silence_task and not _silence_task.done():
            _silence_task.cancel()
        _silence_task = asyncio.create_task(_silence_reprompt(1))

    async def on_speech_start():
        _cancel_silence_timer()
        if aria_speaking and stream_id:
            try:
                await websocket.send_json({"event": "clearAudio", "streamId": stream_id})
            except Exception:
                pass

    async def on_transcript(text: str, language: str = "en"):
        if aria_speaking:
            return
        cleaned = text.strip()
        if not cleaned or len(cleaned) < 3:
            return
        if cleaned.lower().rstrip("।.!?,") in _NOISE:
            return
        if len(cleaned.split()) == 1 and len(cleaned) < 5:
            return
        _cancel_silence_timer()
        await transcript_queue.put((cleaned, language, time.monotonic()))

    async def process_queue():
        nonlocal session_language, farewell_sent, aria_speaking
        nonlocal _english_turn_count, _non_english_turn_count, _last_non_english_lang, _last_reply_generated_at
        nonlocal _available_rooms, _availability_done, _djubo_task
        while True:
            text, stt_language, queued_at = await transcript_queue.get()
            try:
                if not _call_active:
                    continue
                while not transcript_queue.empty():
                    stale_text, stale_lang, stale_at = transcript_queue.get_nowait()
                    transcript_queue.task_done()
                    stt_language, text, queued_at = stale_lang, stale_text, stale_at

                if len(text.split()) <= 2 and not _is_farewell(text) and queued_at < _last_reply_generated_at:
                    continue
                if farewell_sent and _is_farewell(text):
                    continue

                explicit_lang = _detect_explicit_lang(text)
                if explicit_lang:
                    session_language = explicit_lang
                    _english_turn_count = 10 if explicit_lang == "en" else 0
                    _non_english_turn_count = 0 if explicit_lang == "en" else 10
                    _last_non_english_lang = explicit_lang
                elif stt_language != "en":
                    _english_turn_count = 0
                    if stt_language == _last_non_english_lang:
                        _non_english_turn_count += 1
                    else:
                        _non_english_turn_count = 1
                        _last_non_english_lang = stt_language
                    if _non_english_turn_count >= 2:
                        session_language = stt_language
                else:
                    _non_english_turn_count = 0
                    _last_non_english_lang = "en"
                    _english_turn_count += 1
                    if _english_turn_count >= 2:
                        session_language = "en"
                speak_language = session_language

                conversation_history.append({"role": "user", "content": text})
                _llm_start_at = time.monotonic()

                # Trigger Djubo availability check once both dates are confirmed.
                # Runs as background task so it never blocks the LLM response.
                if not _availability_done:
                    checkin_iso, checkout_iso = _extract_iso_dates(conversation_history)
                    if checkin_iso and checkout_iso:
                        _availability_done = True
                        log.info(f"[DJUBO] Triggering availability (background): {checkin_iso} → {checkout_iso}")
                        async def _fetch_avail(_ci=checkin_iso, _co=checkout_iso):
                            nonlocal _available_rooms
                            try:
                                _available_rooms = await get_available_room_names(_ci, _co)
                                log.info(f"[DJUBO] Rooms available: {_available_rooms}")
                            except Exception as _e:
                                log.warning(f"[DJUBO] availability check failed: {_e}")
                        _djubo_task = asyncio.create_task(_fetch_avail())
                # If a background Djubo task just finished, its result is already in _available_rooms

                rag_task = start_rag_task(text) if needs_rag(text) else None

                sentences, tts_tasks, first_sentence = [], [], True
                async for sentence in generate_response_stream(
                    text, conversation_history, speak_language, rag_task=rag_task,
                    returning_guest=_returning_guest, available_rooms=_available_rooms,
                ):
                    clean = clean_for_tts(sentence)
                    if not clean:
                        continue
                    sentences.append(clean)
                    lang = _pick_tts_lang(clean, stt_language, speak_language)
                    log.info(f"[VB-LLM] [{lang}] {clean[:80]}")
                    tts_tasks.append((lang, asyncio.create_task(text_to_mulaw(clean, lang))))
                    if first_sentence:
                        first_sentence = False
                        _last_reply_generated_at = time.monotonic()
                        while not transcript_queue.empty():
                            s_text, s_lang, s_at = transcript_queue.get_nowait()
                            transcript_queue.task_done()
                            if s_at < _llm_start_at:
                                await transcript_queue.put((s_text, s_lang, s_at))

                reply = " ".join(sentences) or "Could you say that again?"
                if not sentences:
                    tts_tasks = [(speak_language, asyncio.create_task(text_to_mulaw(reply, speak_language)))]
                    _last_reply_generated_at = time.monotonic()

                log.info(f"[VB-LLM-FULL] {reply}")
                conversation_history.append({"role": "assistant", "content": reply})

                if _is_farewell(text) or any(w in reply.lower() for w in _FAREWELL_IN_REPLY):
                    farewell_sent = True

                aria_speaking = True
                for lang, task in tts_tasks:
                    try:
                        await _send_audio(await task)
                    except Exception as e:
                        log.error(f"[VB-TTS] {e}")
                aria_speaking = False

                if farewell_sent:
                    await asyncio.sleep(0.5)  # brief pause so final audio drains
                    log.info("[VB-WS] Farewell sent — closing connection")
                    await websocket.close()
                    return
                if _call_active:
                    _reset_silence_timer()
            except Exception as e:
                log.error(f"[VB-QUEUE] {e}")
                aria_speaking = False
            finally:
                transcript_queue.task_done()

    stt = SileroVADSTT(on_transcript=on_transcript, on_speech_start=on_speech_start)
    _stt_ready = asyncio.Event()

    async def _start_stt():
        await stt.start()
        _stt_ready.set()

    asyncio.create_task(_start_stt())
    _queue_task = asyncio.create_task(process_queue())

    try:
        async for message in websocket.iter_text():
            data = json.loads(message)
            event = data.get("event", "")

            if event == "start":
                start_data = data.get("start", {})
                stream_id  = start_data.get("streamId", "")
                call_id    = start_data.get("callId", "")
                # extraHeaders passed from /vobiz-answer: "from=91xxx,to=91xxx"
                extra_raw = start_data.get("extraHeaders", "")
                extra = dict(kv.split("=", 1) for kv in extra_raw.split(",") if "=" in kv)
                phone = extra.get("from", start_data.get("from", "unknown"))
                _call_meta["call_sid"]     = call_id
                _call_meta["phone_number"] = phone
                _call_meta["direction"]    = "inbound"
                _call_meta["started_at"]   = datetime.now(tz=None).isoformat()
                fmt = start_data.get("mediaFormat", {})
                _inbound_encoding = fmt.get("encoding", "audio/x-mulaw")
                log.info(f"[VB-WS] Stream started: {stream_id} | callId={call_id} | fmt={fmt}")

                # Returning guest lookup (non-blocking)
                async def _lookup_guest():
                    nonlocal _returning_guest
                    try:
                        guest = await asyncio.get_event_loop().run_in_executor(
                            None, get_guest_by_phone, phone
                        )
                        if guest:
                            _returning_guest = guest
                            log.info(f"[GUEST] Returning: {guest['name']}")
                    except Exception as _e:
                        log.warning(f"[GUEST] lookup failed: {_e}")
                asyncio.create_task(_lookup_guest())

                if _GREETING_AUDIO_EN:
                    asyncio.create_task(_send_audio(_GREETING_AUDIO_EN))
                else:
                    asyncio.create_task(speak(GREETING))

            elif event == "media":
                if _stt_ready.is_set():
                    raw = data.get("media", {}).get("payload", "")
                    if raw:
                        audio_bytes = base64.b64decode(raw)
                        await stt.send_audio(audio_bytes)

            elif event == "playedStream":
                log.info(f"[VB-WS] Checkpoint reached: {data.get('name','')}")

            elif event == "clearedAudio":
                log.info("[VB-WS] Audio cleared (barge-in)")

    except Exception as e:
        if "disconnect" not in str(e).lower() and "close" not in str(e).lower():
            log.error(f"[VB-WS] {e}")
    finally:
        _call_active = False
        _cancel_silence_timer()
        _queue_task.cancel()
        await stt.stop()
        log.info("[VB-WS] Disconnected")
        if conversation_history:
            _call_meta["ended_at"] = datetime.now(tz=None).isoformat()
            _call_meta["language"] = session_language
            asyncio.create_task(run_post_call_pipeline(conversation_history, _call_meta))


# ─── 7. VoBiz Answer URL — Gemini Live (/vobiz-answer-gemini) ─────────────────
# Separate answer URL so VoBiz can be pointed to Gemini Live without touching
# the existing /vobiz-answer → /vobiz-stream pipeline.

@app.api_route("/vobiz-answer-gemini", methods=["GET", "POST"])
async def vobiz_answer_gemini(request: Request):
    try:
        form = await request.form()
        caller_from = form.get("From", "") or form.get("from", "")
        caller_to   = form.get("To",   "") or form.get("to",   "")
    except Exception:
        caller_from = caller_to = ""

    ws_url     = PUBLIC_URL.replace("https://", "wss://").replace("http://", "ws://")
    stream_url = f"{ws_url}/vobiz-stream-gemini"
    status_url = f"{PUBLIC_URL}/vobiz-status"

    extra      = f"from={caller_from},to={caller_to}" if caller_from else ""
    extra_attr = f' extraHeaders="{extra}"' if extra else ""

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f'<Stream bidirectional="true" keepCallAlive="true"'
        f' contentType="audio/x-mulaw;rate=8000"'
        f' statusCallbackUrl="{status_url}"'
        f'{extra_attr}>{stream_url}</Stream>'
        "</Response>"
    )
    log.info(f"[VB-G] /vobiz-answer-gemini from={caller_from} → {stream_url}")
    return Response(content=xml, media_type="application/xml")


# ─── 8. VoBiz WebSocket — Gemini Live (/vobiz-stream-gemini) ─────────────────
# Single-step S2S: VoBiz mulaw → Gemini Live → mulaw → VoBiz.
# No Silero VAD, no Sarvam STT, no OpenRouter LLM, no Sarvam TTS.

@app.websocket("/vobiz-stream-gemini")
async def vobiz_stream_gemini(websocket: WebSocket):
    await websocket.accept()
    log.info("[VB-G] Gemini Live WebSocket connected")

    from prompts.hotel_prompt import GEMINI_SYSTEM_PROMPT as _HOTEL_PROMPT

    stream_id     = None
    farewell_sent = False
    _call_active  = True
    _silence_task = None
    _silence_attempt_global = 0   # persists across reconnects so attempt 2 (farewell) is reached
    _pre_audio_buf: list[bytes] = []   # Gemini audio buffered before stream_id is known
    _fetched_months: set[int]   = set()  # avoid duplicate far-date availability fetches
    _call_meta = {
        "call_sid": "", "phone_number": "", "direction": "inbound",
        "started_at": datetime.now(tz=None).isoformat(),
    }

    # Usage tracking — mulaw 8kHz: 8000 bytes/sec
    _audio_in_bytes  = 0   # caller audio sent to Gemini
    _audio_out_bytes = 0   # Gemini audio sent to caller

    # Pricing constants (Gemini 2.0 Flash Live)
    _GEMINI_MODEL_NAME       = os.getenv("GEMINI_LIVE_MODEL", "gemini-2.0-flash-live-001")
    _gemini_in_per_1m        = float(os.getenv("GEMINI_AUDIO_IN_COST_PER_1M",  "0.70"))
    _gemini_out_per_1m       = float(os.getenv("GEMINI_AUDIO_OUT_COST_PER_1M", "2.10"))
    _GEMINI_IN_COST_PER_SEC  = (_gemini_in_per_1m  / 1_000_000) * 25  # 25 tokens/sec
    _GEMINI_OUT_COST_PER_SEC = (_gemini_out_per_1m / 1_000_000) * 25
    _VOBIZ_COST_PER_MIN_IN  = float(os.getenv("VOBIZ_COST_PER_MIN_INBOUND",  "0.0054"))
    _VOBIZ_COST_PER_MIN_OUT = float(os.getenv("VOBIZ_COST_PER_MIN_OUTBOUND", "0.0090"))

    conversation_history: list[dict] = []
    _pending_agent_text: list[str]   = []

    # Parallel pricing agent state
    _pricing_fetch_key:   str                = ""    # "checkin|checkout" — avoids duplicate fetches
    _pricing_agent_task: asyncio.Task | None = None

    # Recording buffers — raw mulaw 8kHz bytes for both sides
    _audio_in_buf:  bytearray = bytearray()   # guest → Gemini
    _audio_out_buf: bytearray = bytearray()   # Gemini → guest

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _send_audio(mulaw_bytes: bytes):
        nonlocal _audio_out_bytes
        if not mulaw_bytes:
            return
        _audio_out_bytes += len(mulaw_bytes)
        _audio_out_buf.extend(mulaw_bytes)   # record Maya's audio
        if not stream_id:
            _pre_audio_buf.append(mulaw_bytes)  # buffer until stream_id arrives
            return
        await websocket.send_json({
            "event": "playAudio",
            "streamId": stream_id,
            "media": {
                "contentType": "audio/x-mulaw",
                "sampleRate": 8000,
                "payload": base64.b64encode(mulaw_bytes).decode(),
            },
        })

    async def _on_interrupted():
        if stream_id:
            try:
                await websocket.send_json({"event": "clearAudio", "streamId": stream_id})
                log.info("[VB-G] clearAudio sent (barge-in)")
            except Exception:
                pass

    async def _on_user_transcript(text: str):
        nonlocal _silence_attempt_global, _pricing_agent_task
        log.info(f"[VB-G USER] {text}")
        _cancel_silence_timer()
        _flush_agent_turn()
        _silence_attempt_global = 0   # guest spoke — reset silence counter
        conversation_history.append({"role": "user", "content": text})

        # Trigger parallel pricing agent after each user turn (non-blocking)
        if _pricing_agent_task is None or _pricing_agent_task.done():
            _pricing_agent_task = asyncio.create_task(_run_pricing_agent())

        # Detect far-future month mention → refresh Djubo availability for that month
        m = _MONTH_PATTERN.search(text)
        if m:
            month_name  = m.group(1).lower()
            target_num  = _MONTH_NUMS.get(month_name, 0)
            if target_num and target_num not in _fetched_months:
                today   = date.today()
                cutoff  = today + timedelta(days=31)
                year    = today.year
                try:
                    target = date(year, target_num, 1)
                    if target < today:
                        target = date(year + 1, target_num, 1)
                except ValueError:
                    target = None
                if target and target > cutoff:
                    _fetched_months.add(target_num)
                    last_day = calendar.monthrange(target.year, target_num)[1]
                    asyncio.create_task(
                        _fetch_availability_for_range(
                            target.isoformat(),
                            date(target.year, target_num, last_day).isoformat(),
                            month_name.capitalize(),
                        )
                    )

    async def _on_agent_text(text: str):
        nonlocal farewell_sent
        _pending_agent_text.append(text)
        full = " ".join(_pending_agent_text)
        log.info(f"[VB-G AGENT] {text}")
        if any(w in full.lower() for w in _FAREWELL_IN_REPLY):
            farewell_sent = True
            _flush_agent_turn()
            await asyncio.sleep(5)   # allow TTS audio to finish playing before closing
            try:
                await websocket.close()
            except Exception:
                pass

    def _flush_agent_turn():
        if _pending_agent_text:
            full = " ".join(_pending_agent_text).strip()
            if full:
                conversation_history.append({"role": "assistant", "content": full})
            _pending_agent_text.clear()

    async def _silence_reprompt(attempt: int):
        nonlocal _silence_attempt_global
        delay = 12 if attempt == 1 else 10
        await asyncio.sleep(delay)
        if farewell_sent or not _call_active:
            return
        _silence_attempt_global += 1
        if gemini._session:
            from google.genai import types as _gt
            if _silence_attempt_global == 1:
                note = "[system: guest has been silent — gently ask if they are still there]"
            else:
                note = (
                    "[system: guest is still silent. Warmly wrap up the call now with the standard farewell: "
                    "'Thank you for calling Lotus Sutra Goa, we look forward to welcoming you to Arambol!' "
                    "Say nothing else after the farewell.]"
                )
            try:
                await gemini._session.send_client_content(
                    turns=_gt.Content(
                        role="user",
                        parts=[_gt.Part(text=note)],
                    ),
                    turn_complete=True,
                )
                log.info(f"[SILENCE] Attempt {_silence_attempt_global} (local={attempt}) — note injected")
            except Exception as _e:
                log.warning(f"[SILENCE] Note inject error: {_e}")
        nonlocal _silence_task
        if _silence_attempt_global < 2:
            _silence_task = asyncio.create_task(_silence_reprompt(2))

    def _cancel_silence_timer():
        nonlocal _silence_task
        if _silence_task and not _silence_task.done():
            _silence_task.cancel()
            _silence_task = None

    def _reset_silence_timer():
        nonlocal _silence_task
        if _silence_task and not _silence_task.done():
            _silence_task.cancel()
        _silence_task = asyncio.create_task(_silence_reprompt(1))

    async def _run_pricing_agent():
        """Parallel watcher: extract dates+room from history → fetch Djubo pricing → inject note."""
        nonlocal _pricing_fetch_key, _pricing_agent_task
        if len(conversation_history) < 2:
            return
        import httpx as _httpx

        recent = conversation_history[-10:]
        transcript = "\n".join(f"{t['role'].upper()}: {t['content']}" for t in recent)
        today_iso  = date.today().isoformat()

        try:
            async with _httpx.AsyncClient(timeout=8) as _c:
                _r = await _c.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY', '')}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "google/gemini-flash-1.5-8b",
                        "messages": [{
                            "role": "user",
                            "content": (
                                f"Hotel booking conversation (today={today_iso}):\n{transcript}\n\n"
                                "Extract check-in date, check-out date, and room type if both dates are confirmed. "
                                "Dates must be in the future. Reply JSON only:\n"
                                '{"checkin":"YYYY-MM-DD","checkout":"YYYY-MM-DD","room_type":"string"}\n'
                                "Use null for any missing value."
                            ),
                        }],
                        "max_tokens": 60,
                        "temperature": 0,
                    },
                )
            raw = _r.json()["choices"][0]["message"]["content"].strip()
            raw = raw.strip("```json").strip("```").strip()
            info = json.loads(raw)
        except Exception as _e:
            log.debug(f"[PRICING-AGENT] extraction failed: {_e}")
            return

        checkin   = info.get("checkin")
        checkout  = info.get("checkout")

        if not checkin or not checkout or checkin == "null" or checkout == "null":
            return
        try:
            _ci, _co = date.fromisoformat(checkin), date.fromisoformat(checkout)
            if _ci >= _co or _ci < date.today():
                return
        except Exception:
            return

        fetch_key = f"{checkin}|{checkout}"
        if fetch_key == _pricing_fetch_key:
            return
        _pricing_fetch_key = fetch_key

        log.info(f"[PRICING-AGENT] Fetching pricing for {checkin}→{checkout}")
        pricing = await get_room_pricing(checkin, checkout)
        if not pricing:
            log.info("[PRICING-AGENT] No pricing returned from Djubo")
            return

        lines = [f"{name.title()}: ₹{price:,}/night" for name, price in pricing.items()]
        note = (
            f"[System: Live room pricing for {checkin} to {checkout} — "
            + ", ".join(lines)
            + ". Quote these exact prices when the guest asks about rates for these dates.]"
        )
        await gemini.send_system_note(note)
        log.info(f"[PRICING-AGENT] Pricing injected → {pricing}")

    async def _fetch_and_inject_availability():
        """Fetch Djubo live availability for next 30 days and inject silently into Gemini."""
        today = date.today()
        end   = today + timedelta(days=30)
        names = await get_available_room_names(today.isoformat(), end.isoformat())
        if names:
            await gemini.send_system_note(
                f"Live Djubo availability (next 30 days): {', '.join(names)}. "
                "Use this when guest asks about room availability."
            )
        elif names is not None:
            await gemini.send_system_note(
                "No rooms available in the next 30 days per Djubo PMS. "
                "Suggest the guest contact us for alternative dates."
            )

    async def _fetch_availability_for_range(start_iso: str, end_iso: str, label: str):
        """Fetch Djubo availability for a specific far-future date range."""
        names = await get_available_room_names(start_iso, end_iso)
        if names:
            await gemini.send_system_note(
                f"Live Djubo availability for {label}: {', '.join(names)}."
            )
        elif names is not None:
            await gemini.send_system_note(f"No rooms available for {label} per Djubo PMS.")

    # ── System prompt — inject current IST date/time to prevent past-date bookings ──
    _IST = timezone(timedelta(hours=5, minutes=30))
    _now = datetime.now(_IST)
    _date_line = (
        f"[Today is {_now.strftime('%A, %d %B %Y')}. "
        f"Current time: {_now.strftime('%I:%M %p')} IST. "
        "Never accept or confirm bookings for past dates — gently redirect if the guest mentions one.]"
    )
    system_prompt = (
        _date_line + "\n\n"
        + _HOTEL_PROMPT.replace(
            "Reply in {language};",
            "Detect the guest's language from their speech and reply in the same language (Hindi, Marathi, or English);"
        )
    )

    async def _on_reconnect():
        # Restart silence timer after every reconnect so guest silence is caught
        _reset_silence_timer()

    gemini = GeminiLiveSession(
        system_prompt=system_prompt,
        on_audio_out=_send_audio,
        on_interrupted=_on_interrupted,
        on_user_transcript=_on_user_transcript,
        on_agent_text=_on_agent_text,
        on_reconnect=_on_reconnect,
    )

    async def _on_vad_speech_start():
        _cancel_silence_timer()
        await gemini.send_activity_start()

    async def _on_vad_speech_end():
        await gemini.send_activity_end()
        _reset_silence_timer()

    vad = SileroVADOnly(
        on_speech_start=_on_vad_speech_start,
        on_speech_end=_on_vad_speech_end,
    )
    _vad_ready = asyncio.Event()

    async def _start_vad():
        await vad.start()
        _vad_ready.set()

    asyncio.create_task(_start_vad())

    # Pre-connect Gemini immediately so it's ready when the caller speaks.
    # No greeting_text — the cached Sarvam greeting plays on "start" event with zero latency.
    await gemini.start()

    # ── VoBiz message loop ────────────────────────────────────────────────────

    try:
        async for message in websocket.iter_text():
            data  = json.loads(message)
            event = data.get("event", "")

            if event == "start":
                start_data = data.get("start", {})
                stream_id  = start_data.get("streamId", "")
                call_id    = start_data.get("callId", "")
                extra_raw  = start_data.get("extraHeaders", "")
                extra = dict(kv.split("=", 1) for kv in extra_raw.split(",") if "=" in kv)
                phone = extra.get("from", start_data.get("from", "unknown"))
                _call_meta.update({
                    "call_sid": call_id,
                    "phone_number": phone,
                    "started_at": datetime.now(tz=None).isoformat(),
                })
                log.info(f"[VB-G] Stream started: {stream_id} | callId={call_id} | from={phone}")

                # Play cached greeting immediately — Gemini Kore voice preferred, Sarvam fallback
                _greeting_audio = _GEMINI_GREETING_AUDIO or _GREETING_AUDIO_EN
                if _greeting_audio:
                    asyncio.create_task(_send_audio(_greeting_audio))
                    gemini.inject_agent_turn(GREETING)
                    src = "Gemini/Kore" if _GEMINI_GREETING_AUDIO else "Sarvam"
                    log.info(f"[VB-G] Greeting played ({src}), injected into Gemini history")

                # Flush any Gemini audio buffered before stream_id was known
                if _pre_audio_buf:
                    log.info(f"[VB-G] Flushing {len(_pre_audio_buf)} pre-buffered audio chunks")
                    for chunk in list(_pre_audio_buf):
                        asyncio.create_task(_send_audio(chunk))
                    _pre_audio_buf.clear()

                # Fire Djubo availability check in background — no latency impact
                asyncio.create_task(_fetch_and_inject_availability())
                _reset_silence_timer()

            elif event == "media":
                raw = data.get("media", {}).get("payload", "")
                if raw:
                    audio = base64.b64decode(raw)
                    _audio_in_bytes += len(audio)
                    _audio_in_buf.extend(audio)    # record guest's audio
                    await gemini.send_audio(audio)
                    if _vad_ready.is_set():
                        await vad.send_audio(audio)

            elif event == "playedStream":
                log.info(f"[VB-G] Checkpoint: {data.get('name', '')}")

            elif event == "clearedAudio":
                log.info("[VB-G] Audio cleared (barge-in confirmed)")

            elif event == "stop":
                log.info("[VB-G] Stream stopped by VoBiz")
                break

    async def _create_and_upload_recording(call_sid: str,
                                            audio_in: bytearray,
                                            audio_out: bytearray) -> str | None:
        """Mix guest + Maya mulaw buffers into a mono WAV and upload to Supabase Storage."""
        import audioop, wave, io
        if not audio_in and not audio_out:
            return None
        try:
            # Convert mulaw → PCM 16-bit (2 bytes/sample, 8000 Hz)
            pcm_in  = audioop.ulaw2lin(bytes(audio_in),  2) if audio_in  else b""
            pcm_out = audioop.ulaw2lin(bytes(audio_out), 2) if audio_out else b""
            # Pad shorter stream with silence
            if len(pcm_in) < len(pcm_out):
                pcm_in  = pcm_in  + bytes(len(pcm_out) - len(pcm_in))
            elif len(pcm_out) < len(pcm_in):
                pcm_out = pcm_out + bytes(len(pcm_in) - len(pcm_out))
            # Mix both channels at 50% each to avoid clipping
            mixed = audioop.add(pcm_in, pcm_out, 2)
            # Write WAV to an in-memory buffer
            wav_buf = io.BytesIO()
            with wave.open(wav_buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(8000)
                wf.writeframes(mixed)
            wav_bytes = wav_buf.getvalue()
            # Upload to Supabase Storage
            from services.database import _get_client as _db
            db = _db()
            if not db:
                return None
            path = f"{call_sid}.wav"
            db.storage.from_("recordings").upload(
                path,
                wav_bytes,
                {"content-type": "audio/wav", "upsert": "true"},
            )
            public_url = db.storage.from_("recordings").get_public_url(path)
            log.info(f"[VB-G] Recording uploaded → {public_url}")
            return public_url
        except Exception as rec_err:
            log.error(f"[VB-G] Recording upload failed: {rec_err}")
            return None

    except Exception as e:
        if "disconnect" not in str(e).lower() and "close" not in str(e).lower():
            log.error(f"[VB-G] {e}")
    finally:
        _call_active = False
        _cancel_silence_timer()
        _flush_agent_turn()
        await gemini.stop()
        await vad.stop()
        log.info("[VB-G] Disconnected")
        _call_meta["ended_at"] = datetime.now(tz=None).isoformat()
        _call_meta["language"] = "hi"

        # Log usage/billing
        from services.database import log_usage as _log_usage
        _audio_in_secs  = _audio_in_bytes  / 8000
        _audio_out_secs = _audio_out_bytes / 8000
        _gemini_cost    = (_audio_in_secs * _GEMINI_IN_COST_PER_SEC
                         + _audio_out_secs * _GEMINI_OUT_COST_PER_SEC)
        _log_usage(
            call_sid         = _call_meta.get("call_sid", ""),
            service          = "gemini_live",
            model            = _GEMINI_MODEL_NAME,
            audio_in_seconds = round(_audio_in_secs, 2),
            audio_out_seconds= round(_audio_out_secs, 2),
            cost_usd         = _gemini_cost,
        )
        try:
            _start = datetime.fromisoformat(_call_meta["started_at"])
            _end   = datetime.fromisoformat(_call_meta["ended_at"])
            _dur   = max(0, (_end - _start).total_seconds())
        except Exception:
            _dur = 0
        _direction  = _call_meta.get("direction", "inbound")
        _vobiz_rate = _VOBIZ_COST_PER_MIN_OUT if _direction == "outbound" else _VOBIZ_COST_PER_MIN_IN
        _vobiz_cost = (_dur / 60) * _vobiz_rate
        _log_usage(
            call_sid          = _call_meta.get("call_sid", ""),
            service           = "vobiz",
            model             = f"VoBiz ({_direction})",
            duration_seconds  = round(_dur, 2),
            cost_usd          = _vobiz_cost,
        )
        log.info(f"[VB-G] Usage logged — Gemini: ${_gemini_cost:.6f} | VoBiz: ${_vobiz_cost:.6f}")

        # Upload recording then hand off to post-call pipeline
        _call_sid_for_rec = _call_meta.get("call_sid", "unknown")
        _rec_url = await _create_and_upload_recording(
            _call_sid_for_rec, _audio_in_buf, _audio_out_buf
        )
        if _rec_url:
            _call_meta["recording_url"] = _rec_url

        if conversation_history:
            asyncio.create_task(run_post_call_pipeline(conversation_history, _call_meta))


# ─── Health check ─────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "agent": "Lotus Sutra Goa — Maya", "telephony": TELEPHONY}


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    log.info(f"Starting Lotus Sutra Voice Agent on port {port}")
    log.info(f"Telephony: {TELEPHONY}")
    log.info(f"Twilio webhook:    {PUBLIC_URL}/incoming-call")
    log.info(f"VoiceLink webhook: {PUBLIC_URL}/voicelink-webhook")
    log.info(f"VoiceLink stream:  {PUBLIC_URL}/voicelink-stream")
    log.info(f"VoBiz Answer URL:  {PUBLIC_URL}/vobiz-answer")
    log.info(f"VoBiz stream:      {PUBLIC_URL}/vobiz-stream")
    log.info(f"Gemini Live Answer:{PUBLIC_URL}/vobiz-answer-gemini")
    log.info(f"Gemini Live stream:{PUBLIC_URL}/vobiz-stream-gemini")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False, log_level="info")
