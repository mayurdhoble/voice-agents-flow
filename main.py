import os
import sys
import json
import base64
import asyncio
import logging
import time
import audioop
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from services.stt_livekit import SileroVADSTT
from services.llm import generate_response_stream, needs_rag, start_rag_task
from services.tts import text_to_mulaw, clean_for_tts
from services.extraction import run_post_call_pipeline
from services.database import get_guest_by_phone
from services.djubo import get_available_room_names

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


def _parse_date_to_iso(date_str: str) -> str | None:
    """Convert human-readable date like 'tenth December' or '10 August' to YYYY-MM-DD."""
    try:
        import dateparser
        from datetime import datetime as _dt
        parsed = dateparser.parse(date_str, settings={"PREFER_DATES_FROM": "future", "DATE_ORDER": "DMY"})
        if parsed:
            return parsed.strftime("%Y-%m-%d")
    except Exception:
        pass
    return None


def _extract_iso_dates(history: list[dict]) -> tuple[str | None, str | None]:
    """Extract confirmed check-in and check-out as ISO dates from conversation history."""
    import re
    checkin_raw = checkout_raw = None

    # Flexible date capture: stops at punctuation or 'and'/'to'
    _DATE = r"((?:[A-Za-z0-9]+[,\s\-/]*){1,6}?)(?=\s*(?:and|to|till|through|\.|\,|\?|$))"

    _CHECKIN_PATS = [
        r"check[- ]?in\s*(?:date\s*)?(?:is|:|-|on|will be|would be)\s*(?:on\s+)?(?:the\s+)?" + _DATE,
        r"arriving\s+(?:on\s+)?(?:the\s+)?" + _DATE,
        r"arrival\s*(?:is|:|-|on)\s*(?:the\s+)?" + _DATE,
    ]
    _CHECKOUT_PATS = [
        r"check[- ]?out\s*(?:date\s*)?(?:is|:|-|on|will be|would be)\s*(?:on\s+)?(?:the\s+)?" + _DATE,
        r"checking\s+out\s+(?:on\s+)?(?:the\s+)?" + _DATE,
        r"departure\s*(?:is|:|-|on)\s*(?:the\s+)?" + _DATE,
    ]

    def _first_match(text, patterns):
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                raw = m.group(1).strip().rstrip("., ")
                if len(raw) >= 4:
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

GREETING = "Thank you for calling Lotus Sutra Goa. This is Aria — how may I assist you today?"

# Pre-cached greeting audio (generated at startup to eliminate first-call TTS latency)
_GREETING_AUDIO_EN: bytes | None = None

@app.on_event("startup")
async def _prewarm():
    global _GREETING_AUDIO_EN
    try:
        _GREETING_AUDIO_EN = await text_to_mulaw(GREETING, "en")
        log.info(f"[PREWARM] Greeting cached: {len(_GREETING_AUDIO_EN)}b")
    except Exception as e:
        log.warning(f"[PREWARM] Greeting cache failed: {e}")

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
    asyncio.create_task(process_queue())

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
    asyncio.create_task(process_queue())

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
    _availability_done = False       # fire only once per call
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
        nonlocal _available_rooms, _availability_done
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

                # Trigger Djubo availability check once both dates are confirmed
                if not _availability_done:
                    checkin_iso, checkout_iso = _extract_iso_dates(conversation_history)
                    if checkin_iso and checkout_iso:
                        _availability_done = True
                        log.info(f"[DJUBO] Triggering availability: {checkin_iso} → {checkout_iso}")
                        try:
                            _available_rooms = await get_available_room_names(checkin_iso, checkout_iso)
                        except Exception as _e:
                            log.warning(f"[DJUBO] availability check failed: {_e}")

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

                if not farewell_sent and _call_active:
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
    asyncio.create_task(process_queue())

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
        await stt.stop()
        log.info("[VB-WS] Disconnected")
        if conversation_history:
            _call_meta["ended_at"] = datetime.now(tz=None).isoformat()
            _call_meta["language"] = session_language
            asyncio.create_task(run_post_call_pipeline(conversation_history, _call_meta))


# ─── Health check ─────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "agent": "Lotus Sutra Goa — Aria", "telephony": TELEPHONY}


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
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False, log_level="info")
