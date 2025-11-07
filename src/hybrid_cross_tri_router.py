import asyncio
import os
import time

import ccxt

ex = {
    "binance": ccxt.binance({'apiKey':os.getenv('BINANCE_API_KEY'),'secret':os.getenv('BINANCE_SECRET_KEY')}),
    "kucoin":  ccxt.kucoin({'apiKey':os.getenv('KUCOIN_API_KEY'),'secret':os.getenv('KUCOIN_SECRET_KEY'),'password':os.getenv('KUCOIN_PASSPHRASE')}),
    "kraken":  ccxt.kraken({'apiKey':os.getenv('KRAKEN_API_KEY'),'secret':os.getenv('KRAKEN_SECRET_KEY')}),
}

PAIR = os.getenv("PAIR", "BTC/USDC")
EDGE_OPEN_BPS = float(os.getenv("EDGE_OPEN_BPS", 2.0))
HEDGE_SIZE = float(os.getenv("HEDGE_SIZE_BTC", 0.00008))
CHECK_INTERVAL = float(os.getenv("CHECK_INTERVAL_S", 1.5))
COOLDOWN = 20
last_alert = 0

def get_mid(exch):
    t = exch.fetch_ticker(PAIR)
    return (t["bid"] + t["ask"]) / 2

async def main_loop():
    global last_alert
    print(f"[BOOT] Stage-38.3 router | EDGE>{EDGE_OPEN_BPS}bps | cooldown={COOLDOWN}s")
    while True:
        try:
            mids = {n:get_mid(e) for n,e in ex.items()}
            for a,pa in mids.items():
                for b,pb in mids.items():
                    if a==b: continue
                    edge = (pb-pa)/pa*1e4
                    if edge > EDGE_OPEN_BPS:
                        now = time.time()
                        if now - last_alert >= COOLDOWN:
                            print(f"⚡ HEDGE EXEC | Buy={a}@{pa:.2f} → Sell={b}@{pb:.2f} | Edge={edge:.2f}")
                            last_alert = now
                        else:
                            print(f"[SKIP] cooldown active | {a}->{b} edge={edge:.2f}")
            await asyncio.sleep(CHECK_INTERVAL)
        except Exception as e:
            import traceback
            print("[ERR]", e)
            traceback.print_exc()
            await asyncio.sleep(3)


asyncio.run(main_loop())
