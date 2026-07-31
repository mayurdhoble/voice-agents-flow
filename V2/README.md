# Hotel Front Desk Voice Agent

AI-powered hotel front desk agent with **Indian English accent**, built on **Gemini Live** + **Twilio**.

**Persona:** Priya — warm, professional, always sounds like the same person  
**Languages:** English (Indian accent), Hindi, Marathi, and other Indian languages  
**Hotel:** Configurable via `.env`

---

## Architecture

```
Incoming Call (Twilio)
       │
       ▼ WebSocket (mulaw 8kHz)
  FastAPI Server
       │
       ▼ WebSocket (PCM 16kHz)
  Gemini Live API
  (en-IN, Kore voice)
       │
       ▼ Audio response (PCM 24kHz → mulaw 8kHz)
  FastAPI Server
       │
       ▼ WebSocket
  Caller hears Priya
```

---

## Quick Start

### 1. Install
```bash
python setup.py
```

### 2. Configure `.env`
```
GEMINI_API_KEY=...       # from https://aistudio.google.com/app/apikey
TWILIO_ACCOUNT_SID=...   # from https://console.twilio.com
TWILIO_AUTH_TOKEN=...
TWILIO_PHONE_NUMBER=+91XXXXXXXXXX
PUBLIC_URL=https://abc123.ngrok.io
```

### 3. Test the persona (no phone needed)
```bash
python test_agent.py
```

### 4. Run the server
```bash
python main.py
```

### 5. Expose locally (for development)
```bash
ngrok http 8000
# Copy the HTTPS URL → set as PUBLIC_URL in .env
```

### 6. Configure Twilio
- Go to your Twilio phone number settings
- Set **Voice webhook** to: `https://your-ngrok-url/incoming-call`
- Method: `HTTP POST`

---

## Voice Configuration

| Setting | Value | Notes |
|---------|-------|-------|
| Model | `gemini-2.0-flash-live-001` | Gemini Live |
| Voice | `Kore` | Warm female voice |
| Language | `en-IN` | Indian English |
| Accent | Indian English | Configured via system prompt |

**To change the voice**, edit `VOICE_NAME` in `config.py`:
- `Kore` — warm female (recommended)
- `Aoede` — expressive female
- `Puck` — friendly male
- `Charon` — calm male

---

## Customizing the Hotel

Edit `prompts.py` or set these in `.env`:
```
HOTEL_NAME=Your Hotel Name
HOTEL_CITY=Your City
AGENT_NAME=Your Agent Name
```

To add rooms, services, or pricing — edit the `SYSTEM_PROMPT` in `prompts.py`.

---

## File Structure

```
├── main.py          # FastAPI app + Twilio webhooks
├── call_handler.py  # Per-call Gemini Live session manager
├── audio_utils.py   # mulaw ↔ PCM conversion
├── prompts.py       # Priya's system prompt (hotel info + persona)
├── config.py        # All configuration
├── test_agent.py    # Text-mode test (no phone required)
├── setup.py         # One-click setup
├── requirements.txt
└── .env.example
```

---

## Requirements

- Python 3.10+
- Google Gemini API key (Gemini Live access)
- Twilio account with a phone number
- ngrok (for local development)
