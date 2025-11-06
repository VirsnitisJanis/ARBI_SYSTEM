import time

def place_post_only(side, venue, price, size, ttl_s, pad_bps):
    px = price
    if side == "buy":
        px = price * (1 - pad_bps/10000.0)  # zem bid → noteikti resting
    else:
        px = price * (1 + pad_bps/10000.0)  # virs ask → noteikti resting
    return {
        "side": side, "venue": venue, "price": px, "size": float(size),
        "ts": time.time(), "expiry": time.time() + ttl_s, "filled": False
    }

def process_post_only(order, bid, ask):
    """
    Vienkāršots simulators:
    - BUY fillējas, ja tirgus nokrīt līdz order.price vai zemāk (ask <= price)
    - SELL fillējas, ja tirgus uzkāpj līdz order.price vai augstāk (bid >= price)
    - EXPIRE, ja pārsniedz TTL
    Atgriež: (status, reason, fill_px, fill_qty)
      status: True=filled, False=expired, None=open
    """
    now = time.time()
    if now >= order["expiry"]:
        return (False, "EXPIRED", None, 0.0)

    if order["side"] == "buy":
        if ask is not None and ask <= order["price"]:
            return (True, "FILLED", order["price"], order["size"])
    else:
        if bid is not None and bid >= order["price"]:
            return (True, "FILLED", order["price"], order["size"])
    return (None, None, None, 0.0)
