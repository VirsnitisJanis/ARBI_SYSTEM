import os, glob, csv, statistics, time
from notify import send

LOOKBACK_H = int(os.getenv("PNL_LOOKBACK_H", "24"))
EDGE_MIN = float(os.getenv("EDGE_MIN", "0.8"))
EDGE_MAX = float(os.getenv("EDGE_MAX", "3.0"))
HEDGE_MIN = float(os.getenv("HEDGE_MIN", "0.0003"))
HEDGE_MAX = float(os.getenv("HEDGE_MAX", "0.0010"))
ADAPT_RATE = float(os.getenv("ADAPT_RATE", "0.2"))

def read_pnls():
    files = glob.glob("logs/*.csv")
    pnls = []
    for f in files:
        with open(f) as fp:
            for row in csv.reader(fp, delimiter=','):
                if len(row) >= 3 and "FILL" in row[2]:
                    try: pnls.append(float(row[1]))
                    except: pass
    return pnls[-100:]

def adjust_param(val, delta, low, high):
    return max(low, min(high, val + delta))

def main():
    print(f"[BOOT] Stage-24 PnL Intelligence — lookback={LOOKBACK_H}h")
    pnls = read_pnls()
    avg = statistics.mean(pnls) if pnls else 0
    total = sum(pnls)
    print(f"[ANALYZE] fills={len(pnls)} avgPnL={avg:.6f} total={total:.4f}")

    # Dinamiski pielāgo EDGE un HEDGE
    edge = float(os.getenv("EDGE_OPEN_BPS", "2.0"))
    hedge = float(os.getenv("HEDGE_SIZE_BTC", "0.0004"))
    if total > 0:
        edge = adjust_param(edge, -ADAPT_RATE, EDGE_MIN, EDGE_MAX)
        hedge = adjust_param(hedge, ADAPT_RATE*hedge, HEDGE_MIN, HEDGE_MAX)
    else:
        edge = adjust_param(edge, ADAPT_RATE, EDGE_MIN, EDGE_MAX)
        hedge = adjust_param(hedge, -ADAPT_RATE*hedge, HEDGE_MIN, HEDGE_MAX)

    msg = (f"🤖 PnL Intelligence Update\n"
           f"PnL (24 h): {total:.4f}\nAvg per trade: {avg:.6f}\n"
           f"New EDGE_OPEN_BPS: {edge:.2f}\nNew HEDGE_SIZE_BTC: {hedge:.6f}")
    print(msg)
    send(msg)

    # Saglabā atjauninātos iestatījumus .env.local
    with open(".env.local", "a") as f:
        f.write(f"\n# Auto-update {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"EDGE_OPEN_BPS={edge}\nHEDGE_SIZE_BTC={hedge}\n")

if __name__ == "__main__":
    main()
