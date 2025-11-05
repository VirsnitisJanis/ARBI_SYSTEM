import os
import ccxt.async_support as ccxt  # async version

class CEX:
    def __init__(self, name):
        self.name = name
        self.client = getattr(ccxt, name)({
            "apiKey": os.getenv(f"{name.upper()}_KEY"),
            "secret": os.getenv(f"{name.upper()}_SECRET")
        })

    async def ticker(self, pair):
        return await self.client.fetch_ticker(pair)

    async def balance(self):
        return await self.client.fetch_balance()

    async def buy(self, pair, amount):
        return await self.client.create_order(pair, 'market', 'buy', amount)

    async def sell(self, pair, amount):
        return await self.client.create_order(pair, 'market', 'sell', amount)

    async def close(self):
        await self.client.close()
