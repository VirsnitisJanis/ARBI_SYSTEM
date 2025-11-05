import asyncio
import json

import websockets

PAIRS = {
    "ab": "btcusdc",   # USDC -> BTC
    "bc": "ethbtc",    # BTC -> ETH
    "ac": "ethusdc"    # ETH -> USDC
}

def ws_url(pair):
    return f"wss://stream.binance.com:9443/ws/{pair}@bookTicker"

class TriStream:
    def __init__(self):
        self.books = {"ab": None, "bc": None, "ac": None}

    async def sub_pair(self, key):
        url = ws_url(PAIRS[key])
        while True:
            try:
                async with websockets.connect(url) as ws:
                    while True:
                        msg = json.loads(await ws.recv())
                        self.books[key] = (
                            float(msg["b"]),
                            float(msg["a"])
                        )
            except Exception:
                await asyncio.sleep(0.5)
                continue

    async def start(self):
        tasks = []
        for k in self.books.keys():
            tasks.append(asyncio.create_task(self.sub_pair(k)))
        await asyncio.gather(*tasks)
