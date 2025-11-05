import time, random
from utils.balances import adjust, snapshot
from sim.orderbook_sim import SimOrderBook

sim = SimOrderBook(latency_ms=30, fill_prob=0.35, slippage_bps=0.25)

def place_maker(side, venue, price, size):
    return {
        "side": side,
        "venue": venue,
        "price": price,
        "size": size,
        "ts": time.time(),
        "filled": False
    }

async def process_maker(order, bid, ask):
    filled, slip_price, size = await sim.place_maker(
        order["side"], order["price"], order["size"], bid, ask
    )

    if not filled:
        return False, "NO_FILL"

    # simulate hedge instantly (no risk module yet)
    pnl = (ask - slip_price) * size if order["side"]=="buy" else (slip_price - bid) * size

    adjust(order["venue"], "BTC",  size if order["side"]=="buy" else -size)
    adjust(order["venue"], "USDC", -slip_price*size if order["side"]=="buy" else slip_price*size)

    return True, pnl
