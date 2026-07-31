import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_LIVE_MODEL", "gemini-2.0-flash-live-001")

# Voice: "Kore" = warm female | options: Aoede, Charon, Fenrir, Kore, Puck
VOICE_NAME = "Kore"
LANGUAGE_CODE = "en-IN"  # Indian English

# Vobiz credentials — https://console.vobiz.ai
VOBIZ_AUTH_ID = os.getenv("VOBIZ_AUTH_ID", "")
VOBIZ_AUTH_TOKEN = os.getenv("VOBIZ_AUTH_TOKEN", "")
VOBIZ_PHONE_NUMBER = os.getenv("VOBIZ_PHONE_NUMBER", "")
VOBIZ_API_BASE = "https://api.vobiz.ai/api/v1"

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
PUBLIC_URL = os.getenv("PUBLIC_URL", "").rstrip("/")

HOTEL_NAME = os.getenv("HOTEL_NAME", "The Royal Palace Hotel")
HOTEL_CITY = os.getenv("HOTEL_CITY", "Mumbai")
AGENT_NAME = os.getenv("AGENT_NAME", "Priya")

# Audio
TWILIO_SAMPLE_RATE = 8000   # Vobiz mulaw input is 8kHz (same as Twilio)
GEMINI_SAMPLE_RATE = 16000  # Gemini Live input
GEMINI_OUTPUT_RATE = 24000  # Gemini Live output
