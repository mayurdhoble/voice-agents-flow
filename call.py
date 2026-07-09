"""
Usage:
    python call.py +918806889635
    python call.py +919999999999
"""
import sys
import os
from dotenv import load_dotenv
load_dotenv()
from twilio.rest import Client

number = sys.argv[1] if len(sys.argv) > 1 else os.getenv("TEST_NUMBER")
if not number:
    print("Usage: python call.py +91XXXXXXXXXX")
    sys.exit(1)

client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
call = client.calls.create(
    to=number,
    from_=os.getenv("TWILIO_PHONE_NUMBER"),
    url=os.getenv("PUBLIC_URL") + "/incoming-call"
)
print(f"Calling {number}... SID: {call.sid}")
