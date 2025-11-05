import asyncio
import os

import ccxt

from engine.maker_engine import place_maker, process_maker_order, settle_fill
from utils import balances as B

PAIR = "BTC/USDC"
BASE = "USDC"

A = "binance"
Bv = "kucoin"

NOTIONAL = float(os.getenv("NOTIONAL_USDC","25"))
EDGE_OPEN_BPS = float(os.getenv("EDGE_OPEN_BPS","1"))   # easy trigger
EDGE_CANCEL_BPS = float(os.getenv("EDGE_CANCEL_BPS","0.3"))

TAKER_FEE = 0.0006   # 6bps est
MAKER_FEE = 0.0001   # 1bps est

async def loop():
    ca, cb = ccxt.binance(), ccxt.kucoin()
    maker_order = None

    print(f"[BOOT] MAKER CROSS {A} ↔ {Bv} {PAIR}")

    while True:
        ta = await asyncio.to_thread(ca.fetch_ticker, PAIR)
        tb = await asyncio.to_thread(cb.fetch_ticker, PAIR)

        a_bid, a_ask = ta["bid"], ta["ask"]
        b_bid, b_ask = tb["bid"], tb["ask"]

        mid = (a_bid + a_ask + b_bid + b_ask) / 4
        edge_ab = ((b_bid - a_ask) / mid) * 10000

        print(f"[EDGE] {edge_ab:.2f}bps | order={maker_order}")

        # OPEN TRADE
        if maker_order is None and edge_ab >= EDGE_OPEN_BPS:
            size = NOTIONAL / a_ask
            if B.get(A,"USDC") >= NOTIONAL:
                maker_order = place_maker("buy", A, a_bid, size)
                print("[PLACE]", maker_order)

        # MANAGE EXISTING ORDER
        if maker_order:
            status, reason = process_maker_order(maker_order, {"bid":a_bid,"ask":a_ask})

            # FILLED
            if status is True:
                pnl, bought_btc = settle_fill(maker_order, b_bid, fee=MAKER_FEE)
                # hedge simulation
                hedge_out = bought_btc * b_bid * (1 - TAKER_FEE)
                B.adjust(Bv, BASE, hedge_out)
                print("[HEDGE EXEC]", hedge_out)

                print("[FILL] PNL:", pnl, B.snapshot())
                maker_order = None

            # CANCEL
            elif status is False:
                print("[CANCEL]", reason)
                maker_order = None

            # CANCEL BAD EDGE
            elif edge_ab < EDGE_CANCEL_BPS:
                print("[FORCE CANCEL] edge fell")
                maker_order = None

        await asyncio.sleep(0.25)

if __name__ == "__main__":
    try: asyncio.run(loop())
    except KeyboardInterrupt:
        print("STOP")