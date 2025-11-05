import os, time
from utils.quant import bps, round_price, round_amount

EDGE_OPEN = float(os.getenv("EDGE_OPEN_BPS", "3"))    # open slieksnis
EDGE_CANCEL = float(os.getenv("EDGE_CANCEL_BPS", "1"))
TTL = int(os.getenv("MAKER_TTL_S", "4"))
PAD = float(os.getenv("PRICE_PAD_BPS", "1"))
NOTIONAL = float(os.getenv("QUANTITY_USDC", "25"))

class MMRouter:
    def __init__(self, bnx, kuc, pair):
        self.bnx = bnx
        self.kuc = kuc
        self.pair = pair
        self.positions = 0.0
        self.open_gross = 0.0
        self.live = {}  # oid → meta

    async def _sizes(self, market_b, market_k):
        # amount step/tick
        step_b = market_b['limits']['amount']['min'] or market_b['precision'].get('amount', 1e-6)
        step_k = market_k['limits']['amount']['min'] or market_k['precision'].get('amount', 1e-6)
        tick_b = market_b['precision']['price']
        tick_k = market_k['precision']['price']
        return step_b, step_k, tick_b, tick_k

    async def place_both(self, b_bid, b_ask, k_bid, k_ask, market_b, market_k):
        # Ja Binance dārgāks => sell on Binance (maker ask pad), buy on KuCoin (maker bid pad)
        # Ja KuCoin dārgāks => sell on KuCoin, buy on Binance
        step_b, step_k, tick_b, tick_k = await self._sizes(market_b, market_k)

        # aprēķini daudzumu no NOTIONAL / mid
        mid_b = (b_bid + b_ask)/2.0
        amt = NOTIONAL / mid_b
        amt_b = round_amount(amt, step_b)
        amt_k = round_amount(amt, step_k)
        amt_use = max(min(amt_b, amt_k), 0.0)

        # kotēšanas cenas ar PAD
        b_sell_px = round_price(b_ask * (1 + bps(PAD)), tick_b)
        b_buy_px  = round_price(b_bid * (1 - bps(PAD)), tick_b)
        k_sell_px = round_price(k_ask * (1 + bps(PAD)), tick_k)
        k_buy_px  = round_price(k_bid * (1 - bps(PAD)), tick_k)

        return amt_use, b_sell_px, b_buy_px, k_sell_px, k_buy_px

    async def open_mm(self, side_expensive, amt, b_sell, b_buy, k_sell, k_buy):
        # side_expensive: 'binance' vai 'kucoin' — kur pārdodam
        if amt <= 0: return None
        if side_expensive == 'binance':
            o1 = await self.bnx.create_postonly_limit(self.pair, 'sell', amt, b_sell, TTL)
            o2 = await self.kuc.create_postonly_limit(self.pair, 'buy',  amt, k_buy, TTL)
        else:
            o1 = await self.kuc.create_postonly_limit(self.pair, 'sell', amt, k_sell, TTL)
            o2 = await self.bnx.create_postonly_limit(self.pair, 'buy',  amt, b_buy, TTL)
        self.open_gross += amt * (o1['price'] + o2['price'])/2.0
        now = time.time()
        self.live[o1['id']] = {'ex':'exp','ts':now,'side':'sell','amt':amt}
        self.live[o2['id']] = {'ex':'cheap','ts':now,'side':'buy','amt':amt}
        print(f"[OPEN] {side_expensive.upper()} sell & OTHER buy | amt={amt} prices=({o1['price']},{o2['price']})")
        return o1, o2

    async def cancel_all_if_edge_drops(self, pair, cur_edge_bps):
        if abs(cur_edge_bps) >= EDGE_CANCEL: return
        # atcelt visus atvērtos postOnly
        for ex, cli in (('binance', self.bnx), ('kucoin', self.kuc)):
            try:
                opens = await cli.fetch_open_orders(pair)
                for o in opens:
                    await cli.cancel(pair, o['id'])
                    self.open_gross = max(0.0, self.open_gross - o['amount'] * o['price'])
                    print(f"[CANCEL] {ex} {o['side']} {o['amount']} @ {o['price']} (edge fell)")
            except Exception as e:
                print("[CANCEL_ERR]", ex, e)
