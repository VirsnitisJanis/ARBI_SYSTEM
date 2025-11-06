import time, os
from pathlib import Path

_PATH = Path("logs/cross_m2m.csv")
_PATH.parent.mkdir(parents=True, exist_ok=True)

def log_tick(a_bid,a_ask,b_bid,b_ask,edge_ab,edge_ba,state):
    with _PATH.open("a") as f:
        f.write(",".join(map(str,[
            time.time(), a_bid, a_ask, b_bid, b_ask, edge_ab, edge_ba, state
        ])) + "\n")

def log_fill(role, venue, side, price, qty, pnl=None):
    with _PATH.open("a") as f:
        f.write(",".join(map(str,[
            time.time(), role, venue, side, price, qty, "" if pnl is None else pnl
        ])) + "\n")
