import os, time, requests, csv
from pathlib import Path
from datetime import datetime

# Automātiska .env.local ielāde, ja TG nav ENV
env_file = Path(".env.local")
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            if line.strip() and not line.startswith("#"):
                key, _, val = line.strip().partition("=")
                if key not in os.environ:
                    os.environ[key] = val

BOT_TOKEN = os.getenv("TG_BOT_TOKEN") or os.getenv("TG_TOKEN") or ""
CHAT_ID = os.getenv("TG_CHAT_ID") or os.getenv("TG_CHAT") or ""

def send(msg: str):
    if not BOT_TOKEN or not CHAT_ID:
        print("[WARN] Telegram not configured.")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": msg},
            timeout=5,
        )
    except Exception as e:
        print("[TG ERR]", e)
