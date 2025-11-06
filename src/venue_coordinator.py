import os, shlex, time, itertools, subprocess
from pathlib import Path

PAIRS   = [p.strip() for p in os.getenv("PAIRS","BTC/USDC").split(",") if p.strip()]
VENUES  = [v.strip() for v in os.getenv("VENUES","binance,kucoin,kraken").split(",") if v.strip()]
PYTHON  = os.getenv("PYTHON_BIN","python3")
SCRIPT  = os.getenv("LIVE_SCRIPT","src/main_cross_live_safe.py")
BASE_ENV_KEYS = {
    "NOTIONAL_USDC","EDGE_OPEN_BPS","EDGE_CANCEL_BPS",
    "MAX_INV_BTC","RESTART_DELAY_S","MAKER_TTL_S","PRICE_PAD_BPS",
    "SLIPPAGE_BPS","TAKER_FEE_BPS_BINANCE","TAKER_FEE_BPS_KUCOIN",
    "CHECK_INTERVAL_S"
}

Path("logs").mkdir(parents=True, exist_ok=True)
procs = []

def spawn(pair, a, b):
    pair_tag = pair.replace("/","-")
    logf = f"logs/live_{pair_tag}_{a}-{b}.csv"

    env = os.environ.copy()
    env["PAIR"] = pair
    env["VENUE_A"] = a
    env["VENUE_B"] = b
    env["LOG_FILE"] = logf

    # pārnesam tikai vajadzīgos env (ja iestatīti)
    for k in list(env.keys()):
        if k.startswith(("KRAKEN_","BINANCE_","KUCOIN_")):
            continue
        if k not in BASE_ENV_KEYS and k not in {"PAIR","VENUE_A","VENUE_B","LOG_FILE","TG_TOKEN","TG_CHAT"}:
            # atstājam pārējo, jo botam var vajadzēt
            pass

    cmd = f'{PYTHON} {shlex.quote(SCRIPT)}'
    p = subprocess.Popen(cmd, shell=True, env=env)
    print(f"[SPAWN] {pair} {a}<->{b} pid={p.pid} log={logf}")
    return p

def main():
    # visas unikālās venue pāru kombinācijas
    pairs = list(itertools.combinations(VENUES, 2))
    for pair in PAIRS:
        for a,b in pairs:
            procs.append(spawn(pair, a, b))

    try:
        # vienkāršs sargs: ja kāds nomirst — parāda un turpina
        while True:
            alive = []
            for p in procs:
                ret = p.poll()
                if ret is None:
                    alive.append(p)
                else:
                    print(f"[EXIT] pid={p.pid} code={ret}")
            procs[:] = alive
            time.sleep(2)
    except KeyboardInterrupt:
        for p in procs:
            try: p.terminate()
            except Exception: pass

if __name__ == "__main__":
    main()
