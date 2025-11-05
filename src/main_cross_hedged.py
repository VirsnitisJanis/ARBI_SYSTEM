import asyncio
import os

import ccxt

from engine.maker_engine import place_maker, process_maker_order, settle_fill
from utils.balances import get, snapshot

PAIR = os.getenv("PAIR","BTC/USDC")
A, Bv = os.getenv("VENUE_A","binance"), os.getenv("VENUE_B","kucoin")
NOTIONAL = float(os.getenv("NOTIONAL_USDC","25"))
EDGE_OPEN_BPS   = float(os.getenv("EDGE_OPEN_BPS","1.0"))
EDGE_CANCEL_BPS = float(os.getenv("EDGE_CANCEL_BPS","0.3"))

async def loop():
    ca, cb = ccxt.binance(), ccxt.kucoin()
    maker_order = None
    

    # DEV: force-fill test mode
    if os.getenv("FORCE_FILL") == "1":
        from utils.balances import adjust, snapshot
        print("[DEV] Force fill triggered")

        size = 0.00025
        price = 25000   # fake reference

        adjust("binance","BTC", size)
        adjust("binance","USDC", -size*price)
        adjust("kucoin","BTC", -size)
        adjust("kucoin","USDC", size*price)

        print("[SNAP]", snapshot())
        exit()

    print(f"[BOOT] HEDGED mode {A} ↔ {Bv} {PAIR}")

    while True:
        ta = await asyncio.to_thread(ca.fetch_ticker, PAIR)
        tb = await asyncio.to_thread(cb.fetch_ticker, PAIR)
        a_bid,a_ask = ta["bid"], ta["ask"]
        b_bid,b_ask = tb["bid"], tb["ask"]

        mid = (a_bid+a_ask+b_bid+b_ask)/4
        edge_ab = ((b_bid - a_ask)/mid) * 10000.0
        print(f"[EDGE] {edge_ab:.2f}bps | order={maker_order}")

        if maker_order is None and edge_ab >= EDGE_OPEN_BPS:
            size = NOTIONAL / a_ask
            if get(A,"USDC")>=NOTIONAL and get(Bv,"BTC")>=size:
                maker_order = place_maker("buy", A, a_bid, size)
                print("[PLACE A]", maker_order)

        if maker_order:
            status, reason = process_maker_order(maker_order, {"bid":a_bid,"ask":a_ask})

            # force cancel, ja edge izkūst
            if status is None and edge_ab < EDGE_CANCEL_BPS:
                maker_order["expiry"] = 0  # piespiež EXPIRED
                status, reason = (False, "FORCE_CANCEL_EDGE")

            if status is True:
                pnl = settle_fill(maker_order, b_bid)
                print("[HEDGE EXEC]", b_bid, "| PnL:", pnl, "| SNAP:", snapshot())
                maker_order = None
            elif status is False:
                print("[CANCEL]", reason)
                maker_order = None

        await asyncio.sleep(0.25)

if __name__=="__main__":
    try: asyncio.run(loop())
    except KeyboardInterrupt: pass
