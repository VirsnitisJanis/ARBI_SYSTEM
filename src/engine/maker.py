import time, asyncio

class MakerEngine:
    def __init__(self, ex_a, ex_b, ttl_s: int, pad_bps: float):
        self.ex_a = ex_a
        self.ex_b = ex_b
        self.ttl  = ttl_s
        self.pad  = pad_bps / 10000.0

    async def _client(self, venue):
        return self.ex_a if venue == "binance" else self.ex_b

    async def place_limit(self, venue, pair, side, ref_px, qty):
        # nedaudz “iekšā” grāmatā, lai fill notiktu, bet joprojām maker
        px = ref_px * (1 + self.pad if side == "buy" else 1 - self.pad)
        px = float(f"{px:.2f}")  # BTC/USDC parasti 2 dec.
        ex = await self._client(venue)
        o  = await ex.create_order(symbol=pair.replace("/", ""), type="limit", side=side, price=px, amount=qty)
        return o["id"], px

    async def wait_or_cancel(self, venue, pair, order_id):
        ex = await self._client(venue)
        t0 = time.time()
        while time.time() - t0 < self.ttl:
            try:
                o = await ex.fetch_order(order_id, pair)
                if o.get("status") == "closed":
                    return True, o
            except Exception:
                pass
            await asyncio.sleep(0.25)
        try:
            await ex.cancel_order(order_id, pair)
        except Exception:
            pass
        return False, None

    async def run(self, venue, pair, side, ref_px, qty):
        oid, px = await self.place_limit(venue, pair, side, ref_px, qty)
        filled, order = await self.wait_or_cancel(venue, pair, oid)
        return filled, px, order
