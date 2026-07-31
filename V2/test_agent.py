"""
Text-based test: verify that Priya's persona and Indian English work correctly
without needing a real phone call. Run with: python test_agent.py
"""

import asyncio
import logging

from google import genai
from google.genai import types

from config import GEMINI_API_KEY, GEMINI_MODEL, VOICE_NAME, LANGUAGE_CODE
from prompts import SYSTEM_PROMPT

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test")

TEST_INPUTS = [
    "Hello, I want to book a room for 2 nights.",
    "Mujhe ek room chahiye, kya available hai?",       # Hindi
    "Mala ek room book karaychi ahe.",                 # Marathi
    "What is the price of a deluxe room?",
    "Do you have any special package for honeymoon?",
]


async def run_text_test():
    client = genai.Client(api_key=GEMINI_API_KEY)

    config = types.LiveConnectConfig(
        response_modalities=["TEXT"],
        system_instruction=types.Content(
            parts=[types.Part(text=SYSTEM_PROMPT)]
        ),
    )

    async with client.aio.live.connect(model=GEMINI_MODEL, config=config) as session:
        print("\n" + "=" * 60)
        print("  Hotel Front Desk Agent — Text Test")
        print("=" * 60 + "\n")

        for user_input in TEST_INPUTS:
            print(f"[CALLER]: {user_input}")
            await session.send(input=user_input, end_of_turn=True)

            response_text = ""
            async for response in session.receive():
                if response.text:
                    response_text += response.text
                if hasattr(response, "server_content"):
                    sc = response.server_content
                    if sc and sc.turn_complete:
                        break

            print(f"[PRIYA] : {response_text.strip()}\n")
            print("-" * 60)


if __name__ == "__main__":
    asyncio.run(run_text_test())
