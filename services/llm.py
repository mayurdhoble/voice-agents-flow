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

_STRIP = re.compile(r"^(Aria:|Assistant:)\s*", re.IGNORECASE)

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


# Keywords that signal a guest is asking about hotel facilities/info → trigger RAG
_NEEDS_RAG = re.compile(
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


def needs_rag(message: str) -> bool:
    """Return True if this message warrants a KB lookup."""
    if len(message.split()) <= 3:
        return False
    return bool(_NEEDS_RAG.search(message))


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


def _build_messages(
    user_message: str, history: list[dict], language: str, context: str
) -> list[dict]:
    lang_name = LANGUAGE_NAMES.get(language, "English")
    messages = [{"role": "system", "content": SYSTEM_PROMPT.format(language=lang_name)}]
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
):
    """Async generator — yields clean sentences as LLM streams them.

    Pass rag_task if RAG was already started in the background (e.g. while
    a hold phrase was playing). Otherwise RAG is fetched internally.

    Sentence boundaries: '. ' / '? ' / '! ' / '।' — must have ≥8 chars buffered
    to avoid splitting on "Mr. " or similar short fragments.
    """
    context = await rag_task if rag_task is not None else await _fetch_rag(user_message)
    messages = _build_messages(user_message, history, language, context)

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
