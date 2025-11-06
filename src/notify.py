import os

from telegram import Bot

TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT = os.getenv("TG_CHAT")

bot = Bot(token=TG_TOKEN)

def send(msg: str):
    try:
        bot.send_message(chat_id=TG_CHAT, text=msg[:4000])
    except Exception as e:
        print("[TG ERROR]", e)
