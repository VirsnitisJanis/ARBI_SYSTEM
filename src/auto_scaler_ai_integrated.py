import os, json, time, signal, subprocess, itertools, hashlib
from pathlib import Path

# ------------ Config / ENV ------------
AI_PARAMS_PATH = Path("src/data/ai_params.json")
PAIRS_JSON     = Path("pairs.json")

ROUTER_SCRIPT = os.getenv("ROUTER_SCRIPT", "src/smart_hedge_router_protected.py")
USE_EXCHANGES = [x.strip() for x in os.getenv("USE_EXCHANGES","binance,kucoin,kraken").split(",") if x.strip()]
MAX_AGENTS    = int(os.getenv("MAX_AGENTS","4"))
PAIR_BLACKLIST= set([x.strip() for x in os.getenv("PAIR_BLACKLIST","").split(",") if x.strip()])

REFRESH_SEC   = int(os.getenv("AI_REFRESH_SEC","300"))   # cik bieži pārbaudīt AI parametrus
SEND_TG       = os.getenv("SCALER_TG","1") == "1"

# ------------ Telegram notify ------------
def send(msg: str):
    try:
        from notify import send as tg_send
        if SEND_TG:
            tg_send(msg)
    except Exception as e:
        print("[TG ERROR]", e)

# ------------ Helpers ------------
def load_ai_params():
    if not AI_PARAMS_PATH.exists():
        return {"EDGE_OPEN_BPS":2.0, "HEDGE_SIZE_BTC":0.0004, "RISK_FACTOR":1.0}
    try:
        with open(AI_PARAMS_PATH) as f:
            j = json.load(f)
        return {
            "EDGE_OPEN_BPS": float(j.get("EDGE_OPEN_BPS",2.0)),
            "HEDGE_SIZE_BTC": float(j.get("HEDGE_SIZE_BTC",0.0004)),
            "RISK_FACTOR": float(j.get("RISK_FACTOR",1.0)),
        }
    except Exception as e:
        print("[AI LOAD ERR]", e)
        return {"EDGE_OPEN_BPS":2.0, "HEDGE_SIZE_BTC":0.0004, "RISK_FACTOR":1.0}

def ai_hash(params: dict) -> str:
    s = f"{params['EDGE_OPEN_BPS']}-{params['HEDGE_SIZE_BTC']}-{params['RISK_FACTOR']}"
    return hashlib.sha1(s.encode()).hexdigest()

def choose_pairs():
    # 1) pairs.json > 2) ENV MONITOR_PAIRS > 3) default
    if PAIRS_JSON.exists():
        try:
            j = json.loads(PAIRS_JSON.read_text())
            pairs = j.get("monitor", [])
        except Exception:
            pairs = []
    else:
        env_pairs = os.getenv("MONITOR_PAIRS","").strip()
        pairs = [x.strip() for x in env_pairs.split(",") if x.strip()] if env_pairs else []
    if not pairs:
        pairs = ["BTC/USDC","ETH/USDC"]  # drošais minimums
    pairs = [p for p in pairs if p not in PAIR_BLACKLIST]
    return pairs[:MAX_AGENTS]

def child_env(base_env: dict, pair: str, ai: dict):
    e = dict(base_env)
    e["PAIR"] = pair
    e["EDGE_OPEN_BPS"] = str(ai["EDGE_OPEN_BPS"])
    e["HEDGE_SIZE_BTC"] = str(ai["HEDGE_SIZE_BTC"])
    # bez “burvības skaitļiem”: ļaujam pielāgoties ar risk-factor
    e["ADAPTIVE_COEFF"] = str(max(0.2, min(1.5, 0.6 * ai["RISK_FACTOR"])))
    # saglabā esošās drošības robežas, ja definētas .env.local
    for k, dv in {
        "CHECK_INTERVAL_S":"2.0",
        "STOP_PNL_USD":"-0.10",
        "RECOVERY_WAIT_S":"90",
    }.items():
        if k not in e:
            e[k] = os.getenv(k, dv)
    return e

def spawn(pair: str, ai: dict) -> subprocess.Popen:
    log = f"logs/ai_auto_{pair.replace('/','-')}.log"
    Path("logs").mkdir(exist_ok=True)
    env = child_env(os.environ.copy(), pair, ai)
    cmd = ["python3", ROUTER_SCRIPT]
    f = open(log, "a", buffering=1)
    print(f"[SPAWN] {pair} → {log} | EDGE={ai['EDGE_OPEN_BPS']} SIZE={ai['HEDGE_SIZE_BTC']}")
    return subprocess.Popen(cmd, stdout=f, stderr=f, env=env)

def kill_proc(p: subprocess.Popen):
    if p and p.poll() is None:
        try:
            p.send_signal(signal.SIGTERM)
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        except Exception:
            pass

# ------------ Main loop ------------
def main():
    print(f"[BOOT] Stage-32 AI-Integrated Auto-Scaler — exchanges={USE_EXCHANGES} max_agents={MAX_AGENTS}")
    pairs = choose_pairs()
    ai = load_ai_params()
    h_prev = ai_hash(ai)
    procs = {}

    send(f"🧠 Auto-Scaler (AI) start\nPairs: {', '.join(pairs)}\nEDGE={ai['EDGE_OPEN_BPS']} | SIZE={ai['HEDGE_SIZE_BTC']} | RISK={ai['RISK_FACTOR']}")

    # sākotnējais spawn
    for pair in pairs:
        procs[pair] = spawn(pair, ai)

    last_check = time.time()
    while True:
        # 1) monitorē bērnus
        for pair, p in list(procs.items()):
            if p.poll() is not None:
                print(f"[RESPAWN] {pair} exited → restarting")
                procs[pair] = spawn(pair, ai)

        # 2) periodiski pārbaudi AI parametrus
        if time.time() - last_check >= REFRESH_SEC:
            last_check = time.time()
            new_ai = load_ai_params()
            h_new = ai_hash(new_ai)
            if h_new != h_prev:
                print(f"[AI UPDATE] {ai} → {new_ai}")
                send(f"🧠 AI params updated\nEDGE={new_ai['EDGE_OPEN_BPS']} → SIZE={new_ai['HEDGE_SIZE_BTC']} → RISK={new_ai['RISK_FACTOR']}\nRestarting agents…")
                # pārstartē visus ar jauniem parametriem
                for pair, p in procs.items():
                    kill_proc(p)
                ai = new_ai
                h_prev = h_new
                for pair in pairs:
                    procs[pair] = spawn(pair, ai)

            # arī periodiski var atjaunināt pāru sarakstu (ja vēlies)
            new_pairs = choose_pairs()
            if new_pairs != pairs:
                send(f"♻️ Pairs changed\nOld: {', '.join(pairs)}\nNew: {', '.join(new_pairs)}\nRebalancing agents…")
                # kill no longer needed
                for pair in set(pairs) - set(new_pairs):
                    kill_proc(procs.get(pair))
                    procs.pop(pair, None)
                # spawn newly added
                for pair in new_pairs:
                    if pair not in procs and len(procs) < MAX_AGENTS:
                        procs[pair] = spawn(pair, ai)
                pairs = new_pairs

        time.sleep(2)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("exit")
