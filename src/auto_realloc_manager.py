import os, time, json, ccxt, asyncio
from notify import send

INTERVAL = int(os.getenv("REALLOC_INTERVAL_MIN", "60")) * 60
MIN_VOL = float(os.getenv("REALLOC_MIN_VOL_USDC", "500000"))
TARGET_BASE = os.getenv("TARGET_BASE", "USDC")
MAX_DIFF = float(os.getenv("MAX_REALLOC_DIFF", "0.25"))

async def compute_weights():
    ex = ccxt.binance()
    tickers = ex.fetch_tickers()
    vols = {}
    for p, t in tickers.items():
        if p.endswith(f"/{TARGET_BASE}") and t.get("quoteVolume", 0) > MIN_VOL:
            vols[p] = t["quoteVolume"]
    total = sum(vols.values())
    weights = {p: v / total for p, v in vols.items()} if total else {}
    return weights

async def monitor():
    print(f"[BOOT] Stage-23 Auto-Reallocation Manager — base={TARGET_BASE}")
    while True:
        weights = await compute_weights()
        alloc = {}
        exchs = ["binance", "kucoin", "kraken"]
        i = 0
        for pair, w in weights.items():
            alloc.setdefault(exchs[i % len(exchs)], []).append((pair, w))
            i += 1
        msg = "♻️ *Auto-Reallocation Summary*\n"
        for ex, ps in alloc.items():
            sumw = sum([w for _, w in ps])
            msg += f"{ex.upper()}: {sumw:.2%}\n"
            for pair, w in ps:
                msg += f"  • {pair} → {w:.2%}\n"
        print(msg)
        send(msg)
        time.sleep(INTERVAL)

asyncio.run(monitor())
