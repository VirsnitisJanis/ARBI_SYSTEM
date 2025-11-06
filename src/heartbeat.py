import os
import time

from notify import send

STAMP = "logs/last_beat.txt"

def beat():
    with open(STAMP,"w") as f:
        f.write(str(time.time()))

def check():
    if not os.path.exists(STAMP):
        return
    t = float(open(STAMP).read())
    if time.time() - t > 90:
        send("⚠️ BOT STOPPED — no heartbeat in 90s")
