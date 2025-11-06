import os, time, requests, csv
from pathlib import Path
from datetime import datetime, timedelta

BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
CHAT_ID = os.getenv("TG_CHAT_ID")

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

# === CORE NOTIFICATIONS ===

def send_trade_fill(pair, venue_a, venue_b, pnl, wallets):
    """Sūta tikai, ja darījums reāli izpildīts"""
    msg = (
        f"✅ HEDGE FILL\n"
        f"Pair: {pair}\n"
        f"VenueA: {venue_a}\n"
        f"VenueB: {venue_b}\n"
        f"PnL: {round(pnl, 6)}\n"
        f"Wallets: {wallets}"
    )
    send(msg)
    Path("/tmp/arbi_last_trade.txt").write_text(str(time.time()))

def send_no_trades_today():
    today = datetime.utcnow().strftime("%Y-%m-%d")
    stamp = Path(f"/tmp/arbi_notrades_{today}.txt")
    last_trade = Path("/tmp/arbi_last_trade.txt")

    if last_trade.exists():
        ts = float(last_trade.read_text())
        if datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d") == today:
            return
    if not stamp.exists():
        send("📭 No trades yet today.")
        stamp.write_text("sent")

def send_heartbeat(status: str):
    """Sūta SYSTEM ALIVE max reizi 4 stundās"""
    last = Path("/tmp/arbi_heartbeat.txt")
    now = time.time()
    if last.exists() and now - float(last.read_text()) < 14400:
        return
    last.write_text(str(now))
    send(f"💗 SYSTEM ALIVE — {status}")

def send_error(msg: str):
    send(f"❌ ERROR: {msg}")

def send_halt(reason: str):
    send(f"⛔ SYSTEM HALT — {reason}")

# === DAILY PNL SUMMARY ===
def send_daily_summary():
    today = datetime.utcnow().strftime("%Y-%m-%d")
    stamp = Path(f"/tmp/arbi_summary_{today}.txt")
    if stamp.exists():
        return
    log_files = ["logs/live_safe.csv", "logs/cross_hedge.csv"]
    total_pnl = 0.0
    total_trades = 0
    for file in log_files:
        if not Path(file).exists():
            continue
        try:
            with open(file) as f:
                reader = csv.reader(f, delimiter="|")
                for row in reader:
                    if len(row) < 6:
                        continue
                    try:
                        pnl = float(row[5])
                        total_pnl += pnl
                        total_trades += 1
                    except:
                        pass
        except Exception as e:
            print("[PNL READ ERR]", e)
    msg = f"📊 DAILY SUMMARY — {today}\nTrades: {total_trades}\nTotal PnL: {round(total_pnl,4)} USD"
    send(msg)
    stamp.write_text("sent")

# === AUTO CYCLE ===
def auto_cycle():
    send_heartbeat("all agents running.")
    send_no_trades_today()
    now = datetime.utcnow()
    if now.hour == 23 and now.minute >= 55:
        send_daily_summary()
