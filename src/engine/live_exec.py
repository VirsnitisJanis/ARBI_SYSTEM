import os, asyncio, ccxt

def _dry():
    return os.getenv("DRY_RUN","1") == "1" or os.getenv("LIVE_CONFIRM","NO") != "YES"

def _pad(px, bps, side):
    # bps -> multiplikators taker hedžam
    m = bps/10000.0
    if side == "buy":  return px * (1 + m)
    if side == "sell": return px * (1 - m)
    return px

class LiveVenue:
    def __init__(self, name):
        self.name = name
        self.x = getattr(ccxt, name)()
    async def ticker(self, pair):
        return await asyncio.to_thread(self.x.fetch_ticker, pair)
    async def taker_buy(self, pair, notional_usdc, ref_px, slippage_bps):
        if _dry(): return {"dry":True,"side":"buy","px":_pad(ref_px,slippage_bps,"buy")}
        amt = notional_usdc / _pad(ref_px,slippage_bps,"buy")
        o = await asyncio.to_thread(self.x.create_order, pair, "market", "buy", amt)
        return {"dry":False,"order":o}
    async def taker_sell(self, pair, qty_btc, ref_px, slippage_bps):
        if _dry(): return {"dry":True,"side":"sell","px":_pad(ref_px,slippage_bps,"sell")}
        o = await asyncio.to_thread(self.x.create_order, pair, "market", "sell", qty_btc)
        return {"dry":False,"order":o}
