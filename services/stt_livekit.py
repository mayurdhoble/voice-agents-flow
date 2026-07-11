import os
import asyncio
import audioop
import struct
import logging
import httpx

from livekit import rtc
from livekit.plugins import silero
from livekit.agents.vad import VADEventType

log = logging.getLogger("agent")

SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"

_LANG_MAP = {
    "hi": "hi", "mr": "mr", "te": "te", "ta": "ta",
    "kn": "kn", "bn": "bn", "gu": "gu", "en": "en",
    "pa": "en", "or": "en",
}

SAMPLE_RATE = 8000

# Load Silero model once at import time — keeps it warm across calls and
# avoids the "inference is slower than realtime" cold-start on the first call.
_VAD = silero.VAD.load(
    min_silence_duration=0.3,
    min_speech_duration=0.15,
    prefix_padding_duration=0.1,
)


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


class SileroVADSTT:
    """
    Silero VAD (livekit-plugins-silero) for fast end-of-speech detection (~200ms).
    On END_OF_SPEECH, sends buffered mulaw audio to Sarvam STT for transcription.

    Replaces Deepgram WebSocket VAD which had a fixed 1000ms UtteranceEnd delay.
    No Deepgram API key needed — Silero runs locally.
    """

    def __init__(self, on_transcript, on_speech_start=None):
        self.on_transcript = on_transcript
        self.on_speech_start = on_speech_start
        self.sarvam_key = os.getenv("SARVAM_API_KEY")
        self._vad = _VAD  # reuse the module-level singleton
        self._vad_stream = None
        self._audio_buffer = bytearray()
        self._event_task = None
        self._frame_counter = 0   # feed every 2nd frame to Silero to halve CPU load

    async def start(self):
        self._vad_stream = self._vad.stream()
        self._event_task = asyncio.create_task(self._event_loop())
        # Pre-warm: feed silent frames so the first real-audio inference is fast
        silence = bytes(320)  # 20ms silent PCM16 at 8000 Hz
        for _ in range(8):
            self._vad_stream.push_frame(rtc.AudioFrame(
                data=silence, sample_rate=SAMPLE_RATE,
                num_channels=1, samples_per_channel=160,
            ))
        await asyncio.sleep(0.05)
        log.info("[STT] Ready (Silero VAD + Sarvam STT)")

    async def send_audio(self, mulaw_bytes: bytes):
        """Called for every Twilio media chunk (~20ms of mulaw audio)."""
        # Buffer for Sarvam STT
        self._audio_buffer.extend(mulaw_bytes)
        if len(self._audio_buffer) > 200_000:   # cap at 25s
            self._audio_buffer = self._audio_buffer[-200_000:]

        # Feed every 2nd frame to Silero to halve CPU load (still accurate — VAD works on 40ms windows)
        self._frame_counter += 1
        if self._frame_counter % 2 == 0:
            pcm16 = audioop.ulaw2lin(mulaw_bytes, 2)
            samples_per_channel = len(pcm16) // 2
            frame = rtc.AudioFrame(
                data=pcm16,
                sample_rate=SAMPLE_RATE,
                num_channels=1,
                samples_per_channel=samples_per_channel,
            )
            self._vad_stream.push_frame(frame)

    async def _event_loop(self):
        """Process Silero VAD events; transcribe on END_OF_SPEECH."""
        try:
            async for event in self._vad_stream:
                if event.type == VADEventType.START_OF_SPEECH:
                    log.info("[VAD] Speech started")
                    if self.on_speech_start:
                        asyncio.create_task(self.on_speech_start())

                elif event.type == VADEventType.END_OF_SPEECH:
                    log.info("[VAD] Speech ended — transcribing")
                    if self._audio_buffer:
                        asyncio.create_task(self._transcribe_and_notify())

        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error(f"[VAD] Error: {e}")

    async def _transcribe_and_notify(self):
        buf = bytes(self._audio_buffer)
        self._audio_buffer.clear()

        if len(buf) < 4000:   # < 0.5s — skip noise
            return

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
                    return
                data = resp.json()

            transcript = data.get("transcript", "").strip()
            lang_full = data.get("language_code", "en-IN")
            lang = _LANG_MAP.get(lang_full.split("-")[0], "en")

            if transcript:
                log.info(f"[STT] [{lang}] {transcript}")
                await self.on_transcript(transcript, lang)

        except Exception as e:
            log.error(f"[STT] Sarvam error: {e}")

    async def stop(self):
        if self._event_task:
            self._event_task.cancel()
        if self._vad_stream:
            await self._vad_stream.aclose()
        log.info("[STT] Disconnected")
