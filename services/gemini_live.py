"""
Gemini Live S2S (speech-to-speech) session wrapper.

Replaces the entire STT → LLM → TTS pipeline with a single bidirectional
WebSocket to Google Gemini Live.  Audio flow:
  VoBiz mulaw 8kHz  →  PCM 16kHz  →  Gemini Live
  Gemini Live  →  PCM 24kHz  →  mulaw 8kHz  →  VoBiz
"""
import os
import asyncio
import audioop
import logging
from google import genai
from google.genai import types

log = logging.getLogger("agent")

GEMINI_MODEL = os.getenv("GEMINI_LIVE_MODEL", "gemini-2.0-flash-live-001")
GEMINI_VOICE = os.getenv("GEMINI_LIVE_VOICE", "Aoede")


def _mulaw8k_to_pcm16k(mulaw_bytes: bytes) -> bytes:
    pcm_8k = audioop.ulaw2lin(mulaw_bytes, 2)
    pcm_16k, _ = audioop.ratecv(pcm_8k, 2, 1, 8000, 16000, None)
    return pcm_16k


def _pcm24k_to_mulaw8k(pcm_24k: bytes) -> bytes:
    pcm_8k, _ = audioop.ratecv(pcm_24k, 2, 1, 24000, 8000, None)
    return audioop.lin2ulaw(pcm_8k, 2)


class GeminiLiveSession:
    """
    Manages a single Gemini Live call session.

    Callbacks (all async):
      on_audio_out(mulaw_bytes)   — called for every audio chunk from Gemini
      on_interrupted()            — called when Gemini detects barge-in
      on_user_transcript(text)    — called with each user speech transcript
      on_agent_text(text)         — called with each agent text chunk
    """

    def __init__(
        self,
        system_prompt: str,
        on_audio_out,
        on_interrupted=None,
        on_user_transcript=None,
        on_agent_text=None,
    ):
        self._system_prompt = system_prompt
        self._on_audio_out = on_audio_out
        self._on_interrupted = on_interrupted
        self._on_user_transcript = on_user_transcript
        self._on_agent_text = on_agent_text

        self._client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
        self._audio_in_q: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._main_task: asyncio.Task | None = None
        self._active = False
        self._session = None

    # ── Public API ────────────────────────────────────────────────────────────

    async def start(self, greeting_text: str | None = None):
        """Connect to Gemini Live and start send/recv loops."""
        self._active = True
        self._main_task = asyncio.create_task(
            self._run(greeting_text), name="gemini-live-main"
        )
        log.info(f"[GEMINI] Session starting — model={GEMINI_MODEL} voice={GEMINI_VOICE}")

    async def send_audio(self, mulaw_bytes: bytes):
        """Feed a VoBiz mulaw 8kHz audio chunk into Gemini."""
        if self._active:
            await self._audio_in_q.put(mulaw_bytes)

    async def stop(self):
        """Gracefully shut down the Gemini session."""
        self._active = False
        await self._audio_in_q.put(None)   # unblock the send loop
        if self._main_task and not self._main_task.done():
            self._main_task.cancel()
            try:
                await self._main_task
            except (asyncio.CancelledError, Exception):
                pass
        log.info("[GEMINI] Session stopped")

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _run(self, greeting_text: str | None):
        """Holds the async-with block open; runs send + recv concurrently."""
        config = types.LiveConnectConfig(
            system_instruction=self._system_prompt,
            generation_config=types.GenerationConfig(
                response_modalities=["AUDIO"],
            ),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=GEMINI_VOICE
                    )
                )
            ),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
        )

        try:
            async with self._client.aio.live.connect(
                model=GEMINI_MODEL, config=config
            ) as session:
                self._session = session
                log.info("[GEMINI] Connected")

                if greeting_text:
                    await session.send_client_content(
                        turns=types.Content(
                            role="user",
                            parts=[types.Part(text=greeting_text)],
                        ),
                        turn_complete=True,
                    )

                send_task = asyncio.create_task(self._send_loop(session))
                recv_task = asyncio.create_task(self._recv_loop(session))

                # Wait until either loop finishes (usually recv on call end)
                done, pending = await asyncio.wait(
                    [send_task, recv_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for t in pending:
                    t.cancel()
                    try:
                        await t
                    except (asyncio.CancelledError, Exception):
                        pass

        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error(f"[GEMINI] Session error: {e}")
        finally:
            self._session = None

    async def _send_loop(self, session):
        """Read mulaw chunks from queue, convert to PCM 16kHz, send to Gemini."""
        try:
            while self._active:
                chunk = await self._audio_in_q.get()
                if chunk is None:
                    break
                pcm16k = _mulaw8k_to_pcm16k(chunk)
                await session.send_realtime_input(
                    audio=types.Blob(data=pcm16k, mime_type="audio/pcm;rate=16000")
                )
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error(f"[GEMINI] Send error: {e}")

    async def _recv_loop(self, session):
        """Receive from Gemini; route audio out, transcripts, and interrupts."""
        try:
            async for msg in session.receive():
                if not self._active:
                    break

                sc = msg.server_content
                if not sc:
                    continue

                # Barge-in: guest spoke over the agent
                if sc.interrupted:
                    log.info("[GEMINI] Barge-in detected")
                    if self._on_interrupted:
                        asyncio.create_task(self._on_interrupted())

                # Audio + text from model turn
                if sc.model_turn:
                    for part in sc.model_turn.parts:
                        if part.inline_data and part.inline_data.data:
                            mulaw = _pcm24k_to_mulaw8k(part.inline_data.data)
                            await self._on_audio_out(mulaw)
                        if part.text and self._on_agent_text:
                            asyncio.create_task(self._on_agent_text(part.text))

                if sc.turn_complete:
                    log.info("[GEMINI] Agent turn complete")

                # Input audio transcript (what the user said)
                if hasattr(sc, "input_transcription") and sc.input_transcription:
                    t = getattr(sc.input_transcription, "text", "") or ""
                    if t.strip() and self._on_user_transcript:
                        asyncio.create_task(self._on_user_transcript(t.strip()))

                # Output audio transcript (what the agent said)
                if hasattr(sc, "output_transcription") and sc.output_transcription:
                    t = getattr(sc.output_transcription, "text", "") or ""
                    if t.strip() and self._on_agent_text:
                        asyncio.create_task(self._on_agent_text(t.strip()))

        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error(f"[GEMINI] Recv error: {e}")
