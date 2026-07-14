"""
Make an outbound call via VoiceLink.
Usage:
    python vl_call.py +919876543210
"""
import sys
import os
import asyncio
from dotenv import load_dotenv
load_dotenv()

from services.voicelink import make_call

number = sys.argv[1] if len(sys.argv) > 1 else os.getenv("TEST_NUMBER")
if not number:
    print("Usage: python vl_call.py +91XXXXXXXXXX")
    sys.exit(1)

result = asyncio.run(make_call(number))
if result:
    print(f"Call initiated: {result}")
else:
    print("Call failed — check logs")
