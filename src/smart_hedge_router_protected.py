import asyncio, os, ccxt, time
from utils.balances import snapshot, get, adjust
from notify import send
from heartbeat import beat
from risk_guard import check_pnl, check_orders

PAIR = os.getenv("PAIR", "BTC/USDC")
EDGE_OPEN = float(os.getenv("EDGE_OPEN_BPS", "2.0"))
HEDGE_SIZE = float(os.getenv("HEDGE_SIZE_BTC", "0.0004"))
ADAPTIVE_COEFF = float(os.getenv("ADAPTIVE_COEFF", "0.6"))
CHECK_INTERVAL = float(os.getenv("CHECK_INTERVAL_S", "1.5"))
STOP_PNL = float(os.getenv("STOP_PNL_USD", "-0.10"))
RECOVERY_WAIT = float(os.getenv("RECOVERY_WAIT_S", "60"))

ex = {
    "binance": ccxt.binance({
        "apiKey": os.getenv("BINANCE_API_KEY"),
        "secret": os.getenv("BINANCE_SECRET_KEY"),
        "enableRateLimit": True,
    }),
    "kucoin": ccxt.kucoin({
        "apiKey": os.getenv("KUCOIN_API_KEY"),
        "secret": os.getenv("KUCOIN_SECRET_KEY"),
        "enableRateLimit": True,
    }),
    "kraken": ccxt.kraken({
        "apiKey": os.getenv("KRAKEN_API_KEY"),
        "secret": os.getenv("KRAKEN_SECRET_KEY"),
        "enableRateLimit": True,
    }),
}

async def get_spreads(pair):
    tickers = {}
    for v, api in ex.items():
        try:
            t = await asyncio.to_thread(api.fetch_ticker, pair)
            tickers[v] = (t["bid"], t["ask"])
        except Exception:
            tickers[v] = (None, None)
    return tickers

async def post_only_order(venue, side, price, size):
    api = ex[venue]
    try:
        order = await asyncio.to_thread(
            api.create_order,
            PAIR, "limit", side, size, price, {"postOnly": True}
        )
        print(f"[ORDER] {venue} {side.upper()} {size}@{price}")
        return order
    except Exception as e:
        print(f"[ORDER ERR] {venue} {side}: {e}")
        return None

async def router_loop(pair):
    print(f"[BOOT] Smart Hedge Router (Protected) — {pair}")
    send(f"🧠 Smart Hedge Router (Protected) live — {pair}")
    last_edge, halted = 0, False

    while True:
        beat()
        # === Risk Guard pre-check ===
        check_orders()
        ok = check_pnl()
        if not ok:
            send("🛑 Trading paused due to risk breach.")
            halted = True
            await asyncio.sleep(RECOVERY_WAIT)
            continue

        if halted:
            send("♻️ Risk recovered — resuming trading.")
            halted = False

        spreads = await get_spreads(pair)
        valid = {v: s for v, s in spreads.items() if s[0] and s[1]}
        if len(valid) < 2:
            await asyncio.sleep(2)
            continue

        best_bid_v, best_bid = max(valid.items(), key=lambda x: x[1][0])
        best_ask_v, best_ask = min(valid.items(), key=lambda x: x[1][1])
        bid, ask = best_bid[0], best_ask[1]
        mid = (bid + ask) / 2
        edge = ((bid - ask) / mid) * 10000
        adj_edge = ADAPTIVE_COEFF * edge + (1 - ADAPTIVE_COEFF) * last_edge
        last_edge = adj_edge

        print(f"[EDGE] raw={edge:.2f} adj={adj_edge:.2f} | buy={best_ask_v}@{ask:.2f} → sell={best_bid_v}@{bid:.2f}")

        if adj_edge > EDGE_OPEN:
            print(f"[EXEC] Trigger hedge {best_ask_v}→{best_bid_v} | edge={adj_edge:.2f}")
            send(f"⚡ HEDGE EXEC\nBuy={best_ask_v}@{ask}\nSell={best_bid_v}@{bid}\nEdge={adj_edge:.2f}")
            size = HEDGE_SIZE
            buy_order = await post_only_order(best_ask_v, "buy", ask, size)
            sell_order = await post_only_order(best_bid_v, "sell", bid, size)

            if buy_order and sell_order:
                pnl = (bid - ask) * size
                adjust(best_ask_v, "BTC", size)
                adjust(best_bid_v, "BTC", -size)
                print(f"[HEDGE OK] PnL={pnl:.5f} USD | {snapshot()}")
                send(f"💰 Hedge done PnL={pnl:.5f}\nSnap: {snapshot()}")

        await asyncio.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    try:
        asyncio.run(router_loop(PAIR))
    except KeyboardInterrupt:
        print("exit")
