from typing import List, Tuple

def exec_price(side: str, book: dict, size: float) -> float:
    """
    side: 'buy' -> walk ASKS, 'sell' -> walk BIDS
    book: {'bids': [(px,qty),...], 'asks': [(px,qty),...]}
    size: BTC size to execute
    returns VWAP fill price for requested size; raises if not enough liq
    """
    levels: List[Tuple[float, float]] = book['asks'] if side == 'buy' else book['bids']
    remain = float(size)
    if remain <= 0 or not levels:
        raise ValueError("bad size or empty book")

    cost = 0.0
    filled = 0.0
    for px, qty in levels:
        take = qty if qty <= remain else remain
        cost += take * px
        filled += take
        remain -= take
        if remain <= 0:
            break

    if remain > 1e-12:
        raise RuntimeError("insufficient depth for requested size")
    return cost / filled
