import os, csv, time, glob, json
from datetime import datetime
from utils.balances import snapshot
try:
    from notify import send
except Exception:
    def send(msg): print("[TG SKIP]", msg)

LOG_GLOB = os.getenv("DASH_LOGS", "logs/live_*.csv")
REFRESH  = float(os.getenv("DASH_REFRESH_S","15"))
SEND_SUM = os.getenv("DASH_SEND_TG","1") == "1"

def read_pnls():
    totals = {"fills":0, "pnl":0.0, "files":{}}
    for path in glob.glob(LOG_GLOB):
        fills = 0
        pnl   = 0.0
        try:
            with open(path, newline="") as f:
                r = csv.reader(f)
                for row in r:
                    # FILL rindas pie mums: [ts, "FILL", pnl, snapshot_dict]
                    if len(row)>=3 and row[1]=="FILL":
                        fills += 1
                        try:
                            pnl += float(row[2])
                        except: pass
        except FileNotFoundError:
            continue
        totals["files"][path] = {"fills":fills,"pnl":pnl}
        totals["fills"] += fills
        totals["pnl"]   += pnl
    return totals

def fmt_table(tot):
    lines = []
    lines.append(f"[{datetime.utcnow().isoformat(timespec='seconds')}Z]  TOTAL fills={tot['fills']}  PnL={tot['pnl']:.6f}")
    for k,v in sorted(tot["files"].items()):
        lines.append(f"- {k}: fills={v['fills']}  pnl={v['pnl']:.6f}")
    lines.append(f"Snapshot: {json.dumps(snapshot())}")
    return "\n".join(lines)

def main():
    print("[BOOT] PnL Dashboard")
    while True:
        tot = read_pnls()
        view = fmt_table(tot)
        print(view, flush=True)
        if SEND_SUM:
            try:
                send("📊 PnL Dashboard\n" + view)
            except Exception as e:
                print("[TG ERROR]", e)
        time.sleep(REFRESH)

if __name__=="__main__":
    main()
