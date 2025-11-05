from dataclasses import dataclass

@dataclass
class TriSymbols:
    base: str
    mid: str
    quote: str
    a_b: str
    b_c: str
    a_c: str

def make_tri_symbols(base="USDT", mid="BTC", quote="ETH"):
    return TriSymbols(
        base=base,
        mid=mid,
        quote=quote,
        a_b=f"{mid}{base}",   # BTCUSDT
        b_c=f"{quote}{mid}",  # ETHBTC
        a_c=f"{quote}{base}"  # ETHUSDT
    )

class PriceBus:
    def __init__(self):
        self.books = {}

    def update(self, symbol, bid, ask):
        self.books[symbol] = {"bid": bid, "ask": ask}

    def get(self, symbol):
        return self.books.get(symbol)

class TriEngine:
    def __init__(self, symbols: TriSymbols, fee=0.001):
        self.s = symbols
        self.fee = fee

    def compute_edge(self, ab, bc, ac):
        # buy A->B, B->C, sell C->A
        a_to_b = 1 / ab["ask"] * (1 - self.fee)
        b_to_c = a_to_b / bc["ask"] * (1 - self.fee)
        c_to_a = b_to_c * ac["bid"] * (1 - self.fee)
        return c_to_a - 1

class RiskLayer:
    def check(self):
        return True

class Router:
    async def execute(self, direction):
        print("[EXEC] Dummy router - no real trade yet")
        return {"status": "ok", "mode": "dry"}
