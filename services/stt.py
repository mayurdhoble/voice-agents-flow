import os
import json
import struct
import asyncio
import audioop
import httpx
import websockets

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

# Sarvam returns e.g. "hi-IN" — strip region to get our internal code
_LANG_MAP = {
    "hi": "hi", "mr": "mr", "te": "te", "ta": "ta",
    "kn": "kn", "bn": "bn", "gu": "gu", "en": "en",
    "pa": "en", "or": "en",
}


def _build_wav(pcm_bytes: bytes, sample_rate: int = 8000) -> bytes:
    """Wrap raw PCM16 mono bytes in a minimal WAV container."""
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
    Streams mulaw audio to Deepgram for VAD/endpointing only.
    On each speech endpoint, sends buffered audio to Sarvam STT for
    proper multilingual transcription + language detection.
    Calls on_transcript(text, language) with the result.
    """

    def __init__(self, on_transcript):
        self.on_transcript = on_transcript
        self.api_key = os.getenv("DEEPGRAM_API_KEY")
        self.sarvam_key = os.getenv("SARVAM_API_KEY")
        self.ws = None
        self._receiver_task = None
        self._audio_buffer = bytearray()

    async def start(self):
        headers = {"Authorization": f"Token {self.api_key}"}
        self.ws = await websockets.connect(DEEPGRAM_URL, additional_headers=headers)
        self._receiver_task = asyncio.create_task(self._receive_loop())
        print("[STT] Deepgram connected (endpointing) + Sarvam STT (transcription)")

    async def send_audio(self, audio_bytes: bytes):
        self._audio_buffer.extend(audio_bytes)  # buffer for Sarvam
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
        print("[STT] Disconnected")

    async def _transcribe_buffer(self) -> tuple[str, str]:
        """
        Convert buffered mulaw → WAV → POST to Sarvam STT.
        Returns (transcript, language_code). Buffer is cleared on entry.
        """
        if not self._audio_buffer:
            return "", "en"

        buf = bytes(self._audio_buffer)
        self._audio_buffer.clear()  # clear immediately so UtteranceEnd won't double-fire

        if not self.sarvam_key:
            return "", "en"

        try:
            pcm = audioop.ulaw2lin(buf, 2)
            wav = _build_wav(pcm)

            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    SARVAM_STT_URL,
                    headers={"api-subscription-key": self.sarvam_key},
                    files={"file": ("audio.wav", wav, "audio/wav")},
                    data={"model": "saarika:v2", "language_code": "unknown"},
                )
                resp.raise_for_status()
                data = resp.json()

            transcript = data.get("transcript", "").strip()
            lang_full = data.get("language_code", "en-IN")   # e.g. "hi-IN"
            lang = _LANG_MAP.get(lang_full.split("-")[0], "en")
            return transcript, lang

        except Exception as e:
            print(f"[STT] Sarvam error: {e}")
            return "", "en"

    async def _receive_loop(self):
        try:
            async for message in self.ws:
                data = json.loads(message)
                msg_type = data.get("type")

                if msg_type == "Results":
                    # speech_final=True means VAD detected end of speech (endpointing fired)
                    speech_final = data.get("speech_final", False)
                    if speech_final and self._audio_buffer:
                        transcript, language = await self._transcribe_buffer()
                        if transcript:
                            print(f"[STT] [{language}] {transcript}")
                            await self.on_transcript(transcript, language)

                elif msg_type == "UtteranceEnd":
                    # Fallback: fires after utterance_end_ms of silence.
                    # Buffer is empty if speech_final already handled it.
                    if self._audio_buffer:
                        transcript, language = await self._transcribe_buffer()
                        if transcript:
                            print(f"[STT] (utterance_end) [{language}] {transcript}")
                            await self.on_transcript(transcript, language)

        except websockets.exceptions.ConnectionClosed:
            print("[STT] Deepgram connection closed")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[STT] Error: {e}")
