import os
import re
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from openai import AsyncOpenAI
from knowledge_base.retriever import retrieve_context
from prompts.hotel_prompt import SYSTEM_PROMPT, build_user_message

_rag_executor = ThreadPoolExecutor(max_workers=2)  # still used to run sync encode() off event loop
_log = logging.getLogger("agent")

client = AsyncOpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
)

MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-001")

_STRIP = re.compile(r"^(Maya:|Assistant:)\s*", re.IGNORECASE)

LANGUAGE_NAMES = {
    "en": "English",
    "hi": "Hindi",
    "mr": "Marathi",
    "te": "Telugu",
    "ta": "Tamil",
    "kn": "Kannada",
    "bn": "Bengali",
    "gu": "Gujarati",
}


# English/Hinglish keywords — \b word boundaries work fine for ASCII
_NEEDS_RAG_EN = re.compile(
    r"\b(pool|swimming|restaurant|spa|gym|fitness|wifi|wi[-\s]fi|parking|airport|"
    r"pickup|pick[\s-]up|transport|shuttle|"
    r"event|conference|banquet|ball\s*room|hall|space|spaces|party|birthday|"
    r"wedding|function|gathering|"
    r"facility|facilities|amenity|amenities|"
    r"breakfast|dinner|lunch|bar|lounge|catering|cuisine|menu|food|"
    r"veg|vegetarian|vegan|non.veg|nonveg|"
    r"laundry|location|address|direction|nearby|distance|"
    r"garden|terrace|rooftop|"
    r"check[\s-]?in time|check[\s-]?out time|policy|cancellation|"
    r"about the hotel|tell me about|what do you have|what do you offer|"
    r"services|service|"
    r"hotel ke baare|hotel mein kya|hotel about)\b",
    re.IGNORECASE,
)

# Devanagari keywords — no \b: vowel-sign matras (ा ि ी े) are \W in Python regex
# so \b after a matra-ending word fails. Simple substring search is safe enough
# since these are specific hotel-vocabulary terms.
_NEEDS_RAG_DEVA = re.compile(
    # ── Hindi ─────────────────────────────────────────────────────────────
    r"पूल|स्विमिंग|रेस्टोरेंट|रेस्टॉरंट|स्पा|जिम|फिटनेस|"
    r"वाईफाई|वायफाय|वाईफाय|"
    r"पार्किंग|एयरपोर्ट|पिकअप|ट्रांसपोर्ट|शटल|"
    r"इवेंट|कॉन्फ्रेंस|बैंक्वेट|हॉल|पार्टी|बर्थडे|शादी|फंक्शन|"
    r"फैसिलिटी|फैसिलिटीज|सुविधा|सुविधाएं|सुविधाओं|"
    r"नाश्ता|ब्रेकफास्ट|डिनर|लंच|लाउंज|खाना|मेनू|फूड|"
    r"शाकाहारी|मांसाहारी|"
    r"लॉन्ड्री|लोकेशन|पता|दिशा|नजदीक|दूरी|"
    r"गार्डन|टेरेस|रूफटॉप|"
    r"चेक.इन|चेक.आउट|पॉलिसी|कैंसलेशन|"
    r"सर्विस|सर्विसेज|"
    # ── Marathi ───────────────────────────────────────────────────────────
    r"एअरपोर्ट|विमानतळ|वाढदिवस|लग्न|"
    r"इव्हेंट|कॉन्फरन्स|बँक्वेट|"
    r"जेवण|खाणे|"
    r"पत्ता|अंतर|रद्दीकरण",
    re.IGNORECASE,
)


def needs_rag(message: str) -> bool:
    """Return True if this message warrants a KB lookup."""
    if len(message.split()) <= 3:
        return False
    return bool(_NEEDS_RAG_EN.search(message) or _NEEDS_RAG_DEVA.search(message))


async def _fetch_rag(user_message: str) -> str:
    """In-memory KB lookup via cosine similarity (~20ms, no network).
    Only runs when the query contains hotel-facility keywords."""
    if not needs_rag(user_message):
        _log.debug("[LLM] RAG skipped — no facility keywords")
        return ""
    loop = asyncio.get_event_loop()
    # Run sentence-transformers encode() in executor to avoid blocking the event loop
    result = await loop.run_in_executor(_rag_executor, retrieve_context, user_message)
    _log.debug(f"[LLM] RAG hit: {result[:80]}...")
    return result


def start_rag_task(message: str) -> "asyncio.Task[str]":
    """Start RAG fetch as a background asyncio.Task so the caller can do
    other work (e.g. play a hold phrase) while the lookup runs."""
    return asyncio.create_task(_fetch_rag(message))


def _extract_booking_state(history: list[dict]) -> str:
    """Scan assistant messages to extract confirmed booking fields.
    Returns a compact summary string, or empty string if nothing confirmed yet."""
    import re as _re
    state = {}
    for msg in history:
        if msg["role"] != "assistant":
            continue
        t = msg["content"]
        # Name: "Lovely, Mayur!" / "Thank you, Mayur!" / "धन्यवाद, Mayur!"
        if "name" not in state:
            m = _re.search(r"(?:lovely|wonderful|thank you|noted|great|sure|धन्यवाद|बिल्कुल),?\s+([A-Za-zऀ-ॿ]{2,20})[!.,]", t, _re.IGNORECASE)
            if m:
                state["name"] = m.group(1).strip(".,!")
        # Check-in: "check-in is on the ..." / "check-in ... second of August"
        if "check_in" not in state:
            m = _re.search(r"check[- ]?in (?:is (?:on )?(?:the )?|date is )(.{5,30})(?:\.|,|\?)", t, _re.IGNORECASE)
            if m:
                state["check_in"] = m.group(1).strip()
        # Checkout: "checkout would be the ..." / "checking out on the ..."
        if "check_out" not in state:
            m = _re.search(r"(?:checkout|checking out) (?:would be|is|on) (?:the )?(.{5,30})(?:\.|,|\?)", t, _re.IGNORECASE)
            if m:
                state["check_out"] = m.group(1).strip()
    if not state:
        return ""
    lines = []
    if "name" in state:
        lines.append(f"guest name: {state['name']} (locked — do NOT ask again)")
    if "check_in" in state:
        lines.append(f"check-in: {state['check_in']} (confirmed)")
    if "check_out" in state:
        lines.append(f"check-out: {state['check_out']} (confirmed)")
    return "\n".join(lines)


def _build_messages(
    user_message: str, history: list[dict], language: str, context: str,
    returning_guest: dict | None = None,
    available_rooms: list[str] | None = None,
) -> list[dict]:
    lang_name = LANGUAGE_NAMES.get(language, "English")
    system_content = SYSTEM_PROMPT.format(language=lang_name)

    # Returning guest context
    if returning_guest:
        name = returning_guest.get("name", "")
        lb   = returning_guest.get("last_booking")
        lines = [f"RETURNING GUEST: {name} (phone on file)"]
        if lb:
            lines.append(f"Last stay: {lb.get('checkin_date','')} → {lb.get('checkout_date','')} | {lb.get('room_type','')} | status={lb.get('status','')}")
            lines.append("Greet them warmly by name. Confirm if they want the same room or something different.")
        else:
            lines.append("Guest is in our system but has no prior bookings. Greet warmly by name.")
        system_content += "\n\n[" + "\n".join(lines) + "]"

    # Live availability context
    if available_rooms is not None:
        if available_rooms:
            rooms_str = ", ".join(available_rooms)
            system_content += f"\n\n[LIVE AVAILABILITY — only suggest these rooms for the requested dates]\nAvailable: {rooms_str}\nDo NOT suggest any room not in this list."
        else:
            system_content += "\n\n[LIVE AVAILABILITY — no rooms available for requested dates. Apologise and ask if they'd like to try different dates.]"

    booking_state = _extract_booking_state(history)
    if booking_state:
        system_content += f"\n\n[CONFIRMED THIS CALL — NEVER RE-ASK THESE]\n{booking_state}"

    messages = [{"role": "system", "content": system_content}]
    for turn in history[-40:]:
        messages.append({"role": turn["role"], "content": turn["content"]})
    if messages and messages[-1]["role"] == "user":
        messages[-1]["content"] = build_user_message(user_message, context)
    else:
        messages.append({"role": "user", "content": build_user_message(user_message, context)})
    return messages


async def generate_response_stream(
    user_message: str,
    history: list[dict],
    language: str = "en",
    rag_task: "asyncio.Task[str] | None" = None,
    returning_guest: dict | None = None,
    available_rooms: list[str] | None = None,
):
    """Async generator — yields clean sentences as LLM streams them.

    Pass rag_task if RAG was already started in the background (e.g. while
    a hold phrase was playing). Otherwise RAG is fetched internally.

    Sentence boundaries: '. ' / '? ' / '! ' / '।' — must have ≥8 chars buffered
    to avoid splitting on "Mr. " or similar short fragments.
    """
    context = await rag_task if rag_task is not None else await _fetch_rag(user_message)
    messages = _build_messages(user_message, history, language, context,
                               returning_guest=returning_guest, available_rooms=available_rooms)

    stream = await client.chat.completions.create(
        model=MODEL, messages=messages, max_tokens=100, temperature=0.3, stream=True
    )

    buffer = ""
    async for chunk in stream:
        token = chunk.choices[0].delta.content or ""
        buffer += token
        # Yield complete sentences as they arrive
        while True:
            extracted = False
            for sep in (". ", "? ", "! ", "।", "\n"):
                pos = buffer.find(sep)
                if pos >= 0 and (pos + len(sep)) >= 8:
                    sentence = buffer[: pos + len(sep)].strip()
                    buffer = buffer[pos + len(sep) :]
                    clean = _STRIP.sub("", sentence).strip()
                    if clean:
                        yield clean
                    extracted = True
                    break
            if not extracted:
                break

    # Flush whatever remains after stream ends
    remainder = _STRIP.sub("", buffer.strip()).strip()
    if remainder:
        yield remainder


async def generate_response(
    user_message: str,
    history: list[dict],
    language: str = "en",
) -> str:
    """Non-streaming fallback — used for silence reprompts and greeting."""
    context = await _fetch_rag(user_message)
    messages = _build_messages(user_message, history, language, context)

    response = await client.chat.completions.create(
        model=MODEL,
        messages=messages,
        max_tokens=100,
        temperature=0.3,
    )

    raw = response.choices[0].message.content
    if raw is None:
        _log.warning(f"[LLM] content=None finish={response.choices[0].finish_reason}")
    reply = (raw or "").strip()
    reply = _STRIP.sub("", reply).strip()
    return reply or "One moment please, let me check that for you."
