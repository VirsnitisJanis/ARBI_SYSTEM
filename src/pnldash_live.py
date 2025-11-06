import os, time, csv, glob, json
from datetime import datetime
from utils.balances import snapshot
try:
    from notify import send
except Exception:
    def send(msg): print("[TG SKIP]", msg)

LOG_GLOB = os.getenv("DASH_LOGS", "logs/live_*.csv")
REFRESH = float(os.getenv("DASH_REFRESH_S", "10"))
SEND_TG = os.getenv("DASH_SEND_TG", "1") == "1"

def read_pnls():
    data = []
    for path in sorted(glob.glob(LOG_GLOB)):
        pnl, fills, last_fill_ts = 0.0, 0, 0
        try:
            with open(path, newline="") as f:
                r = csv.reader(f)
                for row in r:
                    if len(row)>=3 and row[1]=="FILL":
                        fills += 1
                        try: pnl += float(row[2])
                        except: pass
                        last_fill_ts = float(row[0])
        except FileNotFoundError:
            continue
        data.append({"file":path, "fills":fills, "pnl":pnl, "last":last_fill_ts})
    return data

def fmt_bar(pnl):
    """Vienkāršs ASCII bar grafiks"""
    length = 40
    scaled = max(min(int(pnl*2000)+length//2, length-1), 0)
    line = [" "]*length
    line[length//2] = "|"
    if pnl>0:
        for i in range(length//2, scaled): line[i] = "+"
    else:
        for i in range(scaled, length//2): line[i] = "-"
    return "".join(line)

def print_table(rows, total):
    os.system("clear")
    print("📊 REAL-TIME PnL DASHBOARD")
    print("="*80)
    print(f"Time: {datetime.utcnow().isoformat(timespec='seconds')}Z")
    print(f"Total Fills: {total['fills']:>4} | Total PnL: {total['pnl']:.6f} USD\n")
    print(f"{'File':50} {'Fills':>5} {'PnL':>10} {'ΔGraph'}")
    print("-"*80)
    for r in rows:
        print(f"{r['file'][:50]:50} {r['fills']:>5} {r['pnl']:>10.6f} {fmt_bar(r['pnl'])}")
    print("-"*80)
    print("Wallet Snapshot:", json.dumps(snapshot()))
    print("="*80)

def compute_intervals(rows):
    """sagatavo PnL izmaiņas 5/15/60 min intervāliem"""
    now = time.time()
    stats = {"5min":0,"15min":0,"60min":0}
    for r in rows:
        if now - r["last"] < 300: stats["5min"] += r["pnl"]
        if now - r["last"] < 900: stats["15min"] += r["pnl"]
        if now - r["last"] < 3600: stats["60min"] += r["pnl"]
    return stats

def main():
    print("[BOOT] Real-Time Dashboard (Stage-14)")
    while True:
        rows = read_pnls()
        total = {"fills":sum(r["fills"] for r in rows),
                 "pnl":sum(r["pnl"] for r in rows)}
        print_table(rows, total)

        intervals = compute_intervals(rows)
        msg = (
            f"📈 PnL Summary\n"
            f"Total: {total['pnl']:.6f} USD ({total['fills']} fills)\n"
            f"Δ5min={intervals['5min']:.6f} | Δ15min={intervals['15min']:.6f} | Δ60min={intervals['60min']:.6f}\n"
            f"Snapshot: {json.dumps(snapshot())}"
        )
        if SEND_TG:
            try: send(msg)
            except Exception as e: print("[TG ERROR]", e)
        time.sleep(REFRESH)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("exit")
