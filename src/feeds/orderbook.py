import asyncio, ccxt
from typing import Dict

class OrderBookFetcher:
    def __init__(self, limit:int=20):
        self.limit = limit
        self.a = ccxt.binance()
        self.b = ccxt.kucoin()

    async def fetch_one(self, ex, pair:str) -> Dict[str, list]:
        ob = await asyncio.to_thread(ex.fetch_order_book, pair, self.limit)
        # normalize to [(price, amount), ...]
        bids = [(float(p), float(q)) for p,q in ob.get('bids',[])]
        asks = [(float(p), float(q)) for p,q in ob.get('asks',[])]
        return {'bids': bids, 'asks': asks}

    async def fetch_both(self, pair:str):
        a_task = asyncio.create_task(self.fetch_one(self.a, pair))
        b_task = asyncio.create_task(self.fetch_one(self.b, pair))
        a_book, b_book = await asyncio.gather(a_task, b_task)
        return a_book, b_book
