import asyncio
import os

import ccxt
from dotenv import load_dotenv

load_dotenv()

class Spot:
    def __init__(self, name):
        if name == "binance":
            self.x = ccxt.binance({'enableRateLimit': True})
            key, sec = os.getenv('BINANCE_API_KEY'), os.getenv('BINANCE_SECRET')
        elif name == "kucoin":
            self.x = ccxt.kucoin({'enableRateLimit': True})
            key = os.getenv('KUCOIN_API_KEY')
            sec = os.getenv('KUCOIN_SECRET')
            pwd = os.getenv('KUCOIN_PASSWORD')
        else:
            raise ValueError(name)
        if key and sec:
            self.x.apiKey, self.x.secret = key, sec
            if name == "kucoin" and pwd:
                self.x.password = pwd
    async def load_markets(self):
        return await asyncio.to_thread(self.x.load_markets)

    async def ticker(self, pair):
        return await asyncio.to_thread(self.x.fetch_ticker, pair)

    async def orderbook(self, pair, depth=20):
        return await asyncio.to_thread(self.x.fetch_order_book, pair, depth)

    async def balance(self):
        return await asyncio.to_thread(self.x.fetch_balance)

    async def market(self, pair):
        m = self.x.market(pair)
        return m

    async def create_postonly_limit(self, pair, side, amount, price, ttl_sec=5):
        params = {'postOnly': True}
        order = await asyncio.to_thread(self.x.create_order, pair, 'limit', side, amount, price, params)
        oid = order['id']
        # ieliec timed cancel
        async def _ttl():
            try:
                await asyncio.sleep(ttl_sec)
                await asyncio.to_thread(self.x.cancel_order, oid, pair)
            except Exception:
                pass
        asyncio.create_task(_ttl())
        return order

    async def cancel(self, pair, oid):
        return await asyncio.to_thread(self.x.cancel_order, oid, pair)

    async def fetch_open_orders(self, pair):
        return await asyncio.to_thread(self.x.fetch_open_orders, pair)

    async def fetch_my_trades(self, pair, since=None, limit=50):
        return await asyncio.to_thread(self.x.fetch_my_trades, pair, since, limit)
