import os
import sys
import json
import base64
import asyncio
import logging
import time
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import Response
import uvicorn

from services.stt_livekit import SileroVADSTT
from services.llm import generate_response
from services.tts import text_to_mulaw

# File-based logger so logs appear even when stdout is buffered
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

PUBLIC_URL = os.getenv("PUBLIC_URL", "")


# ─── 1. Twilio Webhook — incoming call ────────────────────────────────────────

@app.api_route("/incoming-call", methods=["GET", "POST"])
async def incoming_call(request: Request):
    log.info("[WEBHOOK] /incoming-call hit")
    ws_url = PUBLIC_URL.replace("https://", "wss://").replace("http://", "ws://")
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{ws_url}/media-stream"/>
    </Connect>
</Response>"""
    log.info(f"[WEBHOOK] Returning TwiML with stream URL: {ws_url}/media-stream")
    return Response(content=twiml, media_type="application/xml")


# ─── 2. WebSocket — real-time audio bridge ────────────────────────────────────

@app.websocket("/media-stream")
async def media_stream(websocket: WebSocket):
    await websocket.accept()
    log.info("[WS] Twilio connected")

    stream_sid = None
    conversation_history = []
    transcript_queue = asyncio.Queue()
    session_language = "en"  # tracks dominant language this call
    farewell_sent = False     # prevent duplicate goodbyes from queued end-call utterances
    aria_speaking = False     # mute VAD while Aria is speaking to prevent echo triggers
    _silence_task = None      # re-prompt timer when caller goes silent
    _call_active = True       # set False in finally to block post-call timer
    _english_turn_count = 0   # consecutive English turns — used to flip back from non-English
    _non_english_turn_count = 0  # consecutive non-English turns — require 2 to switch away from English
    _last_reply_generated_at = 0.0  # monotonic time when last LLM reply was produced

    # Phrases that explicitly request a language switch — override tracking immediately
    _EXPLICIT_LANG_REQUESTS = {
        "en": [
            "speak in english", "speak english", "english only", "talk in english",
            "reply in english", "can you speak english", "switch to english",
            "in english please", "english mein bolo", "english me bolo",
        ],
        "hi": [
            "hindi mein bolo", "hindi me bolo", "speak in hindi", "talk in hindi",
            "hindi boliye", "hindi bol", "switch to hindi",
        ],
        "mr": [
            "marathi madhe bola", "marathi mein bolo", "speak in marathi",
            "talk in marathi", "marathi bolte", "marathi me bolo",
        ],
    }

    def _detect_explicit_lang_request(text: str):
        t = text.lower().strip()
        for lang, phrases in _EXPLICIT_LANG_REQUESTS.items():
            for phrase in phrases:
                if phrase in t:
                    return lang
        return None

    _FAREWELL_WORDS = {
        "bye", "goodbye", "cut the call", "end the call", "end it", "end the call",
        "wrap up", "that's all", "thats all", "i want to end", "want to end",
        "disconnect", "call cut", "band karo", "rakh do", "rakho",
        "समाप्त करा", "कॉल कट", "बंद करा", "कट करता", "कट करते",
        "कॉल काटता", "कॉल काटते", "बंद कर", "रखो", "रख दो",
        "बस हो गया", "बस इतना", "धन्यवाद बस",
        "नाही लागत", "बस एवढं", "ठीक आहे बस",
    }

    def _is_farewell(text: str) -> bool:
        t = text.strip().lower()
        return any(w in t for w in _FAREWELL_WORDS)

    _SILENCE_REPROMPTS = {
        "en": ("Are you still there?", "No problem — feel free to call us back anytime. Goodbye!"),
        "hi": ("क्या आप अभी भी लाइन पर हैं?", "ठीक है, जब चाहें कॉल करें। धन्यवाद!"),
        "mr": ("तुम्ही अजून लाइनवर आहात का?", "ठीक आहे, जेव्हा हवं तेव्हा कॉल करा. धन्यवाद!"),
        "te": ("మీరు ఇంకా లైన్‌లో ఉన్నారా?", "సరే, ఎప్పుడైనా కాల్ చేయండి. ధన్యవాదాలు!"),
        "ta": ("நீங்கள் இன்னும் இணைந்திருக்கிறீர்களா?", "சரி, எப்போது வேண்டுமானாலும் அழைக்கலாம். நன்றி!"),
    }

    async def _silence_reprompt(attempt: int):
        await asyncio.sleep(20)
        if farewell_sent or aria_speaking or not _call_active:
            return
        lang = session_language
        prompts = _SILENCE_REPROMPTS.get(lang, _SILENCE_REPROMPTS["en"])
        if attempt == 1:
            msg = prompts[0]
            log.info(f"[AGENT] Silence timeout — re-prompting (attempt 1)")
            await speak(msg, lang)
            # Start second timer — if still silent, say goodbye
            nonlocal _silence_task
            _silence_task = asyncio.create_task(_silence_reprompt(2))
        else:
            msg = prompts[1]
            log.info(f"[AGENT] Silence timeout — saying goodbye")
            await speak(msg, lang)

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

    async def process_queue():
        nonlocal session_language, farewell_sent, aria_speaking, _english_turn_count, _non_english_turn_count, _last_reply_generated_at
        while True:
            text, stt_language, queued_at = await transcript_queue.get()
            try:
                # If more items are already waiting, drain stale ones — keep only the latest
                while not transcript_queue.empty():
                    stale_text, stale_lang, stale_at = transcript_queue.get_nowait()
                    transcript_queue.task_done()
                    log.info(f"[AGENT] Dropped stale transcript (queue backed up): '{stale_text[:40]}'")
                    stt_language = stale_lang
                    text = stale_text
                    queued_at = stale_at

                # Drop short trailing fragments that arrived before the last LLM reply was generated
                # e.g. "That's all", "okay" appended by user right after their main sentence
                short_fragment = len(text.split()) <= 2 and not _is_farewell(text)
                if short_fragment and queued_at < _last_reply_generated_at:
                    log.info(f"[AGENT] Dropping pre-reply short fragment: '{text}'")
                    continue

                # Skip duplicate goodbyes after farewell already spoken
                if farewell_sent and _is_farewell(text):
                    log.info(f"[AGENT] Skipping duplicate farewell: '{text}'")
                    continue

                # Bidirectional language tracking with explicit override detection
                # 1. Explicit language request ("speak in English") overrides immediately
                # 2. Non-English → requires 2 consecutive turns to switch away from English (prevents single noise words from flipping language)
                # 3. English → requires 2 consecutive turns to flip back from non-English
                explicit_lang = _detect_explicit_lang_request(text)
                if explicit_lang:
                    session_language = explicit_lang
                    _english_turn_count = 10 if explicit_lang == "en" else 0
                    _non_english_turn_count = 0 if explicit_lang == "en" else 10
                    log.info(f"[LANG] Explicit language override → {explicit_lang}")
                elif stt_language != "en":
                    _english_turn_count = 0
                    _non_english_turn_count += 1
                    if _non_english_turn_count >= 2:
                        session_language = stt_language
                else:
                    _non_english_turn_count = 0
                    _english_turn_count += 1
                    if _english_turn_count >= 2:
                        session_language = "en"
                speak_language = session_language

                conversation_history.append({"role": "user", "content": text})
                from services.tts import clean_for_tts
                reply = clean_for_tts(await generate_response(text, conversation_history, speak_language))
                _last_reply_generated_at = time.monotonic()
                log.info(f"[LLM] {reply}")
                conversation_history.append({"role": "assistant", "content": reply})

                if _is_farewell(text):
                    farewell_sent = True

                # If LLM replied mostly in English (>70% ASCII letters), use English TTS
                # This prevents English text being read by Marathi/Hindi voice
                ascii_chars = sum(1 for c in reply if c.isascii() and c.isalpha())
                total_chars = sum(1 for c in reply if c.isalpha())
                if total_chars > 0 and ascii_chars / total_chars > 0.7:
                    tts_language = "en"
                else:
                    tts_language = speak_language

                aria_speaking = True
                await speak(reply, tts_language)
                aria_speaking = False
                # Start silence timer — only if call still active and farewell not sent
                if not farewell_sent and _call_active:
                    _reset_silence_timer()
            except Exception as e:
                log.error(f"[AGENT] Error: {e}")
                aria_speaking = False
            finally:
                transcript_queue.task_done()

    asyncio.create_task(process_queue())

    _NOISE = {"uh", "um", "hmm", "hm", "ah", "oh", "uh-huh", "mhm", "so", "pan", "mudko",
              "ya", "ya edit", "या एडिट", "na", "na sar",
              # Common single-word greetings that appear as background noise / barge-in echo
              "hello", "hi", "hey", "namaste", "नमस्ते", "नमस्कार", "নমস্কার", "vanakkam", "haan"}

    async def on_transcript(text: str, language: str = "en"):
        if aria_speaking:
            log.info(f"[STT] Ignoring transcript while Aria speaking: '{text[:40]}'")
            return
        cleaned = text.strip()
        if not cleaned or len(cleaned) < 3:
            return
        if cleaned.lower().rstrip("।.!?,") in _NOISE:
            log.info(f"[STT] Skipping noise: '{cleaned}'")
            return
        # Drop single-word garbled transcripts under 5 chars (noise like "ya", "na sar")
        words = cleaned.split()
        if len(words) == 1 and len(cleaned) < 5:
            log.info(f"[STT] Skipping single short word: '{cleaned}'")
            return
        _cancel_silence_timer()
        await transcript_queue.put((cleaned, language, time.monotonic()))

    async def speak(text: str, language: str = "en"):
        if not stream_sid:
            log.warning("[SPEAK] No stream_sid yet, cannot send audio")
            return
        try:
            log.info(f"[SPEAK] [{language}] {text[:60]}")
            mulaw_audio = await text_to_mulaw(text, language)
            audio_b64 = base64.b64encode(mulaw_audio).decode("utf-8")
            await websocket.send_json({
                "event": "media",
                "streamSid": stream_sid,
                "media": {"payload": audio_b64}
            })
            log.info(f"[SPEAK] Sent {len(mulaw_audio)} bytes to caller")
        except Exception as e:
            log.error(f"[SPEAK] Error: {e}")

    stt = SileroVADSTT(on_transcript=on_transcript, on_speech_start=on_speech_start)
    await stt.start()

    try:
        async for message in websocket.iter_text():
            data = json.loads(message)
            event = data.get("event")

            if event == "start":
                stream_sid = data["start"]["streamSid"]
                log.info(f"[WS] Stream started: {stream_sid}")
                # Send greeting NOW that stream_sid is set
                asyncio.create_task(speak(
                    "Grand Orchid Hotel, Aria speaking — how can I help you today?"
                ))

            elif event == "media":
                audio_bytes = base64.b64decode(data["media"]["payload"])
                await stt.send_audio(audio_bytes)

            elif event == "stop":
                log.info("[WS] Stream stopped")
                break

    except Exception as e:
        log.error(f"[WS] Connection error: {e}")
    finally:
        _call_active = False
        _cancel_silence_timer()
        await stt.stop()
        log.info("[WS] Twilio disconnected")


# ─── Health check ─────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "agent": "Hotel Voice Agent"}


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    log.info(f"Starting Hotel Voice Agent on port {port}")
    log.info(f"Twilio webhook URL: {PUBLIC_URL}/incoming-call")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False, log_level="info")
