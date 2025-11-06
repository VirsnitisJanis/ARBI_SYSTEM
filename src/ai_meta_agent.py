import os, csv, json, statistics, math, time
from datetime import datetime
from notify import send

LOG_PATH = "logs/live_safe.csv"
AI_PARAMS_PATH = "src/data/ai_params.json"
META_PATH = "src/data/meta_state.json"
LOOKBACK_H = int(os.getenv("META_LOOKBACK_H", 48))
MIN_TRADES = 10

def load_history():
    if not os.path.exists(LOG_PATH):
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
    return rows[-1000:]

def compute_indicators(rows):
    if len(rows) < MIN_TRADES:
        return {"avg": 0.0, "vol": 0.0, "trend": 0.0, "sharpe": 0.0}
    pnls = [p for _, p in rows]
    avg = statistics.mean(pnls)
    vol = statistics.stdev(pnls) if len(pnls) > 1 else 0
    trend = (statistics.mean(pnls[-20:]) - avg) / (abs(avg) + 1e-9)
    sharpe = avg / (vol + 1e-9)
    return {"avg": avg, "vol": vol, "trend": trend, "sharpe": sharpe}

def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def meta_learn(meta, indicators):
    # Pievieno jaunu datu punktu meta modelim
    hist = meta.get("history", [])
    hist.append({
        "t": time.time(),
        "avg": indicators["avg"],
        "vol": indicators["vol"],
        "trend": indicators["trend"],
        "sharpe": indicators["sharpe"]
    })
    hist = hist[-200:]  # saglabā pēdējos 200 punktus
    meta["history"] = hist

    # Meta-trend analīze
    sharpe_vals = [h["sharpe"] for h in hist]
    if len(sharpe_vals) > 10:
        mean_s = statistics.mean(sharpe_vals)
        trend_s = (statistics.mean(sharpe_vals[-10:]) - mean_s)
    else:
        mean_s, trend_s = 0, 0

    # Lēmums — agresīvs vai konservatīvs režīms
    mode = "neutral"
    if trend_s > 0.01 and indicators["trend"] > 0:
        mode = "aggressive"
    elif trend_s < -0.01 or indicators["avg"] < 0:
        mode = "conservative"

    meta["mode"] = mode
    meta["meta_trend"] = trend_s
    meta["last_update"] = datetime.utcnow().isoformat()
    return meta

def apply_mode(params, mode):
    if mode == "aggressive":
        params["EDGE_OPEN_BPS"] = max(1.0, round(params["EDGE_OPEN_BPS"] * 0.9, 2))
        params["HEDGE_SIZE_BTC"] = min(0.001, round(params["HEDGE_SIZE_BTC"] * 1.15, 6))
        params["RISK_FACTOR"] = min(1.5, round(params.get("RISK_FACTOR",1.0) * 1.1, 2))
    elif mode == "conservative":
        params["EDGE_OPEN_BPS"] = min(5.0, round(params["EDGE_OPEN_BPS"] * 1.1, 2))
        params["HEDGE_SIZE_BTC"] = max(0.0001, round(params["HEDGE_SIZE_BTC"] * 0.85, 6))
        params["RISK_FACTOR"] = max(0.5, round(params.get("RISK_FACTOR",1.0) * 0.9, 2))
    return params

def main():
    print("[BOOT] Stage-29 Meta-Learning Agent — 48h lookback")
    rows = load_history()
    indicators = compute_indicators(rows)
    params = load_json(AI_PARAMS_PATH, {})
    meta = load_json(META_PATH, {})

    meta = meta_learn(meta, indicators)
    new_params = apply_mode(params, meta.get("mode", "neutral"))
    save_json(AI_PARAMS_PATH, new_params)
    save_json(META_PATH, meta)

    msg = (
        f"🧠 *Stage-29 Meta-Learning Update*\n"
        f"Avg PnL: {indicators['avg']:.6f}\n"
        f"Volatility: {indicators['vol']:.6f}\n"
        f"Trend: {indicators['trend']:.3f}\n"
        f"Sharpe: {indicators['sharpe']:.3f}\n"
        f"\n"
        f"Meta-Trend: {meta['meta_trend']:.3f}\n"
        f"Mode: *{meta['mode'].upper()}*\n"
        f"\n"
        f"➡️ EDGE_OPEN_BPS → {new_params['EDGE_OPEN_BPS']}\n"
        f"➡️ HEDGE_SIZE_BTC → {new_params['HEDGE_SIZE_BTC']}\n"
        f"➡️ RISK_FACTOR → {new_params['RISK_FACTOR']}\n"
        f"Updated: {meta['last_update']}"
    )
    print(msg)
    send(msg)

if __name__ == "__main__":
    main()
