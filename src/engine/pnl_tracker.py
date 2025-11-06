import csv
import os
import time

from utils.balances import snapshot

LOG_PNL = "logs/pnl.csv"

def record_pnl(pair, sideA, pxA, sideB, pxB, qty, fee_a_bps, fee_b_bps):
    """
    Aprēķina kopējo PnL (USDC) no divu biržu fill pāra.
    """
    fee_a = pxA * qty * (fee_a_bps / 10000)
    fee_b = pxB * qty * (fee_b_bps / 10000)

    # A ir BUY, B ir SELL → peļņa = (pxB - pxA)*qty - (fee_a + fee_b)
    if sideA == "buy" and sideB == "sell":
        pnl = (pxB - pxA) * qty - fee_a - fee_b
    elif sideA == "sell" and sideB == "buy":
        pnl = (pxA - pxB) * qty - fee_a - fee_b
    else:
        pnl = 0

    os.makedirs(os.path.dirname(LOG_PNL), exist_ok=True)
    newfile = not os.path.exists(LOG_PNL)
    with open(LOG_PNL, "a", newline="") as f:
        w = csv.writer(f)
        if newfile:
            w.writerow(["ts","pair","sideA","pxA","sideB","pxB","qty","pnl","wallets"])
        w.writerow([time.time(), pair, sideA, pxA, sideB, pxB, qty, pnl, snapshot()])
    return pnl
