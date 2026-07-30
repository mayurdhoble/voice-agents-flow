"""
Gemini Live S2S session — V2 architecture.

One persistent WebSocket per call, three coroutines in asyncio.gather,
outer while-loop over inner async-for to handle turns without reconnecting.

Audio pipeline (V2):
  VoBiz mulaw 8kHz  →  3× gain  →  PCM 16kHz (stateful)  →  Gemini Live
  Gemini Live PCM 24kHz  →  PCM 8kHz (stateful)  →  mulaw 8kHz  →  VoBiz

Stateful resampling carries state across chunk boundaries — no click artifacts.
100ms batching (5 × 20ms chunks) gives Gemini VAD a real speech window.
"""
import os
import asyncio
import audioop
import logging
from google import genai
from google.genai import types

log = logging.getLogger("agent")

GEMINI_MODEL       = os.getenv("GEMINI_LIVE_MODEL", "gemini-3.1-flash-live-preview")
GEMINI_VOICE       = os.getenv("GEMINI_LIVE_VOICE", "Zephyr")
GEMINI_API_VERSION = os.getenv("GEMINI_API_VERSION", "v1alpha")
GEMINI_MAX_OUTPUT_TOKENS = int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "512") or "0")

CHUNK_BUFFER_SIZE = 5   # 5 × 20ms = 100ms per Gemini send — better VAD detection


class GeminiLiveSession:
    """
    One instance per call. Opens exactly one Gemini Live WebSocket and keeps it
    alive for the entire call via the outer while / inner async-for pattern from V2.
    No reconnect logic, no history replay, no state injection — Gemini holds context.
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

        self._client = genai.Client(
            api_key=os.getenv("GOOGLE_API_KEY"),
            http_options={"api_version": GEMINI_API_VERSION},
        )
        self._audio_in_q: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._audio_out_q: asyncio.Queue[bytes] = asyncio.Queue()
        self._main_task: asyncio.Task | None = None
        self._active = False
        self._session = None

        # Stateful resamplers — never reset mid-call, prevents chunk-boundary pops
        self._upsample_state = None    # 8kHz → 16kHz (caller → Gemini)
        self._downsample_state = None  # 24kHz → 8kHz (Gemini → caller)

    # ── Public API ────────────────────────────────────────────────────────────

    async def start(self, greeting_text: str | None = None):
        """Open the Gemini session and start the three coroutines."""
        self._active = True
        self._main_task = asyncio.create_task(
            self._run(greeting_text), name="gemini-live-main"
        )
        log.info(f"[GEMINI] Session starting — model={GEMINI_MODEL} voice={GEMINI_VOICE}")

    async def send_audio(self, mulaw_bytes: bytes):
        """Feed a VoBiz mulaw 8kHz chunk into the pipeline."""
        if self._active:
            await self._audio_in_q.put(mulaw_bytes)

    async def send_system_note(self, text: str, speak_now: bool = False):
        """Inject a silent context note or a spoken prompt into the live session.

        speak_now=False  — Gemini absorbs it without replying (use for pricing data, state)
        speak_now=True   — Gemini treats it as a user turn and responds aloud
        """
        if self._session:
            try:
                await self._session.send_client_content(
                    turns=types.Content(
                        role="user",
                        parts=[types.Part(text=f"[System: {text}]")],
                    ),
                    turn_complete=speak_now,
                )
                log.info(f"[GEMINI] Note injected (speak_now={speak_now}): {text[:80]}")
            except Exception as e:
                log.warning(f"[GEMINI] Note inject error: {e}")

    def clear_audio_queue(self):
        """Discard buffered outbound audio — call on barge-in so cleared VoBiz
        audio matches what was actually trimmed from the recording."""
        cleared = 0
        while not self._audio_out_q.empty():
            try:
                self._audio_out_q.get_nowait()
                cleared += 1
            except asyncio.QueueEmpty:
                break
        if cleared:
            log.info(f"[GEMINI] Cleared {cleared} buffered audio chunks (barge-in)")

    async def stop(self):
        """Shut down the session cleanly."""
        self._active = False
        await self._audio_in_q.put(None)   # unblock _send_loop
        if self._main_task and not self._main_task.done():
            self._main_task.cancel()
            try:
                await self._main_task
            except (asyncio.CancelledError, Exception):
                pass
        log.info("[GEMINI] Session stopped")

    # ── Internal ──────────────────────────────────────────────────────────────

    def _build_config(self) -> types.LiveConnectConfig:
        return types.LiveConnectConfig(
            system_instruction=self._system_prompt,
            generation_config=types.GenerationConfig(
                response_modalities=["AUDIO"],
                **({"max_output_tokens": GEMINI_MAX_OUTPUT_TOKENS}
                   if GEMINI_MAX_OUTPUT_TOKENS else {}),
            ),
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    disabled=False,
                    # HIGH start: catch speech onset fast, reducing latency
                    start_of_speech_sensitivity=types.StartSensitivity.START_SENSITIVITY_HIGH,
                    # LOW end: wait longer before cutting off — prevents premature turn-end
                    end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_LOW,
                    silence_duration_ms=int(os.getenv("GEMINI_VAD_SILENCE_MS", "800")),
                )
            ),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=GEMINI_VOICE
                    )
                ),
                language_code="en-IN",   # Indian English accent at voice layer — not prompt rules
            ),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
        )

    async def _run(self, greeting_text: str | None):
        """Open one Gemini session and run three coroutines for the entire call."""
        try:
            config = self._build_config()
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
                    log.info("[GEMINI] Greeting turn sent — Maya will speak it")
                else:
                    # Cached greeting already played — tell Gemini not to re-greet
                    await session.send_client_content(
                        turns=types.Content(
                            role="user",
                            parts=[types.Part(text=(
                                "[System] The greeting has already been played to the guest. "
                                "Do NOT say Namaste, do NOT greet or introduce yourself. "
                                "Wait for the guest to speak and respond directly to what they say."
                            ))],
                        ),
                        turn_complete=False,
                    )
                    log.info("[GEMINI] No-greet context sent (cached greeting played)")

                await asyncio.gather(
                    self._send_loop(session),
                    self._recv_loop(session),
                    self._flush_loop(),
                )

        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error(f"[GEMINI] Session error: {e}", exc_info=True)
        finally:
            self._session = None
            self._active = False

    async def _send_loop(self, session):
        """Read mulaw from queue, apply V2 audio pipeline, send 100ms batches to Gemini."""
        buf: list[bytes] = []
        try:
            while self._active:
                chunk = await self._audio_in_q.get()
                if chunk is None:
                    break

                # V2 pipeline: mulaw → PCM 8kHz → 3× gain boost → PCM 16kHz
                # Stateful ratecv keeps state across chunks — no boundary artifacts
                pcm_8k = audioop.ulaw2lin(chunk, 2)
                pcm_8k = audioop.mul(pcm_8k, 2, 3.0)
                pcm_16k, self._upsample_state = audioop.ratecv(
                    pcm_8k, 2, 1, 8000, 16000, self._upsample_state
                )

                buf.append(pcm_16k)
                if len(buf) >= CHUNK_BUFFER_SIZE:
                    combined = b"".join(buf)
                    buf.clear()
                    try:
                        await session.send_realtime_input(
                            audio=types.Blob(data=combined, mime_type="audio/pcm;rate=16000")
                        )
                    except Exception as e:
                        log.error(f"[GEMINI] send_realtime_input error: {e}")
                        self._active = False
                        break
        except asyncio.CancelledError:
            pass

    async def _recv_loop(self, session):
        """V2 pattern: outer while keeps session alive; inner async-for handles one turn.
        When the inner loop exits (turn complete), outer loop re-enters receive()."""
        try:
            while self._active:
                turn_had_response = False
                async for msg in session.receive():
                    if not self._active:
                        return

                    sc = msg.server_content
                    if not sc:
                        continue

                    turn_had_response = True

                    if sc.interrupted:
                        log.info("[GEMINI] Barge-in detected")
                        if self._on_interrupted:
                            asyncio.create_task(self._on_interrupted())

                    if sc.model_turn:
                        for part in sc.model_turn.parts:
                            if part.inline_data and part.inline_data.data:
                                # Stateful downsample 24kHz → 8kHz → mulaw
                                pcm_8k, self._downsample_state = audioop.ratecv(
                                    part.inline_data.data, 2, 1, 24000, 8000,
                                    self._downsample_state
                                )
                                mulaw = audioop.lin2ulaw(pcm_8k, 2)
                                await self._audio_out_q.put(mulaw)
                            # part.text is NOT used — output_transcription is the
                            # primary text source in AUDIO mode. Using both would
                            # double every sentence in _pending_agent_text, causing
                            # false farewell detection and garbled conversation history.

                    # Input transcription — what the guest said
                    if hasattr(sc, "input_transcription") and sc.input_transcription:
                        t = getattr(sc.input_transcription, "text", "") or ""
                        if t.strip():
                            log.info(f"[GEMINI USER] {t.strip()}")
                            if self._on_user_transcript:
                                asyncio.create_task(self._on_user_transcript(t.strip()))

                    # Output transcription — what Maya said (primary text source in AUDIO mode)
                    if hasattr(sc, "output_transcription") and sc.output_transcription:
                        t = getattr(sc.output_transcription, "text", "") or ""
                        if t.strip():
                            log.info(f"[GEMINI AGENT] {t.strip()}")
                            if self._on_agent_text:
                                asyncio.create_task(self._on_agent_text(t.strip()))

                # Inner async-for exhausted — turn complete
                if turn_had_response:
                    log.info("[GEMINI] Turn complete — waiting for guest input")
                else:
                    log.info("[GEMINI] Session closed by server")
                    break

        except asyncio.CancelledError:
            pass
        except Exception as e:
            if "1000" in str(e):
                log.debug("[GEMINI] Session closed normally (1000)")
            else:
                log.error(f"[GEMINI] Recv error: {e}", exc_info=True)
        finally:
            self._active = False

    async def _flush_loop(self):
        """Drain outbound audio queue and deliver to caller."""
        while self._active or not self._audio_out_q.empty():
            try:
                mulaw = await asyncio.wait_for(self._audio_out_q.get(), timeout=0.5)
                await self._on_audio_out(mulaw)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                log.warning(f"[GEMINI] Flush error: {e}")
                break
