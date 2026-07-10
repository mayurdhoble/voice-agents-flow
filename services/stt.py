import os
import json
import struct
import asyncio
import audioop
import logging
import httpx
import websockets

log = logging.getLogger("agent")

# Deepgram: used only for VAD / endpointing (detect when caller stops speaking)
DEEPGRAM_URL = (
    "wss://api.deepgram.com/v1/listen"
    "?model=nova-2-general"
    "&encoding=mulaw"
    "&sample_rate=8000"
    "&channels=1"
    "&endpointing=300"
    "&interim_results=true"
    "&utterance_end_ms=1000"
)

SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"

_LANG_MAP = {
    "hi": "hi", "mr": "mr", "te": "te", "ta": "ta",
    "kn": "kn", "bn": "bn", "gu": "gu", "en": "en",
    "pa": "en", "or": "en",
}


def _build_wav(pcm_bytes: bytes, sample_rate: int = 8000) -> bytes:
    n = len(pcm_bytes)
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + n, b"WAVE",
        b"fmt ", 16, 1, 1,
        sample_rate, sample_rate * 2,
        2, 16,
        b"data", n,
    ) + pcm_bytes


class DeepgramSTT:
    """
    Deepgram handles VAD/endpointing only.
    On UtteranceEnd (1000ms silence = full utterance), sends buffered audio
    to Sarvam STT (saarika:v2.5) for accurate multilingual transcription
    + automatic language detection.
    """

    def __init__(self, on_transcript):
        self.on_transcript = on_transcript
        self.dg_key = os.getenv("DEEPGRAM_API_KEY")
        self.sarvam_key = os.getenv("SARVAM_API_KEY")
        self.ws = None
        self._receiver_task = None
        self._audio_buffer = bytearray()

    async def start(self):
        headers = {"Authorization": f"Token {self.dg_key}"}
        self.ws = await websockets.connect(DEEPGRAM_URL, additional_headers=headers)
        self._receiver_task = asyncio.create_task(self._receive_loop())
        log.info("[STT] Ready (Deepgram VAD + Sarvam STT)")

    async def send_audio(self, audio_bytes: bytes):
        self._audio_buffer.extend(audio_bytes)
        # Sarvam STT limit = 30s. Cap buffer at 25s (200000 bytes @ 8kHz mulaw).
        # Keep the most recent audio — oldest speech is least relevant.
        if len(self._audio_buffer) > 200_000:
            self._audio_buffer = self._audio_buffer[-200_000:]
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
        log.info("[STT] Disconnected")

    async def _transcribe(self) -> tuple[str, str]:
        """Send buffered audio to Sarvam STT. Returns (transcript, lang)."""
        if len(self._audio_buffer) < 4000:   # < 0.5s of audio — skip noise
            self._audio_buffer.clear()
            return "", "en"

        buf = bytes(self._audio_buffer)
        self._audio_buffer.clear()

        try:
            pcm = audioop.ulaw2lin(buf, 2)
            wav = _build_wav(pcm)

            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    SARVAM_STT_URL,
                    headers={"api-subscription-key": self.sarvam_key},
                    files={"file": ("audio.wav", wav, "audio/wav")},
                    data={"model": "saarika:v2.5"},
                )
                if not resp.is_success:
                    log.warning(f"[STT] Sarvam {resp.status_code}: {resp.text[:200]}")
                    return "", "en"
                data = resp.json()

            transcript = data.get("transcript", "").strip()
            lang_full = data.get("language_code", "en-IN")
            lang = _LANG_MAP.get(lang_full.split("-")[0], "en")
            return transcript, lang

        except Exception as e:
            log.error(f"[STT] Sarvam error: {e}")
            return "", "en"

    async def _receive_loop(self):
        try:
            async for message in self.ws:
                data = json.loads(message)
                msg_type = data.get("type")

                if msg_type == "UtteranceEnd":
                    # Full utterance is in the buffer — transcribe once
                    if self._audio_buffer:
                        transcript, language = await self._transcribe()
                        if transcript:
                            log.info(f"[STT] [{language}] {transcript}")
                            await self.on_transcript(transcript, language)

        except websockets.exceptions.ConnectionClosed:
            log.info("[STT] Deepgram connection closed")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error(f"[STT] Error: {e}")
