import asyncio
import csv
import os
import time
from datetime import datetime

from notify import send

LOG = "logs/pnl.csv"
SUMMARY_INTERVAL_S = int(os.getenv("SUMMARY_INTERVAL_S", "600"))  # ik 10 min
DAY_PNL_FILE = "logs/daily_pnl.csv"

def read_pnl():
    if not os.path.exists(LOG):
        return []
    rows = []
    with open(LOG) as f:
        for r in csv.reader(f):
            if len(r) >= 3 and r[1] == "FILL":
                try:
                    ts = float(r[0])
                    pnl = float(r[2])
                    rows.append((ts, pnl))
                except: pass
    return rows

def summarize():
    rows = read_pnl()
    if not rows:
        return None
    now = time.time()
    day_rows = [r for r in rows if now - r[0] < 86400]
    day_sum = sum(r[1] for r in day_rows)
    total_sum = sum(r[1] for r in rows)
    return len(day_rows), day_sum, total_sum

async def loop():
    while True:
        summary = summarize()
        if summary:
            n, day_pnl, total = summary
            msg = (
                f"📈 *PnL Summary*\n"
                f"Trades today: {n}\n"
                f"Day PnL: {day_pnl:.6f} USDC\n"
                f"Total PnL (all time): {total:.6f} USDC"
            )
            print(msg)
            send(msg)
            with open(DAY_PNL_FILE, "a", newline="") as f:
                csv.writer(f).writerow([datetime.utcnow(), n, day_pnl, total])
        else:
            send("📭 No trades yet today.")
        await asyncio.sleep(SUMMARY_INTERVAL_S)

if __name__ == "__main__":
    try:
        asyncio.run(loop())
    except KeyboardInterrupt:
        print("exit")
