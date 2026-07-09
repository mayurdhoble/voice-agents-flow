import os
import re
from openai import AsyncOpenAI
from knowledge_base.retriever import retrieve_context
from prompts.hotel_prompt import SYSTEM_PROMPT, build_user_message

client = AsyncOpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
)

MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-001")

_STRIP = re.compile(r"^(Aria:|Assistant:)\s*", re.IGNORECASE)

LANGUAGE_NAMES = {
    "hi": "Hindi",
    "mr": "Marathi",
    "en": "English",
}


async def generate_response(
    user_message: str,
    history: list[dict],
    language: str = "en",
) -> str:
    context = retrieve_context(user_message)
    lang_name = LANGUAGE_NAMES.get(language, "English")

    messages = [{"role": "system", "content": SYSTEM_PROMPT.format(language=lang_name)}]

    for turn in history[-6:]:
        messages.append({"role": turn["role"], "content": turn["content"]})

    if messages and messages[-1]["role"] == "user":
        messages[-1]["content"] = build_user_message(user_message, context)
    else:
        messages.append({"role": "user", "content": build_user_message(user_message, context)})

    response = await client.chat.completions.create(
        model=MODEL,
        messages=messages,
        max_tokens=120,
        temperature=0.3,
    )

    reply = response.choices[0].message.content.strip()
    reply = _STRIP.sub("", reply).strip()
    return reply
