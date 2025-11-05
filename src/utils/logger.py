import time, csv, os
from pathlib import Path

def _open_csv(path:str, header:list):
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    init = not p.exists()
    f = p.open("a", newline="")
    w = csv.writer(f)
    if init: w.writerow(header)
    return f, w

def log_cross_scan(a_bid, a_ask, b_bid, b_ask, edge_bps, chosen):
    f,w = _open_csv("logs/cross_scan.csv",
                    ["ts","A_bid","A_ask","B_bid","B_ask","edge_bps","chosen"])
    w.writerow([time.time(), a_bid, a_ask, b_bid, b_ask, edge_bps, chosen]); f.close()

def log_trade(exec_side, notional_usdc, size_btc, a_px, b_px, fees_usdc, pnl_usdc):
    f,w = _open_csv("logs/trades.csv",
        ["ts","side","notional","size_btc","a_px","b_px","fees","pnl"])
    w.writerow([time.time(), exec_side, notional_usdc, size_btc, a_px, b_px, fees_usdc, pnl_usdc]); f.close()
