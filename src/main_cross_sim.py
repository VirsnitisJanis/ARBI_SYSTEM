import asyncio
import random
import time

from engine.maker_engine_sim import place_maker, process_maker
from sim.orderbook_sim import SimOrderBook
from utils.balances import adjust, snapshot

PAIR = "BTC/USDC"
NOTIONAL = 25
EDGE_OPEN_BPS = 2.0       # 2 bps edge required
EDGE_CANCEL_BPS = 0.8     # cancel threshold
LATENCY_MS = 80           # simulated latency
SLIPPAGE_BPS = 0.5        # hedge slippage sim

async def loop():
    obA = SimOrderBook(27000)
    obB = SimOrderBook(27000)

    maker = None
    print("[SIM] Cross-exchange hedge simulator running...")

    while True:
        obA.step()
        obB.step()

        a_bid,a_ask = obA.bid, obA.ask
        b_bid,b_ask = obB.bid, obB.ask

        mid = (a_bid + a_ask + b_bid + b_ask)/4
        edge_ab = ((b_bid - a_ask)/mid) * 10000

        print(f"[EDGE] {edge_ab:.2f} bps | maker={maker}")

        # place maker if no order
        if maker is None and edge_ab >= EDGE_OPEN_BPS:
            size = NOTIONAL / a_ask
            maker = place_maker("buy", "binance", a_bid, size)
            print("[SIM PLACE]", maker)

        # if maker alive → simulate fill
        if maker:
            filled, px, qty = process_maker(maker, a_bid, a_ask)

            # edge collapsed → force expire
            if not filled and edge_ab < EDGE_CANCEL_BPS:
                maker["expiry"] = 0

            # maker fill
            if filled:
                await asyncio.sleep(LATENCY_MS/1000)

                # hedge on B with slippage
                hedge_px = b_bid * (1 - SLIPPAGE_BPS/10000)

                pnl = hedge_px - px

                adjust("binance","BTC", qty)
                adjust("binance","USDC", -px*qty)
                adjust("kucoin","BTC", -qty)
                adjust("kucoin","USDC", hedge_px*qty)

                print(f"[SIM FILL] maker:{px:.2f} hedge:{hedge_px:.2f} pnl:{pnl:.6f}")
                print("[SNAP]", snapshot())

                maker = None

        await asyncio.sleep(0.05)

asyncio.run(loop())
