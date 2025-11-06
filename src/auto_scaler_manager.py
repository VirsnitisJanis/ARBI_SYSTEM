import os, json, time, signal, subprocess, asyncio
import ccxt

from notify import send  # izmanto mūsu rate-limited send()
from utils.balances import load_snapshot   # Stage-20 util

# ─────────────────────────────────────────────────────────────
# ENV parametri (var pārrakstīt .env.local vai export)
# ─────────────────────────────────────────────────────────────
DISCOVERY_SEC    = float(os.getenv("DISCOVERY_SEC", "120"))   # cik bieži atklāt pārus
MIN_QUOTES_USDC  = float(os.getenv("MIN_QUOTES_USDC", "10"))  # min USDC uz katru aģentu
MAX_AGENTS       = int(os.getenv("MAX_AGENTS", "6"))          # maksimums vienlaicīgo aģentu
USE_EXCHANGES    = os.getenv("USE_EXCHANGES", "binance,kucoin,kraken").split(",")

ROUTER_SCRIPT    = os.getenv("ROUTER_SCRIPT", "src/smart_hedge_router_protected.py")
EDGE_OPEN_BPS    = os.getenv("EDGE_OPEN_BPS", "2.0")
HEDGE_SIZE_BTC   = os.getenv("HEDGE_SIZE_BTC", "0.0004")
ADAPTIVE_COEFF   = os.getenv("ADAPTIVE_COEFF", "0.6")
CHECK_INTERVAL_S = os.getenv("CHECK_INTERVAL_S", "2.0")
STOP_PNL_USD     = os.getenv("STOP_PNL_USD", "-0.10")
RECOVERY_WAIT_S  = os.getenv("RECOVERY_WAIT_S", "90")

# Brīvprātīgi: statisks whitelist / blacklist (CSV saraksti)
WHITELIST = set([s.strip() for s in os.getenv("PAIR_WHITELIST", "").split(",") if s.strip()])
BLACKLIST = set([s.strip() for s in os.getenv("PAIR_BLACKLIST", "").split(",") if s.strip()])

# Brīvprātīgi: pairs.json pielāgotai manuālai kontrolei (monitor lauks)
def load_pairs_json():
    if os.path.exists("pairs.json"):
        try:
            with open("pairs.json","r") as f:
                data = json.load(f)
            arr = data.get("monitor", [])
            return [p for p in arr if p]  # drošība
        except Exception:
            return []
    return []

# ─────────────────────────────────────────────────────────────
# CCXT klienti
# ─────────────────────────────────────────────────────────────
def build_clients():
    clients = {}
    for name in USE_EXCHANGES:
        n = name.strip()
        if not n: continue
        if n == "binance":
            clients[n] = ccxt.binance({
                "apiKey": os.getenv("BINANCE_API_KEY"),
                "secret": os.getenv("BINANCE_SECRET_KEY"),
            })
        elif n == "kucoin":
            clients[n] = ccxt.kucoin({
                "apiKey": os.getenv("KUCOIN_API_KEY"),
                "secret": os.getenv("KUCOIN_SECRET_KEY"),
                # CCXT param nosaukums passphrase = 'password'
                "password": os.getenv("KUCOIN_PASSPHRASE"),
            })
        elif n == "kraken":
            clients[n] = ccxt.kraken({
                "apiKey": os.getenv("KRAKEN_API_KEY"),
                "secret": os.getenv("KRAKEN_SECRET_KEY"),
            })
    return clients

# ─────────────────────────────────────────────────────────────
# Dinamiskā pāru atklāšana
# Kritēriji:
#  • aktīvi USDC quote pāri
#  • pieejami vismaz uz 2 biržām (cross-venue iespēja)
#  • atbilst whitelist/blacklist
#  • nepārsniedz budžetu (MIN_QUOTES_USDC * aģentu skaits)
# ─────────────────────────────────────────────────────────────
async def discover_pairs(clients):
    # 1) Markets per exchange (USDC quote)
    venues_pairs = {}
    for v, ex in clients.items():
        try:
            mkts = await asyncio.to_thread(ex.load_markets)
            usdc = {sym for sym, m in mkts.items()
                    if m.get("active") and m.get("quote") == "USDC"}
            venues_pairs[v] = usdc
        except Exception as e:
            venues_pairs[v] = set()

    # 2) kopīgās iespējas: simboli, kas ir pieejami uz ≥2 biržām
    presence = {}
    for v, sset in venues_pairs.items():
        for s in sset:
            presence.setdefault(s, set()).add(v)

    # 3) filtrē ar WL / BL
    candidates = []
    for sym, venues in presence.items():
        if len(venues) < 2:
            continue
        if WHITELIST and sym not in WHITELIST:
            continue
        if sym in BLACKLIST:
            continue
        candidates.append((sym, sorted(list(venues))))

    # 4) ja ir pairs.json — piešķir prioritāti (saglabā kā pirmos)
    manual = load_pairs_json()
    manual_set = set(manual)
    # manuālie vispirms; pārējos pievieno pēc tam
    ordered = []
    if manual:
        for s in manual:
            if s in presence and s not in BLACKLIST:
                ordered.append((s, sorted(list(presence[s]))))
    for s, vv in candidates:
        if s not in manual_set:
            ordered.append((s, vv))

    return ordered

# ─────────────────────────────────────────────────────────────
# Aģentu pārvaldība
# ─────────────────────────────────────────────────────────────
PROCS = {}  # key: pair → subprocess.Popen

def spawn_agent(pair):
    env = os.environ.copy()
    env["PAIR"] = pair
    env["EDGE_OPEN_BPS"] = EDGE_OPEN_BPS
    env["HEDGE_SIZE_BTC"] = HEDGE_SIZE_BTC
    env["ADAPTIVE_COEFF"] = ADAPTIVE_COEFF
    env["CHECK_INTERVAL_S"] = CHECK_INTERVAL_S
    env["STOP_PNL_USD"] = STOP_PNL_USD
    env["RECOVERY_WAIT_S"] = RECOVERY_WAIT_S

    log = f"logs/auto_{pair.replace('/','-')}.log"
    f = open(log, "a")
    p = subprocess.Popen(
        ["python3", ROUTER_SCRIPT],
        stdout=f, stderr=f, env=env
    )
    PROCS[pair] = (p, f)
    print(f"[SPAWN] {pair} pid={p.pid} log={log}")
    return p

def kill_agent(pair):
    tup = PROCS.get(pair)
    if not tup: return
    p, f = tup
    try:
        p.send_signal(signal.SIGTERM)
        try:
            p.wait(timeout=5)
        except Exception:
            p.kill()
    finally:
        try: f.close()
        except Exception: pass
    PROCS.pop(pair, None)
    print(f"[KILL] {pair}")

def living_pairs():
    dead = []
    for pair,(p,f) in PROCS.items():
        if p.poll() is not None:
            dead.append(pair)
    for pair in dead:
        kill_agent(pair)
    return set(PROCS.keys())

# ─────────────────────────────────────────────────────────────
# Budžeta vārti: cik aģentus drīkst uzturēt, ņemot vērā USDC?
# ─────────────────────────────────────────────────────────────
def max_agents_by_budget():
    snap = load_snapshot()
    # ņem USDC summu pāri visām biržām
    tot = 0.0
    for v, assets in snap.items():
        tot += float(assets.get("USDC", 0.0))
    return max(0, min(MAX_AGENTS, int(tot // MIN_QUOTES_USDC)))

# ─────────────────────────────────────────────────────────────
# TG kopsavilkuma nosūtīšana, kad mainās monitorējamie pāri
# ─────────────────────────────────────────────────────────────
def tg_summary(active, added, removed):
    try:
        msg = []
        msg.append("🧭 Auto-Scaler update")
        if added:
            msg.append("➕ Added: " + ", ".join(added))
        if removed:
            msg.append("➖ Removed: " + ", ".join(removed))
        msg.append("▶ Active: " + (", ".join(sorted(active)) if active else "none"))
        send("\n".join(msg))
    except Exception as e:
        print("[TG ERROR]", e)

# ─────────────────────────────────────────────────────────────
# Galvenais monitor cilpa
# ─────────────────────────────────────────────────────────────
async def monitor():
    clients = build_clients()
    print("[BOOT] Auto-Scaler Manager — exchanges", list(clients.keys()))

    current = living_pairs()

    while True:
        # cik aģentu ļauj budžets
        limit = max_agents_by_budget()

        # atrod kandidātus
        discovered = await discover_pairs(clients)
        # tikai simboli (pāru virkne)
        discovered_syms = [s for s,_ in discovered]

        # top N pēc limita; manuālie no pairs.json jau ir prioritizēti
        target_list = discovered_syms[:limit]
        target = set(target_list)

        # izmaiņas
        add = sorted(target - current)
        rem = sorted(current - target)

        # atjauno
        for pair in rem:
            kill_agent(pair)

        for pair in add:
            spawn_agent(pair)

        if add or rem:
            tg_summary(living_pairs(), add, rem)

        # sirds puksts logā
        print(f"[MONITOR] limit={limit} living={sorted(living_pairs())} target={target_list}")
        await asyncio.sleep(DISCOVERY_SEC)

# ─────────────────────────────────────────────────────────────
async def main():
    os.makedirs("logs", exist_ok=True)
    await monitor()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("exit")
