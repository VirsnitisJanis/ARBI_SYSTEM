import os, asyncio, time, ccxt

print("[BOOT] Stage-39.3 SAFE EXEC (boot test v2)")

ex = {
 "binance": ccxt.binance({'apiKey':os.getenv('BINANCE_API_KEY'),'secret':os.getenv('BINANCE_SECRET_KEY')}),
 "kucoin":  ccxt.kucoin({'apiKey':os.getenv('KUCOIN_API_KEY'),'secret':os.getenv('KUCOIN_SECRET_KEY'),'password':os.getenv('KUCOIN_PASSPHRASE')}),
 "kraken":  ccxt.kraken({'apiKey':os.getenv('KRAKEN_API_KEY'),'secret':os.getenv('KRAKEN_SECRET_KEY')}),
}

# Iepriekš ielādē visus tirgus, lai nebūtu NoneType
for name, e in ex.items():
    try:
        e.load_markets()
        print(f"[LOAD] {name} markets → {len(e.markets)} loaded")
    except Exception as err:
        print(f"[ERR-LOAD] {name}", err)

async def main():
    while True:
        try:
            mids = {}
            for name, e in ex.items():
                symbol = "BTC/USDC" if "BTC/USDC" in e.markets else "BTC/USD"
                t = e.fetch_ticker(symbol)
                mids[name] = (t["bid"] + t["ask"]) / 2
            print("[HEARTBEAT]", time.strftime("%H:%M:%S"), mids)
            await asyncio.sleep(30)
        except Exception as err:
            print("[ERR]", err)
            await asyncio.sleep(10)

asyncio.run(main())
