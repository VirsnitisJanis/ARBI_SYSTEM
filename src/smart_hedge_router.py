import asyncio
import os
import random
import time
import ccxt
from utils.balances import snapshot, get, adjust
from notify import send
from heartbeat import beat

PAIR = os.getenv("PAIR", "BTC/USDC")
VENUES = ["binance", "kucoin", "kraken"]
EDGE_OPEN = float(os.getenv("EDGE_OPEN_BPS", "2.0"))
MAX_INV_BTC = float(os.getenv("MAX_INV_BTC", "0.0025"))
HEDGE_SIZE = float(os.getenv("HEDGE_SIZE_BTC", "0.0004"))
ADAPTIVE_COEFF = float(os.getenv("ADAPTIVE_COEFF", "0.6"))
CHECK_INTERVAL = float(os.getenv("CHECK_INTERVAL_S", "1.0"))

# --- ielādē ccxt klientus
ex = {
    "binance": ccxt.binance(),
    "kucoin": ccxt.kucoin(),
    "kraken": ccxt.kraken()
}

async def get_spreads(pair):
    tickers = {}
    for v in VENUES:
        try:
            t = await asyncio.to_thread(ex[v].fetch_ticker, pair)
            tickers[v] = (t["bid"], t["ask"])
        except Exception:
            tickers[v] = (None, None)
    return tickers

async def smart_route(pair):
    print(f"[BOOT] Smart Hedge Router — {pair}")
    send(f"🧠 Smart Hedge Router active — monitoring {pair}")

    last_edge = 0
    while True:
        beat()
        spreads = await get_spreads(pair)

        valid = {v: s for v, s in spreads.items() if s[0] and s[1]}
        if len(valid) < 2:
            print("[WAIT] not enough venues alive")
            await asyncio.sleep(2)
            continue

        # atrodam labāko bid/ask
        best_bid_v, best_bid = max(valid.items(), key=lambda x: x[1][0])
        best_ask_v, best_ask = min(valid.items(), key=lambda x: x[1][1])
        bid, ask = best_bid[0], best_ask[1]

        mid = (bid + ask) / 2
        edge = ((bid - ask) / mid) * 10000
        adj_edge = ADAPTIVE_COEFF * edge + (1 - ADAPTIVE_COEFF) * last_edge
        last_edge = adj_edge

        print(f"[EDGE] raw={edge:.2f} adj={adj_edge:.2f} best_bid={best_bid_v}@{bid:.2f} best_ask={best_ask_v}@{ask:.2f}")

        # automātiska robežu adaptācija
        dyn_open = EDGE_OPEN * (1 + abs(adj_edge) / 100)
        if adj_edge > dyn_open and get(best_ask_v, "USDC") > 10:
            print(f"[ROUTE] {best_ask_v} → {best_bid_v} | edge={adj_edge:.2f}")
            send(f"⚡ Routed hedge {pair}\nBuy @{best_ask_v} → Sell @{best_bid_v}\nEdge={adj_edge:.2f}bps")

            # simulē hedžus
            adjust(best_ask_v, "BTC", +HEDGE_SIZE)
            adjust(best_bid_v, "BTC", -HEDGE_SIZE)
            pnl = (bid - ask) * HEDGE_SIZE
            print(f"[HEDGE] Simulated PnL: {pnl:.5f} USD | {snapshot()}")
            send(f"💰 Smart Hedge Executed\nPnL={pnl:.5f}\nWallets: {snapshot()}")

        await asyncio.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    try:
        asyncio.run(smart_route(PAIR))
    except KeyboardInterrupt:
        print("exit")
