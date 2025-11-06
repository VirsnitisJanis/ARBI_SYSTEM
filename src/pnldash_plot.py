import os, time, csv, glob, json
import matplotlib.pyplot as plt
from datetime import datetime
from utils.balances import snapshot
try:
    from notify import send
except Exception:
    def send(msg): print("[TG SKIP]", msg)

LOG_GLOB = os.getenv("DASH_LOGS", "logs/live_*.csv")
REFRESH = float(os.getenv("DASH_REFRESH_S", "30"))
SEND_TG = os.getenv("DASH_SEND_TG", "1") == "1"
ALERT_NEG = float(os.getenv("ALERT_NEG_USD", "-0.00"))
ALERT_POS = float(os.getenv("ALERT_POS_USD", "0.30"))

def read_pnl_history():
    pts = []
    for path in sorted(glob.glob(LOG_GLOB)):
        try:
            with open(path, newline="") as f:
                r = csv.reader(f)
                for row in r:
                    if len(row)>=3 and row[1]=="FILL":
                        pts.append((float(row[0]), float(row[2])))
        except: pass
    pts.sort()
    out, pnl = [], 0.0
    for ts, v in pts:
        pnl += v
        out.append((ts,pnl))
    return out

def check_alert(pnl_total):
    if pnl_total < ALERT_NEG:
        send(f"⚠️ ALERT: PnL critical ({pnl_total:.4f} USD)")
    elif pnl_total > ALERT_POS:
        send(f"💰 ALERT: Profit target reached ({pnl_total:.4f} USD)")

def main():
    print("[BOOT] Stage-15 PnL Plot Dashboard")
    plt.ion()
    fig, ax = plt.subplots(figsize=(8,4))
    while True:
        data = read_pnl_history()
        if not data:
            time.sleep(REFRESH)
            continue
        xs = [datetime.utcfromtimestamp(t) for t,_ in data]
        ys = [y for _,y in data]
        pnl_total = ys[-1]
        ax.clear()
        ax.plot(xs, ys, linewidth=1.8)
        ax.axhline(0, color="gray", linestyle="--", linewidth=0.8)
        ax.set_title(f"Real-Time PnL (USD) — {pnl_total:.6f}")
        ax.set_xlabel("UTC Time")
        ax.set_ylabel("PnL (USD)")
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.pause(0.01)
        check_alert(pnl_total)
        if SEND_TG:
            msg = (
                f"📈 PnL Update {datetime.utcnow().isoformat(timespec='seconds')}Z\n"
                f"Total PnL = {pnl_total:.6f} USD\n"
                f"Snapshot: {json.dumps(snapshot())}"
            )
            send(msg)
        time.sleep(REFRESH)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("exit")
