import asyncio
import os
import random
import time

import ccxt

from engine.maker_engine import \
    place_maker  # order dict: {side, venue, price, size, expiry, filled}
from engine.pnl_tracker import record_pnl
from notify import send
from utils.balances import adjust, get, snapshot

# =============================================================================
# ENV / CONFIG
# =============================================================================
PAIR = os.getenv("PAIR", "BTC/USDC")
A = os.getenv("VENUE_A", "binance")
B = os.getenv("VENUE_B", "kucoin")

NOTIONAL = float(os.getenv("NOTIONAL_USDC", "25"))

EDGE_OPEN_BPS   = float(os.getenv("EDGE_OPEN_BPS_M2M", "2.5"))
EDGE_CANCEL_BPS = float(os.getenv("EDGE_CANCEL_BPS", "1.0"))
TTL_S           = float(os.getenv("MAKER_TTL_S", "6"))
PRICE_PAD_BPS   = float(os.getenv("PRICE_PAD_BPS", "1.0"))

FEE_BPS_A = float(os.getenv("MAKER_FEE_BPS_A", "1.0"))
FEE_BPS_B = float(os.getenv("MAKER_FEE_BPS_B", "1.5"))

TEST_MODE     = os.getenv("M2M_TEST_MODE", "0") == "1"
TEST_FILL_PROB = float(os.getenv("M2M_TEST_FILL_PROB", "0.25"))
TEST_LAT_MS    = float(os.getenv("M2M_TEST_LAT_MS", "50"))
CHECK_INTERVAL_S = float(os.getenv("CHECK_INTERVAL_S", "0.25"))

# =============================================================================
# CCXT clients
# =============================================================================
ca = ccxt.binance()
cb = ccxt.kucoin()

async def fetch_ticker(exchange, pair):
    return await asyncio.to_thread(exchange.fetch_ticker, pair)

# =============================================================================
# HELPERS
# =============================================================================
def _now_loop_time():
    # konsekventi lietojam event_loop time (monotonic), nevis wall-clock
    return asyncio.get_event_loop().time()

def _place_with_ts(side: str, venue: str, price: float, size: float):
    od = place_maker(side, venue, price, size)
    # maker_engine.place_maker pievieno expiry/filled; mēs pievienojam ts drošībai
    od["ts"] = _now_loop_time()
    return od

# =============================================================================
# MAIN LOOP
# =============================================================================
async def loop():
    orderA = None  # buy on A
    orderB = None  # sell on B

    # pēdējie pabeigtie filli (ciklam), lai var saskaitīt PnL
    last_fillA = None  # tuple: (price, qty)
    last_fillB = None  # tuple: (price, qty)

    print(f"[BOOT] M2M post-only {A} ↔ {B} {PAIR}")
    print("[SNAP]", snapshot())

    while True:
        # 1) tirgus dati
        ta, tb = await asyncio.gather(
            fetch_ticker(ca, PAIR),
            fetch_ticker(cb, PAIR)
        )
        a_bid, a_ask = ta.get("bid"), ta.get("ask")
        b_bid, b_ask = tb.get("bid"), tb.get("ask")

        # aizsardzība pret None
        if any(x is None for x in (a_bid, a_ask, b_bid, b_ask)):
            await asyncio.sleep(CHECK_INTERVAL_S)
            continue

        mid = (a_bid + a_ask + b_bid + b_ask) / 4.0
        edge_ab = ((b_bid - a_ask) / mid) * 10000.0  # buy A, sell B
        edge_ba = ((a_bid - b_ask) / mid) * 10000.0  # sell B, buy A (apgrieztais virziens)

        print(f"[EDGE] AB={edge_ab:.2f}bps BA={edge_ba:.2f}bps | A={orderA} | B={orderB}")

        # 2) Atvēršana (post-only)
        # A -> B: Buy on A (zem bid ar nelielu pad, lai garantē resting)
        if orderA is None and edge_ab >= EDGE_OPEN_BPS:
            size = NOTIONAL / a_ask
            px = a_bid * (1 - PRICE_PAD_BPS/10000.0)
            if get(A, "USDC") >= NOTIONAL:
                orderA = _place_with_ts("buy", A, px, size)
                print("[PLACE A]", orderA)

        # B -> A: Sell on B (virs ask ar nelielu pad)
        if orderB is None and edge_ba >= EDGE_OPEN_BPS:
            size = NOTIONAL / b_ask
            px = b_ask * (1 + PRICE_PAD_BPS/10000.0)
            if get(B, "BTC") >= size:
                orderB = _place_with_ts("sell", B, px, size)
                print("[PLACE B]", orderB)

        # 3) TEST_MODE – simulējam post-only fill + bilanču izmaiņas
        if TEST_MODE:
            # A pusē: BUY fill (ja paveicas)
            if orderA and random.random() < TEST_FILL_PROB:
                await asyncio.sleep(TEST_LAT_MS / 1000.0)
                px, qty = orderA["price"], orderA["size"]
                fee = px * qty * (FEE_BPS_A / 10000.0)
                adjust(A, "BTC",  qty)
                adjust(A, "USDC", -(px*qty) - fee)
                last_fillA = (px, qty)
                print("[TEST-FILL A]", px, qty, snapshot())
                orderA = None

            # B pusē: SELL fill (ja paveicas)
            if orderB and random.random() < TEST_FILL_PROB:
                await asyncio.sleep(TEST_LAT_MS / 1000.0)
                px, qty = orderB["price"], orderB["size"]
                fee = px * qty * (FEE_BPS_B / 10000.0)
                adjust(B, "BTC",  -qty)
                adjust(B, "USDC", +(px*qty) - fee)
                last_fillB = (px, qty)
                print("[TEST-FILL B]", px, qty, snapshot())
                orderB = None

        # 4) TTL / Edge-based cancel (ja orderi joprojām atvērti)
        now_t = _now_loop_time()
        if orderA and (now_t - orderA["ts"] > TTL_S or edge_ab < EDGE_CANCEL_BPS):
            print("[CANCEL A]", "TTL" if (now_t - orderA["ts"] > TTL_S) else "EDGE")
            orderA = None
        if orderB and (now_t - orderB["ts"] > TTL_S or edge_ba < EDGE_CANCEL_BPS):
            print("[CANCEL B]", "TTL" if (now_t - orderB["ts"] > TTL_S) else "EDGE")
            orderB = None

        # 5) Kad abās pusēs ir notikuši fill (pabeigts cikls) → PnL + Telegram
        if last_fillA and last_fillB:
            pxA, qtyA = last_fillA
            pxB, qtyB = last_fillB

            # drošībai – ja izmēri nedaudz atšķiras, rēķinām pēc mazākā
            qty = min(qtyA, qtyB)

            pnl = record_pnl(
                PAIR,
                sideA="buy", pxA=pxA,
                sideB="sell", pxB=pxB,
                qty=qty,
                fee_a_bps=FEE_BPS_A,
                fee_b_bps=FEE_BPS_B
            )
            print("[PNL]", pnl)
            try:
                send(
                    "💰 M2M CYCLE\n"
                    f"Pair: {PAIR}\n"
                    f"Qty: {qty:.8f}\n"
                    f"A buy px: {pxA:.2f} | B sell px: {pxB:.2f}\n"
                    f"PnL: {pnl:.6f} USDC\n"
                    f"Wallets: {snapshot()}"
                )
            except Exception:
                pass

            # sagatavojam nākamajam ciklam
            last_fillA = None
            last_fillB = None

        await asyncio.sleep(CHECK_INTERVAL_S)

# =============================================================================
# RUN
# =============================================================================
if __name__ == "__main__":
    try:
        asyncio.run(loop())
    except KeyboardInterrupt:
        pass
