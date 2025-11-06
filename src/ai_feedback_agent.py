import os, csv, json, statistics, math, time
from datetime import datetime
from notify import send  # izmanto tavu Telegram sūtītāju

DATA_PATH = "src/data/ai_params.json"
LOG_PATH = "logs/live_safe.csv"
LOOKBACK_H = int(os.getenv("AI_LOOKBACK_H", 24))
MIN_TRADES = 5
AI_INTERVAL_H = int(os.getenv("AI_INTERVAL_H", 12))  # cik bieži sūtīt Telegram

def load_pnl():
    """Nolasa pēdējos PnL datus no logiem."""
    if not os.path.exists(LOG_PATH):
        print("[WARN] Nav atrasts logs:", LOG_PATH)
        return []
    rows = []
    with open(LOG_PATH) as f:
        for r in csv.reader(f, delimiter="|"):
            try:
                ts = float(r[0].strip())
                pnl = float(r[-2].strip())
                rows.append((ts, pnl))
            except Exception:
                continue
    rows = rows[-500:]
    return rows

def analyze(rows):
    """Analizē peļņu, risku un tendenci."""
    if len(rows) < MIN_TRADES:
        return {"avg": 0.0, "vol": 0.0, "trend": 0.0}

    pnls = [p for _, p in rows]
    avg = statistics.mean(pnls)
    vol = statistics.stdev(pnls) if len(pnls) > 1 else 0.0
    trend = (statistics.mean(pnls[-10:]) - avg) / (abs(avg) + 1e-9)
    return {"avg": avg, "vol": vol, "trend": trend}

def load_ai_params():
    if not os.path.exists(DATA_PATH):
        return {}
    with open(DATA_PATH) as f:
        return json.load(f)

def save_ai_params(params):
    with open(DATA_PATH, "w") as f:
        json.dump(params, f, indent=2)

def adapt_parameters(metrics, params):
    """AI adaptīvi koriģē stratēģijas iestatījumus."""
    avg, vol, trend = metrics["avg"], metrics["vol"], metrics["trend"]

    if avg > params["TARGET_PNL"] and trend > 0:
        params["EDGE_OPEN_BPS"] = round(params["EDGE_OPEN_BPS"] * 0.95, 2)
        params["HEDGE_SIZE_BTC"] = round(params["HEDGE_SIZE_BTC"] * 1.10, 6)
    elif vol > abs(avg) * 3 or avg < 0:
        params["EDGE_OPEN_BPS"] = round(params["EDGE_OPEN_BPS"] * 1.10, 2)
        params["HEDGE_SIZE_BTC"] = round(params["HEDGE_SIZE_BTC"] * 0.90, 6)

    params["EDGE_OPEN_BPS"] = max(1.0, min(params["EDGE_OPEN_BPS"], 5.0))
    params["HEDGE_SIZE_BTC"] = max(0.0001, min(params["HEDGE_SIZE_BTC"], 0.001))
    params["MODEL_STATE"] = metrics
    return params

def main():
    print(f"[BOOT] Stage-28 AI Feedback Agent — lookback={LOOKBACK_H}h")
    rows = load_pnl()
    metrics = analyze(rows)
    params = load_ai_params()

    print(f"[ANALYZE] trades={len(rows)} avg={metrics['avg']:.6f} vol={metrics['vol']:.6f} trend={metrics['trend']:.3f}")
    updated = adapt_parameters(metrics, params)
    save_ai_params(updated)

    msg = (
        f"🤖 *AI Feedback Update*\n"
        f"Trades analyzed: {len(rows)}\n"
        f"Avg PnL: {metrics['avg']:.6f}\n"
        f"Volatility: {metrics['vol']:.6f}\n"
        f"Trend: {metrics['trend']:.3f}\n"
        f"\n"
        f"➡️ EDGE_OPEN_BPS → *{updated['EDGE_OPEN_BPS']}*\n"
        f"➡️ HEDGE_SIZE_BTC → *{updated['HEDGE_SIZE_BTC']}*\n"
        f"\nNext check in ~{AI_INTERVAL_H}h"
    )
    print(msg)
    send(msg)

if __name__ == "__main__":
    main()
