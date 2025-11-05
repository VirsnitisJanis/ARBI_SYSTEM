from math import floor
import asyncio

class HedgeEngine:
    def __init__(self, ex_a, ex_b, dry_run: bool, fee_bps_a: float, fee_bps_b: float, balances):
        self.ex_a = ex_a
        self.ex_b = ex_b
        self.dry = dry_run
        self.fee = {"binance": fee_bps_a/10000.0, "kucoin": fee_bps_b/10000.0}
        self.bal = balances  # module with add()/snapshot()

    async def _client(self, venue):
        return self.ex_a if venue == "binance" else self.ex_b

    async def _side_px(self, ex, pair, side):
        t = await ex.fetch_ticker(pair)
        return float(t["ask"]) if side == "buy" else float(t["bid"])

    async def market(self, venue, pair, side, notional_usdc):
        ex  = await self._client(venue)
        px  = await self._side_px(ex, pair, side)
        qty = max(1e-6, round(float(notional_usdc)/px, 6))  # BTC qty

        if self.dry:
            fee = notional_usdc * self.fee[venue]
            # bilanču update (USDC↔BTC)
            if side == "buy":
                self.bal.add(venue, "USDC", -notional_usdc - fee)
                self.bal.add(venue, "BTC",  +qty)
            else:
                self.bal.add(venue, "BTC",  -qty)
                self.bal.add(venue, "USDC", +notional_usdc - fee)
            return {"price": px, "amount": qty, "fee_usdc": fee, "dry": True}

        o = await ex.create_order(symbol=pair.replace("/", ""), type="market", side=side, amount=qty)
        # vienkāršs fee aprēķins pēc taker bps
        fee = notional_usdc * self.fee[venue]
        if side == "buy":
            self.bal.add(venue, "USDC", -notional_usdc - fee)
            self.bal.add(venue, "BTC",  +qty)
        else:
            self.bal.add(venue, "BTC",  -qty)
            self.bal.add(venue, "USDC", +notional_usdc - fee)
        return {"order": o, "price": px, "amount": qty, "fee_usdc": fee, "dry": False}
