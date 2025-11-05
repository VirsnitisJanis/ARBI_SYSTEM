import os, asyncio, time
import ccxt
from utils.logger import log_cross_scan
from utils import balances as B
from engine.cross_engine import maybe_trade

PAIR = os.getenv("PAIR","BTC/USDC")
BASE = os.getenv("BASE","USDC")
A = os.getenv("VENUE_A","binance")
Bv = os.getenv("VENUE_B","kucoin")

EDGE_OPEN_BPS = float(os.getenv("EDGE_OPEN_BPS","3"))      # 0.03%
EDGE_CANCEL_BPS = float(os.getenv("EDGE_CANCEL_BPS","1"))  # unused in DRY_RUN
NOTIONAL = float(os.getenv("NOTIONAL_USDC","25"))
MIN_AVAIL_USDC = float(os.getenv("MIN_AVAIL_USDC","10"))

async def fetch_ticker(client, pair):
    t = await client.fetch_ticker(pair)
    return t["bid"], t["ask"]

async def loop():
    print(f"[BOOT] CROSS {A} ↔ {Bv} {PAIR} base={BASE} DRY_RUN={os.getenv('DRY_RUN','1')}")
    ca = ccxt.binance(); cb = ccxt.kucoin()
    while True:
        try:
            a_bid, a_ask = (await asyncio.to_thread(ca.fetch_ticker, PAIR))["bid"], (await asyncio.to_thread(ca.fetch_ticker, PAIR))["ask"]
        except Exception:
            t = await asyncio.to_thread(ca.fetch_ticker, PAIR)
            a_bid, a_ask = t["bid"], t["ask"]
        t2 = await asyncio.to_thread(cb.fetch_ticker, PAIR)
        b_bid, b_ask = t2["bid"], t2["ask"]

        # edge A->B = (B.bid - A.ask)/mid * 10000 bps
        mid = (a_bid+a_ask+b_bid+b_ask)/4.0
        edge_ab_bps = ( (b_bid - a_ask) / mid ) * 10000.0
        edge_ba_bps = ( (a_bid - b_ask) / mid ) * 10000.0

        chosen = "NONE"
        if edge_ab_bps >= EDGE_OPEN_BPS: chosen = "A->B"
        elif edge_ba_bps >= EDGE_OPEN_BPS: chosen = "B->A"  # (nav implementēts DRY_RUN)

        print(f"[MID] A {a_bid:.2f}/{a_ask:.2f} | B {b_bid:.2f}/{b_ask:.2f} | EDGE_AB={edge_ab_bps:.2f} bps EDGE_BA={edge_ba_bps:.2f} bps | choose={chosen}")
        log_cross_scan(a_bid,a_ask,b_bid,b_ask, edge_ab_bps if chosen!='B->A' else edge_ba_bps, chosen)

        if chosen == "A->B":
            if not B.ensure_min(A, "USDC", NOTIONAL*1.02):
                print("[BLOCK] MIN_USDC on", A); await asyncio.sleep(0.5); continue
            # vajag BTC uz B biržā hedžam
            need_btc = NOTIONAL / a_ask
            if B.get(Bv,"BTC") < need_btc:
                print("[BLOCK] MIN_BTC on", Bv, "| need", need_btc); await asyncio.sleep(0.5); continue
            ok, res = maybe_trade({"A":{"bid":a_bid,"ask":a_ask},"B":{"bid":b_bid,"ask":b_ask}},
                                  {"A":A,"B":Bv}, NOTIONAL)
            if ok:
                snap = B.snapshot()
                pnl = float(res)
                print(f"[TRADE] A->B notional={NOTIONAL} pnl={pnl:.4f} | Balances:", snap)
            else:
                print("[SKIP]", res)

        await asyncio.sleep(0.35)

if __name__ == "__main__":
    try:
        asyncio.run(loop())
    except KeyboardInterrupt:
        pass
