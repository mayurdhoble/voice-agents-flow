"""
Hotel Front Desk Voice Calling Agent
Powered by: Gemini Live API + Vobiz (https://console.vobiz.ai)
Voice: Indian English (en-IN), persona: Priya
"""

import asyncio
import logging
import traceback
from contextlib import asynccontextmanager
from urllib.parse import urlparse

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response, JSONResponse

from config import HOST, PORT, PUBLIC_URL, HOTEL_NAME, AGENT_NAME
from call_handler import CallHandler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("hotel_agent")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"=== {HOTEL_NAME} Voice Agent — {AGENT_NAME} ===")
    ws_url = PUBLIC_URL.replace("https://", "wss://").replace("http://", "ws://")
    logger.info(f"Answer URL (set in Vobiz):  POST {PUBLIC_URL}/answer")
    logger.info(f"Hangup URL (set in Vobiz):  POST {PUBLIC_URL}/hangup")
    logger.info(f"WebSocket stream endpoint:  {ws_url}/media-stream")
    yield
    logger.info("Shutting down")


app = FastAPI(
    title=f"{HOTEL_NAME} Voice Agent",
    description="AI hotel front desk with Indian English accent — Vobiz + Gemini Live",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "agent": AGENT_NAME,
        "hotel": HOTEL_NAME,
        "answer_url": f"{PUBLIC_URL}/answer",
        "hangup_url": f"{PUBLIC_URL}/hangup",
    }


@app.post("/answer")
async def answer(request: Request):
    """
    Vobiz Answer URL — called when an inbound call arrives.
    We respond with Vobiz XML that opens a bidirectional audio stream.
    """
    form = await request.form()
    call_uuid = form.get("CallUUID", "unknown")
    caller = form.get("From", "unknown")
    logger.info(f"Incoming call — UUID: {call_uuid}, From: {caller}")

    ws_url = PUBLIC_URL.replace("https://", "wss://").replace("http://", "ws://")

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Stream bidirectional="true" keepCallAlive="true"
            contentType="audio/x-mulaw;rate=8000"
            extraHeaders="X-CallUUID: {call_uuid}">
        {ws_url}/media-stream
    </Stream>
</Response>"""

    return Response(content=xml, media_type="application/xml")


@app.post("/hangup")
async def hangup(request: Request):
    """Vobiz Hangup URL — called when a call ends."""
    form = await request.form()
    call_uuid = form.get("CallUUID", "unknown")
    duration = form.get("Duration", "?")
    logger.info(f"Call ended — UUID: {call_uuid}, Duration: {duration}s")
    return JSONResponse({"status": "ok"})


@app.websocket("/media-stream")
async def media_stream(websocket: WebSocket):
    """
    Vobiz bidirectional audio stream WebSocket.
    Bridges caller audio ↔ Gemini Live in real-time.
    """
    await websocket.accept()
    logger.info("WebSocket connected — starting Gemini Live session")

    handler = CallHandler(websocket)
    try:
        await handler.run()
    except WebSocketDisconnect:
        logger.info("Caller disconnected")
    except Exception:
        logger.error(f"Session error:\n{traceback.format_exc()}")
    finally:
        await handler.cleanup()
        logger.info("Session ended")


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=HOST,
        port=PORT,
        log_level="info",
        reload=False,
    )
