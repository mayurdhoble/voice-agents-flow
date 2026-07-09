import os
import json
import asyncio
import logging
import websockets

log = logging.getLogger("agent")

DEEPGRAM_URL = (
    "wss://api.deepgram.com/v1/listen"
    "?model=nova-2-general"
    "&encoding=mulaw"
    "&sample_rate=8000"
    "&channels=1"
    "&punctuate=true"
    "&smart_format=true"
    "&endpointing=300"
    "&interim_results=true"
    "&utterance_end_ms=1000"
)

# Deepgram/langdetect code → our internal language code
_LANG_MAP = {
    "hi": "hi", "mr": "mr", "te": "te", "ta": "ta",
    "kn": "kn", "bn": "bn", "gu": "gu", "en": "en",
}


def _detect_language(text: str) -> str:
    """Detect language from transcript text. Falls back to 'en' on any error."""
    try:
        from langdetect import detect
        code = detect(text)
        return _LANG_MAP.get(code, "en")
    except Exception:
        return "en"


class DeepgramSTT:
    """
    Streams mulaw audio from Twilio to Deepgram for real-time transcription.
    Runs langdetect on each final transcript for language detection.
    Calls on_transcript(text, language) when caller finishes speaking.
    """

    def __init__(self, on_transcript):
        self.on_transcript = on_transcript
        self.api_key = os.getenv("DEEPGRAM_API_KEY")
        self.ws = None
        self._receiver_task = None

    async def start(self):
        headers = {"Authorization": f"Token {self.api_key}"}
        self.ws = await websockets.connect(DEEPGRAM_URL, additional_headers=headers)
        self._receiver_task = asyncio.create_task(self._receive_loop())
        log.info("[STT] Deepgram connected")

    async def send_audio(self, audio_bytes: bytes):
        if self.ws:
            try:
                await self.ws.send(audio_bytes)
            except Exception:
                pass

    async def stop(self):
        try:
            if self.ws:
                await self.ws.send(json.dumps({"type": "CloseStream"}))
                await self.ws.close()
        except Exception:
            pass
        if self._receiver_task:
            self._receiver_task.cancel()
        log.info("[STT] Deepgram disconnected")

    async def _receive_loop(self):
        last_interim = ""
        last_sent = ""   # dedup: skip if same text sent already
        try:
            async for message in self.ws:
                data = json.loads(message)
                msg_type = data.get("type")

                if msg_type == "Results":
                    try:
                        transcript = data["channel"]["alternatives"][0]["transcript"]
                        is_final = data.get("is_final", False)
                        if transcript:
                            if is_final:
                                last_interim = ""
                                if transcript != last_sent:
                                    last_sent = transcript
                                    language = _detect_language(transcript)
                                    log.info(f"[STT] [{language}] {transcript}")
                                    await self.on_transcript(transcript, language)
                            else:
                                last_interim = transcript
                    except (KeyError, IndexError):
                        pass

                elif msg_type == "UtteranceEnd":
                    # Fallback: fires after utterance_end_ms silence when is_final didn't fire
                    if last_interim.strip() and last_interim != last_sent:
                        text = last_interim
                        last_interim = ""
                        last_sent = text
                        language = _detect_language(text)
                        log.info(f"[STT] (utterance_end) [{language}] {text}")
                        await self.on_transcript(text, language)

        except websockets.exceptions.ConnectionClosed:
            log.info("[STT] Deepgram connection closed")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error(f"[STT] Error: {e}")
