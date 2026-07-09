import os
import json
import asyncio
import websockets

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


class DeepgramSTT:
    """
    Streams mulaw audio from Twilio to Deepgram.
    Calls on_transcript(text, language) when caller finishes speaking.
    language is an ISO code: 'en', 'hi', 'mr', etc.
    """

    def __init__(self, on_transcript):
        self.on_transcript = on_transcript
        self.api_key = os.getenv("DEEPGRAM_API_KEY")
        self.ws = None
        self._receiver_task = None
        self.detected_language = "en"

    async def start(self):
        headers = {"Authorization": f"Token {self.api_key}"}
        self.ws = await websockets.connect(DEEPGRAM_URL, additional_headers=headers)
        self._receiver_task = asyncio.create_task(self._receive_loop())
        print("[STT] Deepgram connected")

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
        print("[STT] Deepgram disconnected")

    async def _receive_loop(self):
        last_interim = ""
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
                                print(f"[STT] {transcript}")
                                await self.on_transcript(transcript, "en")
                            else:
                                last_interim = transcript  # keep latest interim

                    except (KeyError, IndexError):
                        pass

                elif msg_type == "UtteranceEnd":
                    # Fires after utterance_end_ms of no new final transcript
                    # Use last interim so caller's speech isn't lost
                    if last_interim.strip():
                        text = last_interim
                        last_interim = ""
                        print(f"[STT] (utterance_end) {text}")
                        await self.on_transcript(text, "en")

        except websockets.exceptions.ConnectionClosed:
            print("[STT] Deepgram connection closed")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[STT] Error: {e}")
