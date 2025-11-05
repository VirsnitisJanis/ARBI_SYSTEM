# src/engine/maker_engine.py
import csv
import math
import os
import time
from pathlib import Path

from utils.balances import adjust, get, snapshot

# iestatījumi
MAKER_TTL_S     = float(os.getenv("MAKER_TTL_S", "3"))
PRICE_PAD_BPS   = float(os.getenv("PRICE_PAD_BPS", "0.5"))   # 0.5 bps = 0.005%
TAKER_FEE_BPS_A = float(os.getenv("TAKER_FEE_BPS_BINANCE", "6"))   # 6 bps = 0.06%
TAKER_FEE_BPS_B = float(os.getenv("TAKER_FEE_BPS_KUCOIN",  "8"))   # 8 bps = 0.08%

LOG_DIR = Path("logs"); LOG_DIR.mkdir(exist_ok=True, parents=True)
TRADES  = LOG_DIR / "trades.csv"
if not TRADES.exists():
    with TRADES.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ts","venueA","venueB","side","size_btc","price_A","price_B","fee_bps_A","fee_bps_B","pnl_usdc"])

def _pad_price(side:str, ref:float)->float:
    # lai maker limitam būtu labāka izpildes varbūtība: BUY => paceļam līdz ask - pad; SELL => zem bid + pad
    pad = ref * (PRICE_PAD_BPS/10000.0)
    if side == "buy":
        return ref + pad
    else:
        return ref - pad

def place_maker(side, venue, ref_price, size_btc):
    px = _pad_price(side, ref_price)
    return {
        "side": side,
        "venue": venue,
        "price": float(px),
        "size": float(size_btc),
        "expiry": time.time() + MAKER_TTL_S,
        "filled": False
    }

def process_maker_order(order, best):
    # vienkāršots fill nosacījums pret top-of-book
    # BUY maker izpildās, ja best["ask"] <= order["price"]
    # SELL maker izpildās, ja best["bid"] >= order["price"]
    now = time.time()
    if now >= order["expiry"]:
        return (False, "EXPIRED")

    if order["side"] == "buy":
        if best["ask"] <= order["price"]:
            order["filled"] = True
            return (True, "FILLED")
    else:
        if best["bid"] >= order["price"]:
            order["filled"] = True
            return (True, "FILLED")

    return (None, "PENDING")

def _fee(amount:float, bps:float)->float:
    return amount * (bps/10000.0)

def settle_fill(order, hedge_bid_price):
    """
    Maker BUY uz venue A par order['price'] => iztērē USDC_A, saņem BTC_A.
    Hedged SELL uz venue B par hedge_bid_price (taker) => saņem USDC_B, atdod BTC_B.
    PnL mērām USDC: pnl = USDC_B_in - USDC_A_out - fees
    """
    side   = order["side"]
    venueA = order["venue"]
    venueB = "kucoin" if venueA == "binance" else "binance"

    size   = float(order["size"])
    pxA    = float(order["price"])
    pxB    = float(hedge_bid_price)

    # makera fee pieņemam 0 (maker rebates/fees ignorējam vai iestatām atsevišķi, ja vajag)
    maker_cost_usdc = size * pxA
    taker_proceeds_usdc = size * pxB

    feeA = _fee(maker_cost_usdc, 0.0)                 # maker fee (ja gribi – ieliec MAKER_FEE_BPS_A)
    feeB = _fee(taker_proceeds_usdc, TAKER_FEE_BPS_B) # taker fee B

    # bilances grāmatošana
    # Venue A: -USDC, +BTC
    adjust(venueA, "USDC", -maker_cost_usdc - feeA)
    adjust(venueA, "BTC",   +size)

    # Venue B: +USDC, -BTC
    adjust(venueB, "USDC", +taker_proceeds_usdc - feeB)
    adjust(venueB, "BTC",  -size)

    pnl = (taker_proceeds_usdc - feeB) - (maker_cost_usdc + feeA)

    # žurnāls
    with TRADES.open("a", newline="") as f:
        w = csv.writer(f)
        w.writerow([time.time(), venueA, venueB, side, size, pxA, pxB, 0.0, TAKER_FEE_BPS_B, pnl])

    return round(pnl, 6)
