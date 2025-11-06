import asyncio
import json
import math
import os
import time
from collections import defaultdict

import aiohttp
import websockets

# Projekta notifieris (TG brīdinājumiem). Ja nav vajadzīgs, atkomentē pasīvo adapteri zemāk.
from notify import send

# Pasīvais adapteris (ja nav notify.py pieejams):
# def send(msg: str): print("[TG]", msg)

# ─────────────────────────────────────────────────────────────
# ENV
# ─────────────────────────────────────────────────────────────
PAIRS = [p.strip() for p in os.getenv("PAIRS", "BTC/USDC,ETH/USDC").split(",") if p.strip()]
REST_POLL_S = float(os.getenv("REST_POLL_S", "2.0"))
LOG_PATH = os.getenv("LAT_LOG", "logs/feed_latency.csv")
ALERT_LAT_MS = int(os.getenv("LAT_WARN_MS", "300"))         # brīdini, ja stāvēšana > 300ms
ALERT_SUMMARY_S = int(os.getenv("LAT_SUMMARY_S", "900"))    # reizi 15 min kopsavilkums TG
EDGE_PRINT_S = float(os.getenv("EDGE_PRINT_S", "2.0"))      # cik bieži konsolē rādīt edge

# ─────────────────────────────────────────────────────────────
# Palīgfunkcijas
# ─────────────────────────────────────────────────────────────
def now_ms() -> int:
    return int(time.time() * 1000)

def safe_float(x, default=None):
    try:
        return float(x)
    except Exception:
        return default

def bsymbol_binance(pair: str) -> str:
    # "BTC/USDC" -> "btcusdc"
    return pair.replace("/", "").lower()

def kpair_kraken(pair: str) -> str:
    # Kraken simbolu īpatnības: BTC ir "XBT". USDC paliek USDC.
    base, quote = pair.split("/")
    base = "XBT" if base.upper() == "BTC" else base.upper()
    quote = quote.upper()
    return f"{base}/{quote}"

# ─────────────────────────────────────────────────────────────
# Koplietotā kvotu noliktava + metrikas
# ─────────────────────────────────────────────────────────────
# quotes[(venue, pair)] = { 'bid': float, 'ask': float, 'src': 'ws'|'rest', 'ts_ms': int }
quotes = {}
# pēdējā REST roundtrip ms (tikai diagnosticēšanai)
rest_rtt_ms = defaultdict(lambda: math.nan)
# pēdējais WS notikums ms
ws_event_ms = defaultdict(lambda: math.nan)

# faila izveide
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
if not os.path.exists(LOG_PATH):
    with open(LOG_PATH, "w") as f:
        f.write("ts_ms,venue,pair,src,exch_ts_ms,latency_ms,bid,ask,rest_rtt_ms\n")

async def log_row(venue, pair, src, exch_ts_ms, latency_ms, bid, ask):
    with open(LOG_PATH, "a") as f:
        f.write(",".join([
            str(now_ms()),
            venue, pair, src,
            str(exch_ts_ms if exch_ts_ms is not None else ""),
            str(int(latency_ms) if latency_ms is not None else ""),
            str(bid if bid is not None else ""),
            str(ask if ask is not None else ""),
            str(int(rest_rtt_ms[(venue, pair)]) if not math.isnan(rest_rtt_ms[(venue, pair)]) else "")
        ]) + "\n")

def set_quote(venue, pair, bid, ask, src, exch_ts_ms=None):
    quotes[(venue, pair)] = {
        "bid": bid,
        "ask": ask,
        "src": src,
        "ts_ms": exch_ts_ms if exch_ts_ms is not None else now_ms()
    }

def get_quote(venue, pair):
    return quotes.get((venue, pair))

# ─────────────────────────────────────────────────────────────
# Binance WS (@ticker 24hr — satur "E" event time un "b","a")
# ─────────────────────────────────────────────────────────────
async def binance_ws_loop(pairs):
    # multi-stream: /stream?streams=btcusdc@ticker/ethusdc@ticker
    streams = "/".join([f"{bsymbol_binance(p)}@ticker" for p in pairs])
    url = f"wss://stream.binance.com:9443/stream?streams={streams}"

    while True:
        try:
            async with aiohttp.ClientSession() as sess, sess.ws_connect(url, heartbeat=20) as ws:
                async for msg in ws:
                    if msg.type != aiohttp.WSMsgType.TEXT:
                        continue
                    data = msg.json()
                    d = data.get("data", {})
                    sym = d.get("s")    # e.g. BTCUSDC
                    event_ms = d.get("E")  # event time (ms)
                    bid = safe_float(d.get("b"))
                    ask = safe_float(d.get("a"))
                    if not sym or bid is None or ask is None:
                        continue
                    # mapēt atpakaļ uz "BASE/QUOTE"
                    # heuristika: atrod atbilstošo pair pēc nosaukuma
                    for p in pairs:
                        if bsymbol_binance(p).upper() == sym.upper():
                            set_quote("binance", p, bid, ask, "ws", event_ms)
                            ws_event_ms[("binance", p)] = event_ms
                            # latency = now - exch_event
                            lat = now_ms() - event_ms if event_ms else None
                            await log_row("binance", p, "ws", event_ms, lat, bid, ask)
                            # brīdinājums, ja pārlieku stāvs
                            if lat is not None and lat > ALERT_LAT_MS:
                                send(f"⚠️ Binance WS stale {p}: {lat} ms")
                            break
        except Exception as e:
            print("[BINANCE WS] restart on error:", e)
            await asyncio.sleep(2.0)

# ─────────────────────────────────────────────────────────────
# Kraken WS (public ticker; nav event timestamp → latency = None,
# bet reģistrējam stāvēšanas laiku relatīvi pēc pēdējā update)
# ─────────────────────────────────────────────────────────────
async def kraken_ws_loop(pairs):
    url = "wss://ws.kraken.com/"
    kpairs = [kpair_kraken(p) for p in pairs]
    while True:
        try:
            async with websockets.connect(url, ping_interval=20) as ws:
                sub = {
                    "event": "subscribe",
                    "pair": kpairs,
                    "subscription": {"name": "ticker"}
                }
                await ws.send(json.dumps(sub))
                while True:
                    raw = await ws.recv()
                    msg = json.loads(raw)
                    # Kraken ticker ziņa ir masīvs: [channelID, {fields}, pair, channelName]
                    if isinstance(msg, list) and len(msg) >= 4:
                        pair_name = msg[3] if isinstance(msg[3], str) else msg[-1]
                        # reverse map uz mūsu pair
                        my_pair = None
                        for p in pairs:
                            if kpair_kraken(p) == pair_name:
                                my_pair = p
                                break
                        if not my_pair:
                            continue
                        payload = msg[1]
                        # bid/ask atslēgas: 'b' -> [price, wholeLotVol, lotVol], 'a' -> [...]
                        bid = None
                        ask = None
                        if isinstance(payload, dict):
                            b = payload.get("b", [])
                            a = payload.get("a", [])
                            bid = safe_float(b[0] if b else None)
                            ask = safe_float(a[0] if a else None)
                        if bid is not None and ask is not None:
                            set_quote("kraken", my_pair, bid, ask, "ws", None)
                            ws_event_ms[("kraken", my_pair)] = now_ms()
                            await log_row("kraken", my_pair, "ws", None, None, bid, ask)
                    # status messages (ignore)
        except Exception as e:
            print("[KRAKEN WS] restart on error:", e)
            await asyncio.sleep(2.0)

# ─────────────────────────────────────────────────────────────
# REST pollers (ccxt) Binance/KuCoin/Kraken — backup un RTT mērījums
# ─────────────────────────────────────────────────────────────
async def rest_poll_loop(venue: str, pairs):
    import ccxt  # vietējais imports, lai WS var startēt ātrāk
    if venue == "binance":
        ex = ccxt.binance()
    elif venue == "kraken":
        ex = ccxt.kraken()
    elif venue == "kucoin":
        ex = ccxt.kucoin()
    else:
        return

    while True:
        start = time.perf_counter()
        for p in pairs:
            try:
                t = await asyncio.to_thread(ex.fetch_ticker, p)
                bid = safe_float(t.get("bid"))
                ask = safe_float(t.get("ask"))
                if bid is None or ask is None:
                    continue
                set_quote(venue, p, bid, ask, "rest", None)
                rtt = (time.perf_counter() - start) * 1000.0
                rest_rtt_ms[(venue, p)] = rtt
                await log_row(venue, p, "rest", None, rtt, bid, ask)
                if rtt > ALERT_LAT_MS * 2:
                    send(f"⚠️ {venue} REST slow {p}: {int(rtt)} ms")
            except Exception as e:
                print(f"[REST {venue}] {p} err:", e)
        await asyncio.sleep(REST_POLL_S)

# ─────────────────────────────────────────────────────────────
# Edge kalkulators + staleness pārbaude
# ─────────────────────────────────────────────────────────────
def edge_bps(qA, qB):
    # B→A: sell at B bid, buy at A ask
    # raw edge = (B_bid - A_ask) / mid * 10000
    if not qA or not qB:
        return None
    a_bid, a_ask = qA["bid"], qA["ask"]
    b_bid, b_ask = qB["bid"], qB["ask"]
    if None in (a_bid, a_ask, b_bid, b_ask):
        return None
    mid = (a_bid + a_ask + b_bid + b_ask) / 4.0
    if mid <= 0:
        return None
    return ((b_bid - a_ask) / mid) * 10000.0

async def edge_print_loop():
    venues = ["binance", "kucoin", "kraken"]
    while True:
        out = []
        for p in PAIRS:
            q = {v: get_quote(v, p) for v in venues}
            # staleness ms = now - last ts_ms (ja ws bez event ts → ts_ms ir lokālais now_ms uz update)
            stale = {v: (now_ms() - q[v]["ts_ms"]) if q.get(v) else math.nan for v in venues}
            e_bk = edge_bps(q.get("binance"), q.get("kraken"))
            e_kb = edge_bps(q.get("kraken"), q.get("binance"))
            e_bk2 = edge_bps(q.get("binance"), q.get("kucoin"))
            e_kb2 = edge_bps(q.get("kucoin"), q.get("binance"))
            e_kk = edge_bps(q.get("kucoin"), q.get("kraken"))
            e_kk2 = edge_bps(q.get("kraken"), q.get("kucoin"))
            out.append({
                "pair": p,
                "stale_ms": {k: (None if math.isnan(v) else int(v)) for k, v in stale.items()},
                "edges": {
                    "binance->kraken": e_bk,
                    "kraken->binance": e_kb,
                    "binance->kucoin": e_bk2,
                    "kucoin->binance": e_kb2,
                    "kucoin->kraken": e_kk,
                    "kraken->kucoin": e_kk2,
                }
            })
        # konsoles izvade
        print("─"*78)
        for row in out:
            p = row["pair"]
            sm = row["stale_ms"]
            ed = row["edges"]
            def fmt(x):
                return "—" if x is None or math.isnan(x) else f"{x:+.2f}bps"
            print(f"[{p}] stale bin={sm['binance']}ms kua={sm['kucoin']}ms kra={sm['kraken']}ms | "
                  f"B→K {fmt(ed['binance->kraken'])}  K→B {fmt(ed['kraken->binance'])} | "
                  f"B→Ku {fmt(ed['binance->kucoin'])} Ku→B {fmt(ed['kucoin->binance'])} | "
                  f"Ku→K {fmt(ed['kucoin->kraken'])} K→Ku {fmt(ed['kraken->kucoin'])}")
        await asyncio.sleep(EDGE_PRINT_S)

# ─────────────────────────────────────────────────────────────
# TG kopsavilkums ik pa laikam
# ─────────────────────────────────────────────────────────────
async def summary_loop():
    while True:
        lines = ["📊 *Feed Latency Summary*"]
        for p in PAIRS:
            sm = {}
            for v in ["binance", "kucoin", "kraken"]:
                q = get_quote(v, p)
                if q:
                    sm[v] = now_ms() - q["ts_ms"]
                else:
                    sm[v] = None
            def fmt_ms(x):
                return "—" if x is None else f"{int(x)} ms"
            lines.append(f"{p}: binance={fmt_ms(sm['binance'])}, kucoin={fmt_ms(sm['kucoin'])}, kraken={fmt_ms(sm['kraken'])}")
        send("\n".join(lines))
        await asyncio.sleep(ALERT_SUMMARY_S)

# ─────────────────────────────────────────────────────────────
# Boot
# ─────────────────────────────────────────────────────────────
async def main():
    print(f"[BOOT] Stage-34 Feed Latency Monitor — pairs={PAIRS} poll={REST_POLL_S}s warn={ALERT_LAT_MS}ms")
    tasks = []

    # WS up
    tasks.append(asyncio.create_task(binance_ws_loop(PAIRS)))
    tasks.append(asyncio.create_task(kraken_ws_loop(PAIRS)))

    # REST up (backup + RTT)
    tasks.append(asyncio.create_task(rest_poll_loop("binance", PAIRS)))
    tasks.append(asyncio.create_task(rest_poll_loop("kucoin",  PAIRS)))
    tasks.append(asyncio.create_task(rest_poll_loop("kraken",  PAIRS)))

    # Edge/staleness printer
    tasks.append(asyncio.create_task(edge_print_loop()))
    # TG summary
    tasks.append(asyncio.create_task(summary_loop()))

    await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("exit")
