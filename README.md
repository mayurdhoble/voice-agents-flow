# Hotel Voice Agent

AI-powered phone agent that handles hotel customer calls — room bookings, facilities, policies — using your hotel's knowledge base.

## Project Structure

```
├── main.py                     # FastAPI server (Twilio webhook + WebSocket)
├── services/
│   ├── stt.py                  # Deepgram Speech-to-Text (streaming)
│   ├── llm.py                  # OpenRouter LLM with RAG
│   └── tts.py                  # ElevenLabs Text-to-Speech
├── knowledge_base/
│   ├── ingest.py               # Load PDFs/URLs/text into Pinecone (run once)
│   └── retriever.py            # Search Pinecone at runtime
├── prompts/
│   └── hotel_prompt.py         # Agent personality + instructions
├── data/                       # Put your PDFs and .txt files here
├── .env                        # All API keys (fill this in)
└── requirements.txt
```

## Step 1 — Install dependencies

```bash
pip install -r requirements.txt
```

> Also install ffmpeg (required by pydub for audio conversion):
> Windows: `winget install ffmpeg` or download from https://ffmpeg.org

## Step 2 — Fill in .env

Open `.env` and add all your API keys.

## Step 3 — Add your hotel knowledge base

Put your hotel PDFs and text files in the `data/` folder.
Then edit `knowledge_base/ingest.py` — uncomment and add your file paths and URLs:

```python
sources = {
    "pdfs":  ["data/hotel_brochure.pdf", "data/room_types.pdf"],
    "urls":  ["https://yourhotel.com/rooms", "https://yourhotel.com/facilities"],
    "texts": ["data/faq.txt"],
}
```

Run ingestion once:

```bash
python knowledge_base/ingest.py
```

## Step 4 — Start ngrok tunnel (for local dev)

```bash
ngrok http 8000
```

Copy the `https://xxxx.ngrok.io` URL and put it in `.env` as `PUBLIC_URL`.

## Step 5 — Configure Twilio

1. Go to your Twilio phone number settings
2. Set the webhook for incoming calls to: `https://xxxx.ngrok.io/incoming-call`
3. Method: HTTP POST

## Step 6 — Run the server

```bash
python main.py
```

## Step 7 — Test it

Call your Twilio phone number. You'll hear Aria greet you and answer questions from your hotel knowledge base.

## Call Flow

```
Caller speaks
  → Twilio streams audio (mulaw 8kHz) via WebSocket
    → Deepgram transcribes in real-time
      → OpenRouter LLM generates response using hotel KB
        → ElevenLabs converts response to speech
          → Audio streams back to caller via Twilio
```
