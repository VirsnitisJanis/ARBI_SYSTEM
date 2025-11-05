import asyncio
from exchanges.cex import CEX

class MidFeed:
    def __init__(self, pair):
        self.pair = pair
        self.binance = CEX("binance")
        self.kucoin = CEX("kucoin")
        self.data = {}

    async def run(self):
        while True:
            try:
                b = await self.binance.ticker(self.pair)
                k = await self.kucoin.ticker(self.pair)

                self.data = {
                    "binance": (b['bid'], b['ask']),
                    "kucoin": (k['bid'], k['ask'])
                }

                print(f"[MID] BNB {b['bid']} / {b['ask']} | KUC {k['bid']} / {k['ask']}")
            except Exception as e:
                print("[ERR feed]", e)

            await asyncio.sleep(0.25)
