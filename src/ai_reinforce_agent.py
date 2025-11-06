import os, json, time, glob, csv, math
from datetime import datetime, timedelta

# Optional TG notify
try:
    from notify import send
except Exception:
    def send(_): pass

# ----------------------------
# Config (ENV ar drošiem noklusējumiem)
# ----------------------------
LOOKBACK_H       = float(os.getenv("RL_LOOKBACK_H", "24"))
EDGE_MIN_BPS     = float(os.getenv("RL_EDGE_MIN_BPS", "0.8"))
EDGE_MAX_BPS     = float(os.getenv("RL_EDGE_MAX_BPS", "5.0"))
EDGE_STEP_BPS    = float(os.getenv("RL_EDGE_STEP_BPS","0.15"))

SIZE_MIN_BTC     = float(os.getenv("RL_SIZE_MIN_BTC","0.00010"))
SIZE_MAX_BTC     = float(os.getenv("RL_SIZE_MAX_BTC","0.00100"))
SIZE_STEP_BTC    = float(os.getenv("RL_SIZE_STEP_BTC","0.00005"))

TARGET_WIN       = float(os.getenv("RL_TARGET_WIN",  "0.58"))   # vēlamā uzvaru attiecība
TARGET_STD       = float(os.getenv("RL_TARGET_STD",  "0.003"))  # vēlamā PnL std (USD)
AI_TG            = os.getenv("AI_TG","0") == "1"

AI_DIR           = "src/data"
AI_PARAMS_PATH   = os.path.join(AI_DIR, "ai_params.json")
AI_RL_STATE_PATH = os.path.join(AI_DIR, "rl_state.json")

LOG_PATTERNS     = [
    "logs/live_safe.csv",
    "logs/live_*.csv",           # multi-venue
    "logs/*cross*.csv",          # ja FILL tiek rakstīti citos
]

def _ensure_dirs():
    os.makedirs(AI_DIR, exist_ok=True)

def _now_ts():
    return time.time()

def _load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default

def _save_json(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)

def _parse_fill_line(line:str):
    """
    Mēģina izvilkt (ts, pnl_usd) no dažādiem formātiem.
    1) mūsu live_safe.csv: [epoch,"FILL",pnl,{...}]
    2) citi csv, kur FILL var būt citā laukā — meklējam ",FILL," rakstu.
    """
    if "FILL" not in line:
        return None
    # Pamēģinam CSV parseri — robusti pret komatiem JSON snapshotā
    try:
        row = next(csv.reader([line]))
    except Exception:
        return None

    # Meklējam "FILL" indeksu
    idxs = [i for i,v in enumerate(row) if isinstance(v,str) and v.strip().upper()=="FILL"]
    if not idxs:
        return None

    # Heuristika: ts meklējam pirmajā laukā, pnl blakus "FILL"
    ts = None
    pnl = None

    # epoch ts pirmajā laukā?
    try:
        ts_candidate = float(row[0])
        if 1e9 < ts_candidate < 2e10:  # epoch seconds
            ts = ts_candidate
    except Exception:
        ts = None

    # PnL blakus FILL (pirms vai pēc)
    i = idxs[0]
    # pēc FILL
    for j in (i-1, i+1, i+2):
        if 0 <= j < len(row):
            try:
                pnl_candidate = float(row[j])
                pnl = pnl_candidate
                break
            except Exception:
                pass

    if ts is None or pnl is None:
        return None
    return (ts, pnl)

def _collect_fills(since_ts: float):
    fills = []
    paths = []
    for pat in LOG_PATTERNS:
        paths.extend(glob.glob(pat))

    seen = set()
    for p in sorted(set(paths)):
        try:
            with open(p,"r",encoding="utf-8",errors="ignore") as f:
                for line in f:
                    if "FILL" not in line:
                        continue
                    parsed = _parse_fill_line(line)
                    if not parsed:
                        continue
                    ts, pnl = parsed
                    if ts >= since_ts:
                        key = (p, ts, pnl)
                        if key not in seen:
                            seen.add(key)
                            fills.append({"file":p,"ts":ts,"pnl":pnl})
        except Exception:
            continue
    return sorted(fills, key=lambda x: x["ts"])

def _stats(fills):
    n = len(fills)
    if n == 0:
        return dict(n=0, win_rate=0.0, avg=0.0, std=0.0, sum=0.0)
    vals = [x["pnl"] for x in fills]
    s = sum(vals)
    avg = s / n
    var = sum((v-avg)**2 for v in vals)/n
    std = math.sqrt(var)
    win = sum(1 for v in vals if v > 0)/n
    return dict(n=n, win_rate=win, avg=avg, std=std, sum=s)

def _clip(v, lo, hi):
    return max(lo, min(hi, v))

def main():
    _ensure_dirs()
    params = _load_json(AI_PARAMS_PATH, {
        "EDGE_OPEN_BPS": 2.0,
        "HEDGE_SIZE_BTC": 0.0004,
        "RISK_FACTOR": 1.0,
        "TARGET_PNL": 0.002,
        "MODEL_STATE": {}
    })
    rl_state = _load_json(AI_RL_STATE_PATH, {
        "last_update": None,
        "history": []
    })

    lookback_ts = _now_ts() - LOOKBACK_H*3600
    fills = _collect_fills(lookback_ts)
    st = _stats(fills)

    # Reinforcement loģika (vienkārša, robusta):
    edge = float(params.get("EDGE_OPEN_BPS", 2.0))
    size = float(params.get("HEDGE_SIZE_BTC", 0.0004))
    risk = float(params.get("RISK_FACTOR", 1.0))

    # 1) EDGE pielāgošana pēc win-rate un avg
    if st["n"] >= 10:
        if st["win_rate"] < TARGET_WIN or st["avg"] <= 0:
            edge += EDGE_STEP_BPS      # kļūst konservatīvāks
        elif st["win_rate"] > (TARGET_WIN + 0.08) and st["avg"] > 0:
            edge -= EDGE_STEP_BPS/2.0  # pamazām agresīvāks
        edge = _clip(edge, EDGE_MIN_BPS, EDGE_MAX_BPS)

    # 2) SIZE pielāgošana pēc volatilitātes
    if st["n"] >= 10:
        if st["std"] > TARGET_STD:
            size -= SIZE_STEP_BTC      # mazāks risks
        elif st["std"] < TARGET_STD/2.0 and st["win_rate"] >= TARGET_WIN:
            size += SIZE_STEP_BTC/2.0  # nedaudz lielāks izmērs
        size = _clip(size, SIZE_MIN_BTC, SIZE_MAX_BTC)

    # 3) Risk factor (bonus/penalty) — vienkāršs
    if st["n"] >= 10:
        if st["avg"] > 0 and st["win_rate"] >= TARGET_WIN:
            risk = _clip(risk * 1.02, 0.5, 2.0)
        else:
            risk = _clip(risk * 0.98, 0.5, 2.0)

    # Saglabā
    params["EDGE_OPEN_BPS"] = round(edge, 4)
    params["HEDGE_SIZE_BTC"] = round(size, 8)
    params["RISK_FACTOR"] = round(risk, 4)
    params.setdefault("MODEL_STATE", {})
    params["MODEL_STATE"].update({
        "lookback_h": LOOKBACK_H,
        "n": st["n"], "win_rate": st["win_rate"],
        "avg": st["avg"], "std": st["std"], "sum": st["sum"]
    })
    _save_json(AI_PARAMS_PATH, params)

    rl_state["last_update"] = datetime.utcnow().isoformat()
    rl_state["history"].append({
        "ts": rl_state["last_update"],
        "stats": st,
        "params": {
            "EDGE_OPEN_BPS": params["EDGE_OPEN_BPS"],
            "HEDGE_SIZE_BTC": params["HEDGE_SIZE_BTC"],
            "RISK_FACTOR": params["RISK_FACTOR"]
        }
    })
    # saglabā tikai pēdējās 200 rindas
    rl_state["history"] = rl_state["history"][-200:]
    _save_json(AI_RL_STATE_PATH, rl_state)

    # Izvade + TG
    msg = []
    msg.append("🧪 Stage-30 Reinforcement Update")
    msg.append(f"Lookback: {LOOKBACK_H:.0f}h | trades={st['n']}")
    msg.append(f"Win-rate: {st['win_rate']:.2%}")
    msg.append(f"AvgPnL: {st['avg']:.6f} | Std: {st['std']:.6f} | Sum: {st['sum']:.4f}")
    msg.append("")
    msg.append(f"➡ EDGE_OPEN_BPS → {params['EDGE_OPEN_BPS']}")
    msg.append(f"➡ HEDGE_SIZE_BTC → {params['HEDGE_SIZE_BTC']}")
    msg.append(f"➡ RISK_FACTOR → {params['RISK_FACTOR']}")
    out = "\n".join(msg)

    print(out)
    if AI_TG:
        try:
            send(out)
        except Exception as e:
            print("[TG ERROR]", e)

if __name__ == "__main__":
    main()
