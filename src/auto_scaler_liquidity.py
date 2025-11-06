import os, asyncio, ccxt, json, subprocess, time
from notify import send

MIN_VOL = float(os.getenv("MIN_LIQ_VOL_USDC", "500000"))
DISCOVERY_SEC = int(os.getenv("DISCOVERY_SEC", "120"))
MAX_AGENTS = int(os.getenv("MAX_AGENTS", "6"))
USE_EXCHANGES = [e.strip() for e in os.getenv("USE_EXCHANGES", "binance,kucoin").split(",")]
ROUTER_SCRIPT = os.getenv("ROUTER_SCRIPT", "src/smart_hedge_router_protected.py")

async def discover_liquid_pairs():
    ex = ccxt.binance()
    markets = ex.fetch_tickers()
    liquid = []
    for pair, data in markets.items():
        if pair.endswith("/USDC") and data.get("quoteVolume"):
            if data["quoteVolume"] > MIN_VOL:
                liquid.append((pair, data["quoteVolume"]))
    liquid.sort(key=lambda x: x[1], reverse=True)
    return [p for p, _ in liquid[:MAX_AGENTS]]

async def monitor():
    print(f"[BOOT] Stage-22 Liquidity Auto-Scaler — exchanges={USE_EXCHANGES}")
    active = []
    while True:
        pairs = await discover_liquid_pairs()
        if pairs != active:
            print(f"[UPDATE] Liquid pairs ({len(pairs)}): {pairs}")
            msg = "💧 *Liquidity Filter Update*\n"
            msg += "\n".join([f"{p}" for p in pairs])
            send(msg)
            # kill old
            subprocess.call("pkill -f smart_hedge_router_protected.py", shell=True)
            for pair in pairs:
                logf = f"logs/liquid_{pair.replace('/','-')}.log"
                cmd = f"python3 {ROUTER_SCRIPT} {pair} > {logf} 2>&1 &"
                subprocess.call(cmd, shell=True)
                print(f"[SPAWN] {pair} → {logf}")
            active = pairs
        await asyncio.sleep(DISCOVERY_SEC)

asyncio.run(monitor())
