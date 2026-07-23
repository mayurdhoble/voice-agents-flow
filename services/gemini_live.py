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

# Use the model configured in the environment. gemini-3.1-flash-live-preview is the
# Live model available on this account (gemini-2.0-flash-live-001 is NOT available on
# the v1alpha API here — it returns 1008 not-found).
GEMINI_MODEL = os.getenv("GEMINI_LIVE_MODEL", "gemini-3.1-flash-live-preview")
GEMINI_VOICE = os.getenv("GEMINI_LIVE_VOICE", "Zephyr")


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
        on_reconnect=None,
    ):
        self._system_prompt = system_prompt
        self._on_audio_out = on_audio_out
        self._on_interrupted = on_interrupted
        self._on_user_transcript = on_user_transcript
        self._on_agent_text = on_agent_text
        self._on_reconnect = on_reconnect

        self._client = genai.Client(
            api_key=os.getenv("GOOGLE_API_KEY"),
            http_options={"api_version": "v1alpha"},
        )
        self._audio_in_q: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._main_task: asyncio.Task | None = None
        self._active = False
        self._session = None

        # Conversation history for reconnect continuity
        self._history: list[types.Content] = []
        self._pending_user: list[str] = []
        self._pending_agent: list[str] = []

        # Barge-in tracking
        self._barge_in_pending = False   # True after sc.interrupted, until next agent turn
        self._agent_responding = False   # True while Gemini is generating a response
        self._nudge_task: asyncio.Task | None = None

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

    async def send_activity_start(self):
        """Signal that the user started speaking (manual VAD mode)."""
        if self._session:
            try:
                await self._session.send_realtime_input(
                    activity_start=types.ActivityStart()
                )
                log.info("[GEMINI] ActivityStart sent")
            except Exception as e:
                log.warning(f"[GEMINI] ActivityStart error: {e}")
        else:
            log.warning("[GEMINI] ActivityStart skipped — no session")

    async def send_activity_end(self):
        """Signal that the user stopped speaking (manual VAD mode)."""
        if self._session:
            try:
                await self._session.send_realtime_input(
                    activity_end=types.ActivityEnd()
                )
                log.info("[GEMINI] ActivityEnd sent")
                # After a barge-in, Gemini sometimes doesn't respond — nudge it
                if self._barge_in_pending:
                    if self._nudge_task and not self._nudge_task.done():
                        self._nudge_task.cancel()
                    self._nudge_task = asyncio.create_task(self._nudge_if_silent(2.0))
            except Exception as e:
                log.warning(f"[GEMINI] ActivityEnd error: {e}")
        else:
            log.warning("[GEMINI] ActivityEnd skipped — no session")

    def inject_agent_turn(self, text: str):
        """Pre-populate history with an agent message (e.g. pre-cached greeting)."""
        self._history.append(types.Content(
            role="model",
            parts=[types.Part(text=text)],
        ))

    async def send_system_note(self, text: str):
        """Inject a silent system note — Gemini absorbs it without triggering a response."""
        if self._session:
            try:
                await self._session.send_client_content(
                    turns=types.Content(
                        role="user",
                        parts=[types.Part(text=f"[System: {text}]")],
                    ),
                    turn_complete=False,
                )
                log.info(f"[GEMINI] Note injected: {text[:80]}")
            except Exception as e:
                log.warning(f"[GEMINI] Note inject error: {e}")
        else:
            log.warning("[GEMINI] Note inject skipped — no session")

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

    async def _reopen_mic(self):
        """Re-send ActivityStart after barge-in so Gemini captures the user's actual speech."""
        await asyncio.sleep(0.05)   # let the interrupt state settle first
        if self._session and self._active:
            try:
                await self._session.send_realtime_input(activity_start=types.ActivityStart())
                log.info("[GEMINI] ActivityStart re-sent after barge-in")
            except Exception as e:
                log.warning(f"[GEMINI] Reopen mic error: {e}")

    async def _nudge_if_silent(self, delay: float):
        """After a barge-in, if Gemini hasn't started responding, send a text kick."""
        await asyncio.sleep(delay)
        if not self._active or not self._session or not self._barge_in_pending:
            return
        if self._agent_responding:
            return
        try:
            await self._session.send_client_content(
                turns=types.Content(
                    role="user",
                    parts=[types.Part(text="[System: please respond to the guest now]")],
                ),
                turn_complete=True,
            )
            log.info("[GEMINI] Nudge sent — Gemini was silent after barge-in")
        except Exception as e:
            log.warning(f"[GEMINI] Nudge error: {e}")

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _run(self, greeting_text: str | None):
        """Reconnect loop — restarts the Gemini session if it drops mid-call."""
        config = types.LiveConnectConfig(
            system_instruction=self._system_prompt,
            generation_config=types.GenerationConfig(
                response_modalities=["AUDIO"],
            ),
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    disabled=True
                )
            ),
            # ONE pinned voice for the whole call (no language_code). Pinning the
            # voice_name guarantees every session — including every reconnect — uses
            # the SAME voice, so it always sounds like one person start to end.
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

        first_connect = True
        while self._active:
            try:
                async with self._client.aio.live.connect(
                    model=GEMINI_MODEL, config=config
                ) as session:
                    self._session = session
                    reconnect_num = 0 if first_connect else getattr(self, "_reconnect_count", 0)
                    log.info(f"[GEMINI] Connected (reconnect #{reconnect_num})")

                    # On first connect: send greeting as a user text turn
                    if first_connect and greeting_text:
                        await session.send_client_content(
                            turns=types.Content(
                                role="user",
                                parts=[types.Part(text=greeting_text)],
                            ),
                            turn_complete=True,
                        )
                        log.info("[GEMINI] Greeting turn sent — Maya will speak it")
                        # Do NOT send ActivityStart here — that signals "guest is speaking"
                        # and suppresses the greeting. The VAD sends ActivityStart when the
                        # guest actually talks.

                    elif not first_connect and self._history:
                        # Compress history into a single context note.
                        lines = []
                        for turn in self._history:
                            role = "Guest" if turn.role == "user" else "Maya"
                            text = " ".join(p.text for p in turn.parts if p.text)
                            if text.strip():
                                lines.append(f"{role}: {text.strip()}")

                        last_role = self._history[-1].role if self._history else None

                        if last_role == "user":
                            # Guest spoke last — respond now (don't wait for more speech)
                            ctx = (
                                "[System: Brief reconnect. Conversation so far:]\n"
                                + "\n".join(lines)
                                + "\n[System: The guest just spoke. Respond now.]"
                            )
                            await session.send_client_content(
                                turns=types.Content(
                                    role="user", parts=[types.Part(text=ctx)]
                                ),
                                turn_complete=True,
                            )
                            log.info(f"[GEMINI] Context note sent ({len(lines)} turns, guest spoke last — responding)")
                        else:
                            # Maya spoke last — wait for guest
                            ctx = (
                                "[System: Brief reconnect. Conversation so far:]\n"
                                + "\n".join(lines)
                                + "\n[System: Wait for the guest to speak next.]"
                            )
                            await session.send_client_content(
                                turns=types.Content(
                                    role="user", parts=[types.Part(text=ctx)]
                                ),
                                turn_complete=False,
                            )
                            log.info(f"[GEMINI] Context note sent ({len(lines)} turns, waiting for guest)")

                    if not first_connect and self._on_reconnect:
                        asyncio.create_task(self._on_reconnect())

                    first_connect = False

                    send_task = asyncio.create_task(self._send_loop(session))
                    recv_task = asyncio.create_task(self._recv_loop(session))

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

                    if self._active:
                        self._reconnect_count = getattr(self, "_reconnect_count", 0) + 1
                        log.warning(
                            f"[GEMINI] Session ended unexpectedly — reconnecting "
                            f"(attempt {self._reconnect_count})…"
                        )
                        await asyncio.sleep(0.3)

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"[GEMINI] Session error: {e}", exc_info=True)
                if self._active:
                    await asyncio.sleep(1)

        self._session = None

    async def _send_loop(self, session):
        """Read mulaw chunks from queue, convert to PCM 16kHz, send to Gemini."""
        _chunk_count = 0
        try:
            while self._active:
                chunk = await self._audio_in_q.get()
                if chunk is None:
                    break
                pcm16k = _mulaw8k_to_pcm16k(chunk)
                await session.send_realtime_input(
                    audio=types.Blob(data=pcm16k, mime_type="audio/pcm;rate=16000")
                )
                _chunk_count += 1
                if _chunk_count % 100 == 0:
                    log.info(f"[GEMINI] Audio sent: {_chunk_count} chunks ({_chunk_count * 20}ms)")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error(f"[GEMINI] Send error: {e}")

    async def _recv_loop(self, session):
        """Receive from Gemini; route audio out, transcripts, and interrupts."""
        _agent_buf: list[str] = []       # from model_turn.parts[].text (inline)
        _output_trans_buf: list[str] = []  # from output_transcription (audio-only mode)
        try:
            async for msg in session.receive():
                if not self._active:
                    break

                sc = msg.server_content
                if not sc:
                    log.debug(f"[GEMINI] Non-content message: {type(msg)}")
                    continue

                # Barge-in: guest spoke over the agent
                if sc.interrupted:
                    log.info("[GEMINI] Barge-in detected")
                    self._agent_responding = False
                    self._barge_in_pending = True
                    # Save whatever partial agent text we have (inline or transcription)
                    partial = " ".join(_agent_buf) if _agent_buf else " ".join(_output_trans_buf)
                    if partial:
                        self._history.append(types.Content(
                            role="model",
                            parts=[types.Part(text=partial)],
                        ))
                    _agent_buf.clear()
                    _output_trans_buf.clear()
                    if self._on_interrupted:
                        asyncio.create_task(self._on_interrupted())
                    # The ActivityStart that triggered barge-in is consumed by Gemini as a
                    # stop-signal. Re-send it so Gemini starts capturing the user's speech.
                    asyncio.create_task(self._reopen_mic())

                # Audio + inline text from model turn
                if sc.model_turn:
                    for part in sc.model_turn.parts:
                        if part.inline_data and part.inline_data.data:
                            self._agent_responding = True
                            self._barge_in_pending = False
                            if self._nudge_task and not self._nudge_task.done():
                                self._nudge_task.cancel()
                            mulaw = _pcm24k_to_mulaw8k(part.inline_data.data)
                            await self._on_audio_out(mulaw)
                        if part.text:
                            _agent_buf.append(part.text)
                            if self._on_agent_text:
                                asyncio.create_task(self._on_agent_text(part.text))

                if sc.turn_complete:
                    log.info("[GEMINI] Agent turn complete")
                    self._agent_responding = False
                    self._barge_in_pending = False
                    # With response_modalities=AUDIO, text arrives via output_transcription,
                    # not model_turn.parts — so fall back to output_trans_buf for history.
                    final_text = " ".join(_agent_buf) if _agent_buf else " ".join(_output_trans_buf)
                    if final_text:
                        self._history.append(types.Content(
                            role="model",
                            parts=[types.Part(text=final_text)],
                        ))
                        log.info(f"[GEMINI] Model turn saved to history: {final_text[:60]}")
                    _agent_buf.clear()
                    _output_trans_buf.clear()

                # Input audio transcript (what the user said)
                if hasattr(sc, "input_transcription") and sc.input_transcription:
                    t = getattr(sc.input_transcription, "text", "") or ""
                    if t.strip():
                        self._history.append(types.Content(
                            role="user",
                            parts=[types.Part(text=t.strip())],
                        ))
                        log.info(f"[GEMINI] User turn saved to history: {t.strip()[:60]}")
                        if self._on_user_transcript:
                            asyncio.create_task(self._on_user_transcript(t.strip()))

                # Output audio transcript (what the agent said) — primary source in AUDIO mode
                if hasattr(sc, "output_transcription") and sc.output_transcription:
                    t = getattr(sc.output_transcription, "text", "") or ""
                    if t.strip():
                        _output_trans_buf.append(t.strip())
                        if self._on_agent_text:
                            asyncio.create_task(self._on_agent_text(t.strip()))

            log.warning("[GEMINI] recv_loop: session.receive() generator exhausted — session closed by server")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error(f"[GEMINI] Recv error: {e}", exc_info=True)
