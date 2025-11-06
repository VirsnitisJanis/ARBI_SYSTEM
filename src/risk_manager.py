import json
import os
import time

from notify import send

STATE_FILE = "logs/risk_state.json"
MAX_DRAWDOWN_PCT = float(os.getenv("MAX_DRAWDOWN_PCT", "15.0"))
AUTO_SCALE_UP_PCT = float(os.getenv("AUTO_SCALE_UP_PCT", "5.0"))
AUTO_SCALE_DOWN_PCT = float(os.getenv("AUTO_SCALE_DOWN_PCT", "5.0"))
BASE_NOTIONAL = float(os.getenv("BASE_NOTIONAL_USDC", "25"))
UPDATE_INTERVAL_S = int(os.getenv("RISK_UPDATE_INTERVAL_S", "600"))

def read_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"equity": 200.0, "max_equity": 200.0, "notional": BASE_NOTIONAL}

def write_state(s):
    with open(STATE_FILE, "w") as f:
        json.dump(s, f, indent=2)

def read_total_pnl():
    try:
        import csv
        with open("logs/daily_pnl.csv") as f:
            last = list(csv.reader(f))[-1]
            return float(last[2])
    except Exception:
        return 0.0

def compute():
    s = read_state()
    day_pnl = read_total_pnl()
    s["equity"] += day_pnl
    if s["equity"] > s["max_equity"]:
        s["max_equity"] = s["equity"]

    drawdown = 100 * (1 - s["equity"] / s["max_equity"])

    # Downscale on loss
    if drawdown >= MAX_DRAWDOWN_PCT:
        s["notional"] = max(BASE_NOTIONAL * 0.5, s["notional"] * (1 - AUTO_SCALE_DOWN_PCT/100))
        send(f"⚠️ DRAWDOWN {drawdown:.2f}% — reducing notional to {s['notional']:.2f}")
        s["equity"] = s["max_equity"] * (1 - MAX_DRAWDOWN_PCT/100)

    # Upscale after profit day
    elif day_pnl > 0:
        s["notional"] *= (1 + AUTO_SCALE_UP_PCT/100)
        send(f"📈 PROFIT DAY +{day_pnl:.4f} — increasing notional to {s['notional']:.2f}")

    write_state(s)
    print(f"[RISK] equity={s['equity']:.2f} drawdown={drawdown:.2f}% notional={s['notional']:.2f}")

def loop():
    while True:
        compute()
        time.sleep(UPDATE_INTERVAL_S)

if __name__ == "__main__":
    try:
        send("🛡 Risk manager active")
        loop()
    except KeyboardInterrupt:
        print("exit")
