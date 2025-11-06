import os, json, time, math, csv
from datetime import datetime, timedelta, timezone
import ccxt

# Optional TG
try:
    from notify import send as tg_send
except Exception:
    def tg_send(msg): 
        print("[TG SKIP]", msg)

AI_TG = int(os.getenv("AI_TG", "1"))  # 1=ziņot TG
LOOKBACK_H = int(os.getenv("MC_LOOKBACK_H", "24"))  # 24h
PAIR = os.getenv("PAIR", "BTC/USDC")
DATA_PATH = "src/data/ai_params.json"
LOG_GLOB = os.getenv("MC_LOG", "logs/live_safe.csv")  # var būt viens fails; Stage-13/20: vari paplašināt uz patterns

# Drošas robežas
EDGE_MIN, EDGE_MAX = float(os.getenv("MC_EDGE_MIN_BPS","0.8")), float(os.getenv("MC_EDGE_MAX_BPS","5.0"))
SIZE_MIN, SIZE_MAX = float(os.getenv("MC_SIZE_MIN_BTC","0.00010")), float(os.getenv("MC_SIZE_MAX_BTC","0.00150"))

def load_ai_params():
    if not os.path.exists(DATA_PATH):
        os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
        with open(DATA_PATH,"w") as f:
            json.dump({
                "EDGE_OPEN_BPS": 2.0,
                "HEDGE_SIZE_BTC": 0.0004,
                "RISK_FACTOR": 1.0,
                "TARGET_PNL": 0.002,
                "MODEL_STATE": {}
            }, f, indent=2)
    with open(DATA_PATH) as f:
        return json.load(f)

def save_ai_params(p):
    with open(DATA_PATH,"w") as f:
        json.dump(p, f, indent=2)

def parse_fills_from_csv(path, since_ts):
    fills = []
    if not os.path.exists(path):
        return fills
    # gaidām formātu: [ts, "FILL", pnl, snapshot_json]
    with open(path, newline="") as f:
        r = csv.reader(f)
        for row in r:
            if not row: 
                continue
            try:
                ts = float(row[0])
            except Exception:
                continue
            if ts < since_ts:
                continue
            if len(row) >= 3 and str(row[1]).upper() == "FILL":
                try:
                    pnl = float(row[2])
                except Exception:
                    continue
                fills.append(pnl)
    return fills

def pnl_stats(fills):
    n = len(fills)
    if n == 0:
        return dict(n=0, avg=0.0, std=0.0, win=0.0)
    avg = sum(fills)/n
    var = sum((x-avg)**2 for x in fills)/n
    std = math.sqrt(var)
    win = sum(1 for x in fills if x>0)/n
    return dict(n=n, avg=avg, std=std, win=win)

def fetch_vol_24h(symbol):
    # izmanto Binance kā bāzi BTC/USDC; ja nav – atkāpies uz BTC/USDT
    b = ccxt.binance()
    now = int(time.time()*1000)
    since = now - LOOKBACK_H*60*60*1000
    sym = symbol
    try:
        o = b.fetch_ohlcv(sym, timeframe='5m', since=since, limit=1000)
    except Exception:
        sym = "BTC/USDT"
        o = b.fetch_ohlcv(sym, timeframe='5m', since=since, limit=1000)
    closes = [c[4] for c in o if c and c[4]]
    if len(closes) < 20:
        return dict(vol_pct=0.0, regime="NEUTRAL", bars=len(closes))
    rets = []
    for i in range(1,len(closes)):
        p0, p1 = closes[i-1], closes[i]
        if p0>0:
            rets.append((p1/p0)-1.0)
    if not rets:
        return dict(vol_pct=0.0, regime="NEUTRAL", bars=len(closes))
    # 5m loga std → annualized-ish % proxy: std*sqrt(288)*100
    std = (sum((x - (sum(rets)/len(rets)))**2 for x in rets)/len(rets))**0.5
    vol_pct = std * math.sqrt(288) * 100.0
    # režīmi – vienkārši sliekšņi
    if vol_pct >= 80.0:
        regime = "STORM"      # ļoti augsta vol
    elif vol_pct >= 40.0:
        regime = "ACTIVE"     # vidēja/augsta
    elif vol_pct >= 20.0:
        regime = "NORMAL"
    else:
        regime = "CALM"       # ļoti zema vol
    return dict(vol_pct=vol_pct, regime=regime, bars=len(closes))

def decide_new_params(params, pnl, vol):
    base_edge = float(params.get("EDGE_OPEN_BPS", 2.0))
    base_size = float(params.get("HEDGE_SIZE_BTC", 0.0004))
    risk = float(params.get("RISK_FACTOR", 1.0))

    # Pēc vol režīma
    if vol["regime"] == "STORM":
        edge = max(base_edge*1.15 + 0.2, base_edge)     # plašāks slieksnis
        size = max(SIZE_MIN, base_size*0.70)            # mazāks izmērs
        risk *= 0.98
        mode = "DEFENSIVE"
    elif vol["regime"] == "ACTIVE":
        edge = max(base_edge*1.05 + 0.05, base_edge)
        size = max(SIZE_MIN, base_size*0.85)
        mode = "GUARDED"
    elif vol["regime"] == "CALM":
        edge = max(EDGE_MIN, base_edge*0.9)             # agresīvāks (mazāks edge)
        size = min(SIZE_MAX, base_size*1.15)            # lielāks izmērs
        mode = "AGGRESSIVE"
    else:  # NORMAL
        edge = base_edge
        size = base_size
        mode = "NEUTRAL"

    # Pēc win-rate
    if pnl["n"] >= 10:
        if pnl["win"] >= 0.60 and pnl["avg"] > 0:
            edge = max(EDGE_MIN, edge*0.95)             # nedaudz vairāk darījumu
            size = min(SIZE_MAX, size*1.05)
            risk *= 1.01
        elif pnl["win"] < 0.45 or pnl["avg"] < 0:
            edge = min(EDGE_MAX, edge*1.10 + 0.05)
            size = max(SIZE_MIN, size*0.90)
            risk *= 0.99

    # Clamp
    edge = min(max(edge, EDGE_MIN), EDGE_MAX)
    size = min(max(size, SIZE_MIN), SIZE_MAX)
    risk = max(0.5, min(risk, 1.5))

    params["EDGE_OPEN_BPS"] = round(edge, 3)
    params["HEDGE_SIZE_BTC"] = float(f"{size:.8f}")
    params["RISK_FACTOR"] = round(risk, 3)
    params["MODEL_STATE"] = {
        "pnl_trades": pnl["n"],
        "pnl_avg": pnl["avg"],
        "pnl_std": pnl["std"],
        "pnl_win": pnl["win"],
        "vol_24h_pct": vol["vol_pct"],
        "vol_regime": vol["regime"],
        "updated": datetime.now(timezone.utc).isoformat()
    }
    return params, mode

def main():
    print(f"[BOOT] Stage-31 Market Context Agent — lookback={LOOKBACK_H}h")
    # 1) FILL analītika
    since_ts = time.time() - LOOKBACK_H*60*60
    fills = parse_fills_from_csv(LOG_GLOB, since_ts)
    pnl = pnl_stats(fills)

    # 2) Volatilitāte no Binance OHLCV
    vol = fetch_vol_24h(PAIR)

    # 3) Lēmumi
    params = load_ai_params()
    new_params, mode = decide_new_params(params, pnl, vol)
    save_ai_params(new_params)

    # 4) Izvade
    summary = (
        "🧭 Market-Aware AI Update\n"
        f"Lookback: {LOOKBACK_H}h | Fills: {pnl['n']}\n"
        f"AvgPnL: {pnl['avg']:.6f} | Win: {pnl['win']:.2%} | Std: {pnl['std']:.6f}\n"
        f"BTC 24h Vol: {vol['vol_pct']:.2f}% | Regime: {vol['regime']} (bars={vol['bars']})\n\n"
        f"Mode: *{mode}*\n"
        f"➡ EDGE_OPEN_BPS → {new_params['EDGE_OPEN_BPS']}\n"
        f"➡ HEDGE_SIZE_BTC → {new_params['HEDGE_SIZE_BTC']}\n"
        f"➡ RISK_FACTOR → {new_params['RISK_FACTOR']}\n"
        f"Updated: {new_params['MODEL_STATE']['updated']}"
    )
    print(summary)
    if AI_TG == 1:
        try:
            tg_send(summary)
        except Exception as e:
            print("[TG ERROR]", e)

if __name__ == "__main__":
    main()
