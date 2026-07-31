"""
Hotel Front Desk Voice Agent — Call Handler
Vobiz WebSocket ↔ Gemini Live bidirectional audio bridge
"""

import asyncio
import audioop
import base64
import json
import logging

from fastapi import WebSocket
from google import genai
from google.genai import types

from config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    VOICE_NAME,
    LANGUAGE_CODE,
    GEMINI_SAMPLE_RATE,
    GEMINI_OUTPUT_RATE,
)
from prompts import SYSTEM_PROMPT

logger = logging.getLogger("call_handler")

_schema_logged = False

# Buffer 5 Vobiz chunks (5 × 20ms = 100ms) before sending to Gemini
# Larger packets give VAD a better chance to detect speech
CHUNK_BUFFER_SIZE = 5


class CallHandler:
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.stream_id: str = ""
        self.gemini_session = None
        self.client = genai.Client(api_key=GEMINI_API_KEY)
        self._send_queue: asyncio.Queue = asyncio.Queue()
        self._running = True
        self._chunks_sent = 0

        # Maintain ratecv state for continuous resampling (no chunk-boundary pops)
        self._upsample_state = None   # 8kHz → 16kHz (caller → Gemini)
        self._downsample_state = None  # 24kHz → 8kHz (Gemini → caller)

        # Audio buffer — accumulate before sending to Gemini
        self._audio_buffer: list[bytes] = []

    def _build_live_config(self) -> types.LiveConnectConfig:
        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=types.Content(
                parts=[types.Part(text=SYSTEM_PROMPT)]
            ),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=VOICE_NAME,
                    )
                ),
                language_code=LANGUAGE_CODE,
            ),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    start_of_speech_sensitivity=types.StartSensitivity.START_SENSITIVITY_HIGH,
                    end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_LOW,
                )
            ),
        )

    async def run(self):
        async with self.client.aio.live.connect(
            model=GEMINI_MODEL,
            config=self._build_live_config(),
        ) as session:
            self.gemini_session = session
            logger.info("Gemini Live session ready")

            await session.send(
                input="[Phone call connected. Greet the caller warmly as Priya from the hotel front desk.]",
                end_of_turn=True,
            )

            results = await asyncio.gather(
                self._receive_from_vobiz(),
                self._receive_from_gemini(),
                self._flush_to_vobiz(),
                return_exceptions=True,
            )
            for r in results:
                if isinstance(r, Exception):
                    logger.warning(f"Task ended: {r}")

    async def _receive_from_vobiz(self):
        """Read audio from Vobiz and forward buffered chunks to Gemini."""
        global _schema_logged

        async for raw in self.websocket.iter_text():
            if not self._running:
                break
            try:
                data = json.loads(raw)
                event = data.get("event", "")

                if event == "start":
                    start = data.get("start", {})
                    self.stream_id = start.get("streamId") or start.get("streamSid") or ""
                    logger.info(f"Stream started: {self.stream_id}")

                elif event == "media":
                    media = data.get("media", {})

                    if not _schema_logged:
                        keys = {k: (v[:60] + "..." if isinstance(v, str) and len(v) > 60 else v)
                                for k, v in media.items()}
                        logger.info(f"Vobiz media keys: {keys}")
                        _schema_logged = True

                    b64_audio = media.get("payload") or media.get("data")
                    if not isinstance(b64_audio, str) or not b64_audio:
                        continue

                    # Decode mulaw → PCM 16kHz, maintaining resampling state
                    mulaw = base64.b64decode(b64_audio)
                    pcm_8k = audioop.ulaw2lin(mulaw, 2)
                    # Boost gain so Gemini VAD can detect the caller's voice
                    pcm_8k = audioop.mul(pcm_8k, 2, 3.0)
                    pcm_16k, self._upsample_state = audioop.ratecv(
                        pcm_8k, 2, 1, 8000, 16000, self._upsample_state
                    )

                    # Buffer chunks and send in batches for better VAD detection
                    self._audio_buffer.append(pcm_16k)
                    if len(self._audio_buffer) >= CHUNK_BUFFER_SIZE:
                        combined = b"".join(self._audio_buffer)
                        self._audio_buffer.clear()
                        try:
                            await self.gemini_session.send_realtime_input(
                                audio=types.Blob(
                                    mime_type=f"audio/pcm;rate={GEMINI_SAMPLE_RATE}",
                                    data=combined,
                                )
                            )
                            self._chunks_sent += CHUNK_BUFFER_SIZE
                            if self._chunks_sent % 200 == 0:
                                logger.info(f"Audio chunks sent to Gemini: {self._chunks_sent}")
                        except Exception as e:
                            logger.error(f"Gemini send_realtime_input failed: {e}")
                            self._running = False
                            break

                elif event == "stop":
                    logger.info(f"Vobiz STOP event received — caller hung up. Chunks sent: {self._chunks_sent}")
                    self._running = False
                    break

            except json.JSONDecodeError:
                pass
            except Exception as e:
                logger.warning(f"Vobiz frame error: {e}")

    async def _receive_from_gemini(self):
        """Read Gemini responses across multiple turns, staying alive between turns."""
        try:
            while self._running:
                turn_had_response = False
                async for response in self.gemini_session.receive():
                    if not self._running:
                        return

                    turn_had_response = True

                    if hasattr(response, "server_content") and response.server_content:
                        sc = response.server_content
                        if sc.input_transcription and sc.input_transcription.text:
                            logger.info(f"[Caller]: {sc.input_transcription.text}")
                        if sc.output_transcription and sc.output_transcription.text:
                            logger.info(f"[Priya] : {sc.output_transcription.text}")

                    if response.data:
                        pcm_8k, self._downsample_state = audioop.ratecv(
                            response.data, 2, 1, GEMINI_OUTPUT_RATE, 8000, self._downsample_state
                        )
                        mulaw = audioop.lin2ulaw(pcm_8k, 2)
                        payload = base64.b64encode(mulaw).decode("utf-8")
                        await self._send_queue.put(payload)

                # Inner for-loop exited — Gemini completed a turn, wait for next
                if turn_had_response:
                    logger.info("Gemini turn complete — waiting for caller input...")
                else:
                    # No responses at all means the session was truly closed
                    logger.info("Gemini session closed (no more responses)")
                    break

        except Exception as e:
            logger.warning(f"Gemini session error: {e}")
        finally:
            self._running = False

    async def _flush_to_vobiz(self):
        """Drain audio queue and send back to Vobiz."""
        while self._running or not self._send_queue.empty():
            try:
                payload = await asyncio.wait_for(self._send_queue.get(), timeout=0.5)
                msg = json.dumps({
                    "event": "playAudio",
                    "media": {
                        "contentType": "audio/x-mulaw",
                        "sampleRate": "8000",
                        "payload": payload,
                    },
                })
                await self.websocket.send_text(msg)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.warning(f"Vobiz send error: {e}")
                break

    async def cleanup(self):
        self._running = False
        logger.info(f"Call ended — total chunks sent to Gemini: {self._chunks_sent}")
        if self.gemini_session:
            try:
                await self.gemini_session.close()
            except Exception:
                pass
