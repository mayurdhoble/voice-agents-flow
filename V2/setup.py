"""
Quick setup script — copies .env.example to .env and installs dependencies.
Run: python setup.py
"""

import os
import shutil
import subprocess
import sys


def main():
    print("\n=== Hotel Voice Agent Setup ===\n")

    # Copy .env.example → .env if not exists
    if not os.path.exists(".env"):
        shutil.copy(".env.example", ".env")
        print("[1] Created .env from .env.example")
        print("    --> Please edit .env and fill in your API keys before running!\n")
    else:
        print("[1] .env already exists — skipping\n")

    # Install requirements
    print("[2] Installing Python dependencies...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
    print("\n[2] Dependencies installed\n")

    print("=== Setup Complete ===")
    print("\nNext steps:")
    print("  1. Edit .env with your GEMINI_API_KEY, Twilio credentials, and PUBLIC_URL")
    print("  2. Start ngrok:       ngrok http 8000")
    print("  3. Update PUBLIC_URL in .env with the ngrok HTTPS URL")
    print("  4. Test the persona:  python test_agent.py")
    print("  5. Start the server:  python main.py")
    print("  6. Set your Twilio phone number webhook to: https://your-ngrok-url/incoming-call\n")


if __name__ == "__main__":
    main()
