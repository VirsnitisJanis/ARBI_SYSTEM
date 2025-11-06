import os
from telegram import Bot
from pathlib import Path

# Automātiski ielādē TG datus no .env.local, ja nav ENV
env_file = Path(".env.local")
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            if line.strip() and not line.startswith("#"):
                key, _, val = line.strip().partition("=")
                if key not in os.environ:
                    os.environ[key] = val

TG_TOKEN = os.getenv("TG_TOKEN") or os.getenv("TG_BOT_TOKEN") or ""
TG_CHAT = os.getenv("TG_CHAT") or os.getenv("TG_CHAT_ID") or ""

bot = Bot(token=TG_TOKEN) if TG_TOKEN else None

def send(msg: str):
    if not TG_TOKEN or not TG_CHAT:
        print("[WARN] Telegram not configured.")
        return
    try:
        bot.send_message(chat_id=TG_CHAT, text=msg[:4000])
    except Exception as e:
        print("[TG ERROR]", e)
