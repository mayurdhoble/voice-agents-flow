import os
import re
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from openai import AsyncOpenAI
from knowledge_base.retriever import retrieve_context
from prompts.hotel_prompt import SYSTEM_PROMPT, build_user_message

_rag_executor = ThreadPoolExecutor(max_workers=2)
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


async def generate_response(
    user_message: str,
    history: list[dict],
    language: str = "en",
) -> str:
    # Run RAG in thread pool with 2s timeout — fall back to no context if slow
    loop = asyncio.get_event_loop()
    try:
        context = await asyncio.wait_for(
            loop.run_in_executor(_rag_executor, retrieve_context, user_message),
            timeout=2.0,
        )
    except asyncio.TimeoutError:
        _log.warning("[LLM] RAG timeout — proceeding without context")
        context = ""
    lang_name = LANGUAGE_NAMES.get(language, "English")

    messages = [{"role": "system", "content": SYSTEM_PROMPT.format(language=lang_name)}]

    for turn in history[-40:]:
        messages.append({"role": turn["role"], "content": turn["content"]})

    if messages and messages[-1]["role"] == "user":
        messages[-1]["content"] = build_user_message(user_message, context)
    else:
        messages.append({"role": "user", "content": build_user_message(user_message, context)})

    response = await client.chat.completions.create(
        model=MODEL,
        messages=messages,
        max_tokens=60,
        temperature=0.3,
    )

    raw = response.choices[0].message.content
    if raw is None:
        import logging
        logging.getLogger("agent").warning(f"[LLM] content=None finish={response.choices[0].finish_reason}")
    reply = (raw or "").strip()
    reply = _STRIP.sub("", reply).strip()
    return reply or "One moment please, let me check that for you."
