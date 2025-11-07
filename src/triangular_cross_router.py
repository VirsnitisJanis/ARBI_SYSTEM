import os, ccxt, time, asyncio, traceback, requests

ex = {
    "binance": ccxt.binance({'apiKey':os.getenv('BINANCE_API_KEY'),'secret':os.getenv('BINANCE_SECRET_KEY')}),
    "kucoin":  ccxt.kucoin({'apiKey':os.getenv('KUCOIN_API_KEY'),'secret':os.getenv('KUCOIN_SECRET_KEY'),'password':os.getenv('KUCOIN_PASSPHRASE')}),
    "kraken":  ccxt.kraken({'apiKey':os.getenv('KRAKEN_API_KEY'),'secret':os.getenv('KRAKEN_SECRET_KEY')}),
}

# Katras biržas faktiskie pāri
PAIRS = {
    "binance": {"BTCUSDC":"BTC/USDC", "BTCUSDT":"BTC/USDT", "USDTUSDC":"USDT/USDC"},
    "kucoin":  {"BTCUSDC":"BTC/USDC", "BTCUSDT":"BTC/USDT", "USDTUSDC":"USDT/USDC"},
    "kraken":  {"BTCUSD":"BTC/USD",   "BTCUSDT":"BTC/USDT", "USDTUSD":"USDT/USD"},
}

EDGE_OPEN_BPS = float(os.getenv("EDGE_OPEN_BPS",2))
COOLDOWN = 20
CHECK_INTERVAL = 3
HEDGE_SIZE = float(os.getenv("HEDGE_SIZE_BTC",0.0001))
DRY_RUN = int(os.getenv("DRY_RUN",1))
TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT = os.getenv("TG_CHAT_ID")
last_exec = 0

def tg(msg):
    if not TG_TOKEN or not TG_CHAT: return
    try:
        requests.get(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                     params={"chat_id":TG_CHAT,"text":msg})
    except: pass

def safe_price(exh, symbol):
    try:
        t = exh.fetch_ticker(symbol)
        return (t["bid"] + t["ask"]) / 2
    except Exception:
        return None

def get_tri_rate(name, exh):
    try:
        p1 = safe_price(exh, PAIRS[name][list(PAIRS[name].keys())[0]])
        p2 = safe_price(exh, PAIRS[name][list(PAIRS[name].keys())[1]])
        p3 = safe_price(exh, PAIRS[name][list(PAIRS[name].keys())[2]])
        if None in [p1,p2,p3]:
            return None
        return (1/p1)*p2*p3
    except Exception:
        return None

async def execute_trade(buy_v, sell_v):
    try:
        buy_ex, sell_ex = ex[buy_v], ex[sell_v]
        pair = "BTC/USDC" if "USDC" in buy_ex.load_markets() else "BTC/USDT"
        buy_px = safe_price(buy_ex, pair)
        sell_px = safe_price(sell_ex, pair)
        if not buy_px or not sell_px: return
        msg = f"⚡ LIVE TRI-HEDGE\nBuy={buy_v}@{buy_px:.2f}\nSell={sell_v}@{sell_px:.2f}\nSize={HEDGE_SIZE}"
        print(msg); tg(msg)
        if DRY_RUN: return
        o1 = buy_ex.create_order(pair,"limit","buy",HEDGE_SIZE,buy_px)
        o2 = sell_ex.create_order(pair,"limit","sell",HEDGE_SIZE,sell_px)
        await asyncio.sleep(20)
        for n, ex_, oid in [(buy_v,buy_ex,o1['id']),(sell_v,sell_ex,o2['id'])]:
            try:
                od = ex_.fetch_order(oid)
                if od.get("status")!="closed":
                    ex_.cancel_order(oid)
                    print(f"[CANCEL] {n} order {oid}")
            except Exception: pass
    except Exception as e:
        print("[EXEC ERR]", e); traceback.print_exc()

async def main_loop():
    global last_exec
    print(f"[BOOT] Stage-39.2 FIX | EDGE>{EDGE_OPEN_BPS}bps | DRY_RUN={DRY_RUN}")
    while True:
        try:
            rates={n:get_tri_rate(n,e) for n,e in ex.items()}
            valid={n:r for n,r in rates.items() if r}
            if len(valid)<2:
                print("[WAIT] Missing pairs..."); await asyncio.sleep(5); continue
            cheap,exp=min(valid.items(),key=lambda x:x[1]),max(valid.items(),key=lambda x:x[1])
            edge=(exp[1]-cheap[1])/cheap[1]*1e4
            if edge>EDGE_OPEN_BPS:
                now=time.time()
                if now-last_exec>COOLDOWN:
                    await execute_trade(cheap[0],exp[0])
                    last_exec=now
                else:
                    print(f"[SKIP] cooldown active ({int(now-last_exec)}s) | edge={edge:.2f}")
            else:
                print(f"[NET] {cheap[0]}→{exp[0]} edge={edge:.2f} bps")
            await asyncio.sleep(CHECK_INTERVAL)
        except Exception as e:
            print("[ERR]", e); traceback.print_exc(); await asyncio.sleep(5)

asyncio.run(main_loop())
