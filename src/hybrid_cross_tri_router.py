import asyncio, os, json, time
from math import isfinite
import ccxt
from notify import send
from utils.balances import get as bal_get, adjust, snapshot as bal_snapshot
from heartbeat import beat

PAIR         = os.getenv("PAIR", "BTC/USDC")
HEDGE_SIZE   = float(os.getenv("HEDGE_SIZE_BTC", "0.00035"))
ADAPTIVE     = float(os.getenv("ADAPTIVE_COEFF", "0.6"))
CHECK_S      = float(os.getenv("CHECK_INTERVAL_S", "1.5"))

def load_edge_threshold_bps() -> float:
    try:
        with open("src/data/ai_params.json") as f:
            ai = json.load(f)
            v = float(ai.get("EDGE_OPEN_BPS", 0))
            if v > 0:
                return v
    except Exception:
        pass
    return float(os.getenv("EDGE_OPEN_BPS", "2.0"))

EDGE_OPEN_BPS = load_edge_threshold_bps()

def mid(tk):
    if not tk: return None
    b, a = tk.get("bid"), tk.get("ask")
    if b and a: return (b + a) / 2.0
    return tk.get("last")

def inv(x): return 1.0 / x if x and x > 0 else None

def ensure_pair(ex, base, quote):
    s1, s2 = f"{base}/{quote}", f"{quote}/{base}"
    try:
        tk = ex.fetch_ticker(s1)
        m = mid(tk)
        if m and isfinite(m): return (m, 1)
    except Exception: pass
    try:
        tk = ex.fetch_ticker(s2)
        m = mid(tk)
        if m and isfinite(m): return (inv(m), -1)
    except Exception: pass
    return (None, 0)

def local_tri_metrics(ex, name, pair="BTC/USDC"):
    base, quote = pair.split("/")
    if quote != "USDC":
        raise ValueError("Stage-38 paredz *USDC quote* pārus")

    btc_usdc, _ = ensure_pair(ex, "BTC", "USDC")
    btc_usdt, _ = ensure_pair(ex, "BTC", "USDT")
    usdt_usdc, _ = ensure_pair(ex, "USDT", "USDC")

    direct = btc_usdc or (btc_usdt * usdt_usdc if (btc_usdt and usdt_usdc) else None)
    synth  = (btc_usdt * usdt_usdc) if (btc_usdt and usdt_usdc) else None
    if direct and synth:
        diff = direct - synth
        bps = (diff / ((direct + synth) / 2.0)) * 10000.0
        return {"direct_btc_usdc": direct, "synth_btc_usdc": synth, "tri_diff_bps": bps}
    return {"direct_btc_usdc": direct, "synth_btc_usdc": synth, "tri_diff_bps": None}

def vwap_can_fill(ex, pair, side, qty_btc):
    try:
        ob = ex.fetch_order_book(pair, limit=10)
    except Exception:
        return (False, None)
    levels = ob["asks"] if side == "buy" else ob["bids"]

    # FIX: daži līmeņi satur [price, size, cost]; mēs ņemam tikai pirmās 2
    cleaned = []
    for lvl in levels:
        if isinstance(lvl, (list, tuple)) and len(lvl) >= 2:
            cleaned.append((lvl[0], lvl[1]))
    if not cleaned:
        return (False, None)

    need = qty_btc
    cost, got = 0.0, 0.0
    for px, sz in cleaned:
        take = min(need, sz)
        cost += take * px
        got += take
        need -= take
        if need <= 1e-12:
            break
    if got + 1e-12 < qty_btc:
        return (False, None)
    vwap = cost / got
    return (True, vwap)

def have_balances_for_hedge(name_buy, name_sell, size_btc, px_buy, px_sell):
    usdc_need = size_btc * px_buy * 1.002
    btc_need = size_btc * 1.001
    usdc_ok = bal_get(name_buy, "USDC") >= usdc_need
    btc_ok = bal_get(name_sell, "BTC") >= btc_need
    return usdc_ok and btc_ok

async def create_post_only(ex, venue, pair, side, size, price):
    try:
        o = await asyncio.to_thread(ex.create_order, pair, "limit", side, size, price, {"postOnly": True})
        print(f"[ORDER] {venue} {side.upper()} {size}@{price}")
        return o
    except Exception as e:
        print(f"[ORDER ERR] {venue} {side}: {e}")
        return None

def mk_clients():
    return {
        "binance": ccxt.binance({
            "apiKey": os.getenv("BINANCE_API_KEY"),
            "secret": os.getenv("BINANCE_SECRET_KEY"),
            "enableRateLimit": True,
        }),
        "kucoin": ccxt.kucoin({
            "apiKey": os.getenv("KUCOIN_API_KEY"),
            "secret": os.getenv("KUCOIN_SECRET_KEY"),
            "password": os.getenv("KUCOIN_PASSPHRASE"),
            "enableRateLimit": True,
        }),
        "kraken": ccxt.kraken({
            "apiKey": os.getenv("KRAKEN_API_KEY"),
            "secret": os.getenv("KRAKEN_SECRET_KEY"),
            "enableRateLimit": True,
        }),
    }

async def main_loop():
    ex = mk_clients()
    last_edge = 0.0
    send(f"🧩 Stage-38 FIX Hybrid Router live — {PAIR}")

    while True:
        beat()
        metrics = {}
        for name, cli in ex.items():
            try:
                metrics[name] = await asyncio.to_thread(local_tri_metrics, cli, name, PAIR)
            except Exception:
                metrics[name] = {"direct_btc_usdc": None, "synth_btc_usdc": None, "tri_diff_bps": None}
        avail = {n:m for n,m in metrics.items() if m["direct_btc_usdc"]}
        if len(avail) < 2:
            await asyncio.sleep(2)
            continue

        eff = {n:(m["synth_btc_usdc"] or m["direct_btc_usdc"]) for n,m in avail.items()}
        buy_venue  = min(eff.items(), key=lambda x:x[1])[0]
        sell_venue = max(eff.items(), key=lambda x:x[1])[0]
        buy_px, sell_px = eff[buy_venue], eff[sell_venue]
        mid_px = (buy_px + sell_px) / 2
        raw_edge = ((sell_px - buy_px)/mid_px)*10000
        adj_edge = ADAPTIVE*raw_edge + (1-ADAPTIVE)*last_edge
        last_edge = adj_edge
        print(f"[NET] raw={raw_edge:.2f} bps adj={adj_edge:.2f} | buy={buy_venue}@{buy_px:.2f} → sell={sell_venue}@{sell_px:.2f}")

        if adj_edge < EDGE_OPEN_BPS:
            await asyncio.sleep(CHECK_S)
            continue

        ok_buy, vwap_buy  = await asyncio.to_thread(vwap_can_fill, ex[buy_venue],  PAIR, "buy",  HEDGE_SIZE)
        ok_sell,vwap_sell = await asyncio.to_thread(vwap_can_fill, ex[sell_venue], PAIR, "sell", HEDGE_SIZE)
        if not (ok_buy and ok_sell):
            print("[DEPTH] insufficient depth")
            await asyncio.sleep(CHECK_S)
            continue

        if not have_balances_for_hedge(buy_venue, sell_venue, HEDGE_SIZE, vwap_buy, vwap_sell):
            print("[BAL] insufficient balances")
            await asyncio.sleep(CHECK_S)
            continue

        send(f"⚡ HYBRID EXEC\nBuy={buy_venue}@{round(vwap_buy,2)}\nSell={sell_venue}@{round(vwap_sell,2)}\nEdge={adj_edge:.2f}bps")

        buy_o  = await create_post_only(ex[buy_venue],  buy_venue,  PAIR, "buy",  HEDGE_SIZE, vwap_buy)
        sell_o = await create_post_only(ex[sell_venue], sell_venue, PAIR, "sell", HEDGE_SIZE, vwap_sell)
        if buy_o and sell_o:
            pnl = (vwap_sell - vwap_buy)*HEDGE_SIZE
            adjust(buy_venue,"BTC",HEDGE_SIZE)
            adjust(buy_venue,"USDC",-HEDGE_SIZE*vwap_buy)
            adjust(sell_venue,"BTC",-HEDGE_SIZE)
            adjust(sell_venue,"USDC",HEDGE_SIZE*vwap_sell)
            print(f"[HEDGE OK] estPnL={pnl:.4f} | snap={bal_snapshot()}")
            send(f"✅ HYBRID FILL\nPair: {PAIR}\nA: {buy_venue}\nB: {sell_venue}\nPnL≈{round(pnl,4)}")

        await asyncio.sleep(CHECK_S)

if __name__=="__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        print("exit")
