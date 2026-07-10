import os
import sys
import json
import base64
import asyncio
import logging
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
    session_language = "en"  # tracks dominant non-English language this call
    farewell_sent = False     # prevent duplicate goodbyes from queued end-call utterances
    aria_speaking = False     # mute VAD while Aria is speaking to prevent echo triggers

    _FAREWELL_WORDS = {
        "bye", "goodbye", "cut the call", "end the call", "disconnect",
        "समाप्त करा", "कॉल कट", "बंद करा", "कट करता", "कट करते",
        "कॉल काटता", "कॉल काटते", "call cut", "band karo",
    }

    def _is_farewell(text: str) -> bool:
        t = text.strip().lower()
        return any(w in t for w in _FAREWELL_WORDS)

    async def process_queue():
        nonlocal session_language, farewell_sent, aria_speaking
        while True:
            text, stt_language = await transcript_queue.get()
            try:
                # If more items are already waiting, drain stale ones — keep only the latest
                # This prevents the LLM from answering old fragments after the user has moved on
                while not transcript_queue.empty():
                    stale_text, stale_lang = transcript_queue.get_nowait()
                    transcript_queue.task_done()
                    log.info(f"[AGENT] Dropped stale transcript (queue backed up): '{stale_text[:40]}'")
                    # Carry the language from the latest item
                    stt_language = stale_lang
                    text = stale_text

                # Skip duplicate goodbyes after farewell already spoken
                if farewell_sent and _is_farewell(text):
                    log.info(f"[AGENT] Skipping duplicate farewell: '{text}'")
                    continue

                if stt_language != "en":
                    session_language = stt_language
                speak_language = session_language

                conversation_history.append({"role": "user", "content": text})
                from services.tts import clean_for_tts
                reply = clean_for_tts(await generate_response(text, conversation_history, speak_language))
                log.info(f"[LLM] {reply}")
                conversation_history.append({"role": "assistant", "content": reply})

                if _is_farewell(text):
                    farewell_sent = True

                aria_speaking = True
                await speak(reply, speak_language)
                aria_speaking = False
            except Exception as e:
                log.error(f"[AGENT] Error: {e}")
                aria_speaking = False
            finally:
                transcript_queue.task_done()

    asyncio.create_task(process_queue())

    _NOISE = {"uh", "um", "hmm", "hm", "ah", "oh", "uh-huh", "mhm", "so", "pan", "mudko"}

    async def on_transcript(text: str, language: str = "en"):
        if aria_speaking:
            log.info(f"[STT] Ignoring transcript while Aria speaking: '{text[:40]}'")
            return
        cleaned = text.strip()
        if not cleaned or len(cleaned) < 3:
            return
        if cleaned.lower() in _NOISE:
            log.info(f"[STT] Skipping noise: '{cleaned}'")
            return
        await transcript_queue.put((cleaned, language))

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

    stt = SileroVADSTT(on_transcript=on_transcript)
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
