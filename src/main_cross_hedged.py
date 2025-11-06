import asyncio
import math
import os
import time

import ccxt

from utils.balances import adjust, get, snapshot
from utils.logger import CsvLog

PAIR = os.getenv("PAIR","BTC/USDC")
A, Bv = os.getenv("VENUE_A","binance"), os.getenv("VENUE_B","kucoin")
NOTIONAL = float(os.getenv("NOTIONAL_USDC","25"))
EDGE_OPEN_BPS   = float(os.getenv("EDGE_OPEN_BPS","1.0"))
EDGE_CANCEL_BPS = float(os.getenv("EDGE_CANCEL_BPS","0.3"))
TAKER_FEE_BPS_A = float(os.getenv("TAKER_FEE_BPS_BINANCE","6"))
TAKER_FEE_BPS_B = float(os.getenv("TAKER_FEE_BPS_KUCOIN","8"))
SLIPPAGE_BPS    = float(os.getenv("SLIPPAGE_BPS","0.5"))
COOLDOWN_MS     = int(os.getenv("COOLDOWN_MS","1500"))
STOP_PNL        = float(os.getenv("STOP_PNL","-0.5"))   # USDC uz sesiju
MAX_TRADES      = int(os.getenv("MAX_TRADES","50"))

def bps(x): return x/10000.0

async def loop():
    ca, cb = ccxt.binance(), ccxt.kucoin()
    maker_order = None
    last_action_ms = 0
    session_pnl = 0.0
    trades = 0
    log = CsvLog("logs/cross_hedge.csv",
        ["ts","a_bid","a_ask","b_bid","b_ask","edge_raw_bps","edge_net_bps","action","fill_px","hedge_px","pnl","pnl_total",
         "a_usdc","a_btc","b_usdc","b_btc"])

    print(f"[BOOT] HEDGED mode {A} ↔ {Bv} {PAIR}")
    print("[SNAP]", snapshot())

    while True:
        ta = await asyncio.to_thread(ca.fetch_ticker, PAIR)
        tb = await asyncio.to_thread(cb.fetch_ticker, PAIR)
        a_bid,a_ask = ta["bid"], ta["ask"]
        b_bid,b_ask = tb["bid"], tb["ask"]

        mid = (a_bid+a_ask+b_bid+b_ask)/4
        edge_raw = ((b_bid - a_ask)/mid) * 10000.0
        edge_net = edge_raw - (TAKER_FEE_BPS_A + TAKER_FEE_BPS_B + SLIPPAGE_BPS)

        
        now_ms = int(time.time() * 1000)

        cooled = (now_ms - last_action_ms) >= COOLDOWN_MS

        # STOP nosacījumi
        if session_pnl <= STOP_PNL or trades >= MAX_TRADES:
            print(f"[HALT] stop reached | pnl={session_pnl:.5f} trades={trades}")
            log.row(a_bid,a_ask,b_bid,b_ask,edge_raw,edge_net,"HALT","", "", "", session_pnl,
                    get(A,"USDC"),get(A,"BTC"),get(Bv,"USDC"),get(Bv,"BTC"))
            break

        # status
        print(f"[EDGE] raw={edge_raw:.2f}bps net={edge_net:.2f}bps | order={maker_order}")

        # atvēršana
        if maker_order is None and cooled and edge_net >= EDGE_OPEN_BPS:
            size = NOTIONAL / a_ask
            if get(A,"USDC")>=NOTIONAL and get(Bv,"BTC")>=size:
                px = a_bid  # maker buy ar bid (simulēts)
                maker_order = {"side":"buy","venue":A,"price":px,"size":size,"expiry":now_ms+2000,"filled":False}
                last_action_ms = now_ms
                log.row(a_bid,a_ask,b_bid,b_ask,edge_raw,edge_net,"PLACE",px,"","",session_pnl,
                        get(A,"USDC"),get(A,"BTC"),get(Bv,"USDC"),get(Bv,"BTC"))
                print("[PLACE A]", maker_order)

        # menedžments
        if maker_order:
            # vienkāršs fill modelis: ja bid pacelts ≥ mūsu cena, pēc 200ms uzskatām par filled
            if a_bid >= maker_order["price"] and now_ms >= maker_order["expiry"]:
                # hedge uz B (taker sell ar slippage)
                hedge_px = b_bid * (1 - bps(SLIPPAGE_BPS))
                fill_px  = maker_order["price"]
                qty      = maker_order["size"]

                # PnL par 1 BTC vienību = hedge_px - fill_px; par qty = * qty
                pnl = (hedge_px - fill_px) * qty
                # fees (USDC) – vienkāršots (taker abās kājās)
                fee_usdc = (bps(TAKER_FEE_BPS_A)*fill_px*qty) + (bps(TAKER_FEE_BPS_B)*hedge_px*qty)
                pnl -= fee_usdc
                session_pnl += pnl
                trades += 1

                # bilances (lokālais simulators)
                adjust(A,"BTC", qty)
                adjust(A,"USDC", -fill_px*qty)
                adjust(Bv,"BTC", -qty)
                adjust(Bv,"USDC", hedge_px*qty)

                print(f"[HEDGE EXEC] fill={fill_px:.2f} hedge={hedge_px:.2f} | pnl={pnl:.6f} | total={session_pnl:.6f}")
                log.row(a_bid,a_ask,b_bid,b_ask,edge_raw,edge_net,"FILL",fill_px,hedge_px,pnl,session_pnl,
                        get(A,"USDC"),get(A,"BTC"),get(Bv,"USDC"),get(Bv,"BTC"))
                maker_order = None
                last_action_ms = now_ms

            else:
                # edge sabrūk → force cancel
                if edge_net < EDGE_CANCEL_BPS:
                    maker_order = None
                    last_action_ms = now_ms
                    log.row(a_bid,a_ask,b_bid,b_ask,edge_raw,edge_net,"CANCEL","","","",session_pnl,
                            get(A,"USDC"),get(A,"BTC"),get(Bv,"USDC"),get(Bv,"BTC"))
                    print("[CANCEL] edge < cancel_th")

        await asyncio.sleep(0.25)

if __name__=="__main__":
    try:
        asyncio.run(loop())
    except KeyboardInterrupt:
        pass
