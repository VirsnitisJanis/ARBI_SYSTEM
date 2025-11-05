import asyncio
import json

import websockets

BINANCE_WS = "wss://stream.binance.com:9443/ws/btcusdt@ticker"

async def listen_binance():
    print("[WS] Connecting → Binance BTCUSDT ticker")
    async with websockets.connect(BINANCE_WS) as ws:
        print("[WS] Connected. Streaming...")
        while True:
            msg = json.loads(await ws.recv())
            bid = msg.get("b")  # best bid
            ask = msg.get("a")  # best ask
            if bid and ask:
                print(f"Bid: {bid} | Ask: {ask}")

async def main():
    await listen_binance()

if __name__ == "__main__":
    asyncio.run(main())
