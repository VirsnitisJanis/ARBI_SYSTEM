import asyncio
import json
import websockets

class BinanceWS:
    def __init__(self, bus, symbols):
        self.bus = bus
        self.symbols = symbols

    async def connect(self):
        stream = "/".join([s.lower() + "@bookTicker" for s in self.symbols])
        url = f"wss://stream.binance.com:9443/stream?streams={stream}"
        async with websockets.connect(url) as ws:
            while True:
                msg = json.loads(await ws.recv())
                data = msg.get("data", {})
                if "s" in data:
                    sym = data["s"]
                    bid = float(data["b"])
                    ask = float(data["a"])
                    self.bus.update(sym, bid, ask)
