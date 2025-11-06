import os, time, asyncio, csv, traceback
import ccxt

from notify import send  # izmanto tavu esošo Telegram helperi

# ─────────────────────────────────────────────────────────────
# ENV
# ─────────────────────────────────────────────────────────────
VENUES = os.getenv("VENUES","binance,kucoin,kraken").split(",")
CHECK_EVERY_S = float(os.getenv("EXEC_CHECK_EVERY_S","2.0"))
ORDER_MAX_AGE_S = float(os.getenv("ORDER_MAX_AGE_S","20"))        # cik ilgi drīkst stāvēt atvērts
RETRY_MAX = int(os.getenv("EXEC_RETRY_MAX","2"))                  # cik reizes drīkst mēģināt pārlikt
PRICE_NUDGE_BPS = float(os.getenv("PRICE_NUDGE_BPS","5.0"))       # cik “bāzes punktus” pabīdīt
MAKER_PAD_BPS = float(os.getenv("MAKER_PAD_BPS","1.0"))           # maker post-only drošības pad
LOG_FILE = os.getenv("EXEC_VERIFIER_LOG","logs/orders_verified.csv")

# ─────────────────────────────────────────────────────────────
# CCXT klienti
# ─────────────────────────────────────────────────────────────
def mk_clients():
    clients = {}
    if "binance" in VENUES:
        clients["binance"] = ccxt.binance({
            "apiKey": os.getenv("BINANCE_API_KEY"),
            "secret": os.getenv("BINANCE_SECRET_KEY"),
            # "options": {"defaultType":"spot"} # ja vajag
        })
    if "kucoin" in VENUES:
        clients["kucoin"] = ccxt.kucoin({
            "apiKey": os.getenv("KUCOIN_API_KEY"),
            "secret": os.getenv("KUCOIN_SECRET_KEY"),
            "password": os.getenv("KUCOIN_PASSPHRASE"),
        })
    if "kraken" in VENUES:
        clients["kraken"] = ccxt.kraken({
            "apiKey": os.getenv("KRAKEN_API_KEY"),
            "secret": os.getenv("KRAKEN_SECRET_KEY"),
        })
    return clients

# ─────────────────────────────────────────────────────────────
# Palīgfunkcijas
# ─────────────────────────────────────────────────────────────
def now_ms():
    return int(time.time() * 1000)

def write_log(row):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    exists = os.path.isfile(LOG_FILE)
    with open(LOG_FILE, "a", newline="") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(["ts","venue","order_id","symbol","side","status","filled","amount","price","cost","action","note"])
        w.writerow(row)

async def safe_fetch_order(ex, venue, order_id, symbol):
    try:
        return await asyncio.to_thread(ex.fetch_order, order_id, symbol)
    except Exception as e:
        write_log([time.time(), venue, order_id, symbol, "", "ERR", "", "", "", "", "fetch_order", str(e)])
        return None

async def safe_cancel_order(ex, venue, order_id, symbol):
    try:
        await asyncio.to_thread(ex.cancel_order, order_id, symbol)
        return True, None
    except Exception as e:
        return False, e

async def safe_ticker(ex, symbol):
    try:
        t = await asyncio.to_thread(ex.fetch_ticker, symbol)
        return t.get("bid"), t.get("ask")
    except Exception:
        return None, None

async def safe_create_order(ex, symbol, side, amount, price, params=None):
    try:
        o = await asyncio.to_thread(ex.create_order, symbol, "limit", side, amount, price, params or {"postOnly": True})
        return o, None
    except Exception as e:
        return None, e

def pretty_p(order):
    return {
        "id": order.get("id"),
        "symbol": order.get("symbol"),
        "side": order.get("side"),
        "status": order.get("status"),
        "amount": order.get("amount"),
        "filled": order.get("filled"),
        "price": order.get("price"),
        "cost": order.get("cost"),
        "timestamp": order.get("timestamp"),
        "info": order.get("info"),
    }

# ─────────────────────────────────────────────────────────────
# Galvenais cikls
# ─────────────────────────────────────────────────────────────
async def monitor():
    print(f"[BOOT] Stage-36 Order Execution Verifier — venues={VENUES} ttl={ORDER_MAX_AGE_S}s retry={RETRY_MAX}")
    send(f"🛡️ Stage-36 Verifier alive\nVenues: {', '.join(VENUES)}\nTTL: {ORDER_MAX_AGE_S}s  Retry: {RETRY_MAX}")

    ex = mk_clients()
    while True:
        try:
            for venue, cli in ex.items():
                # 1) paņem visus atvērtos orderus
                try:
                    open_orders = await asyncio.to_thread(cli.fetch_open_orders)
                except Exception as e:
                    write_log([time.time(), venue, "", "", "", "ERR", "", "", "", "", "fetch_open_orders", str(e)])
                    continue

                for o in open_orders:
                    oid   = o.get("id")
                    sym   = o.get("symbol")
                    side  = o.get("side")
                    amt   = o.get("amount") or 0.0
                    price = o.get("price")
                    ts    = o.get("timestamp") or now_ms()
                    age_s = max(0, (now_ms() - ts)/1000)

                    # 2) apstiprini statusu
                    fresh = await safe_fetch_order(cli, venue, oid, sym)
                    if not fresh:
                        continue

                    status = fresh.get("status","")
                    filled = float(fresh.get("filled") or 0.0)
                    cost   = fresh.get("cost")
                    write_log([time.time(), venue, oid, sym, side, status, filled, amt, price, cost, "poll", f"age={age_s:.1f}s"])

                    # 3) ja izpildīts → TG + log
                    if status == "closed":
                        msg = (f"✅ FILL CONFIRMED\n"
                               f"{venue.upper()} {sym} {side}\n"
                               f"filled: {filled}/{amt} @ {price}\n"
                               f"cost: {cost}")
                        print(msg)
                        send(msg)
                        continue

                    # 4) ja atcelts (no biržas) → TG + log
                    if status == "canceled":
                        msg = (f"⚠️ ORDER CANCELED\n"
                               f"{venue.upper()} {sym} {side}\n"
                               f"id={oid}  filled={filled}/{amt}")
                        print(msg)
                        send(msg)
                        continue

                    # 5) ja vecāks par TTL → cancel (+retry ja ļauts)
                    if age_s >= ORDER_MAX_AGE_S:
                        ok, err = await safe_cancel_order(cli, venue, oid, sym)
                        note = "cancelled" if ok else f"cancel_err:{err}"
                        write_log([time.time(), venue, oid, sym, side, "expired", filled, amt, price, cost, "cancel", note])

                        if ok:
                            msg = (f"⏳ EXPIRED → CANCELED\n"
                                   f"{venue.upper()} {sym} {side}\n"
                                   f"id={oid} age={age_s:.1f}s filled={filled}/{amt}")
                            print(msg)
                            send(msg)
                        else:
                            print(f"[CANCEL ERR] {venue} {sym} id={oid} err={err}")
                            send(f"🚨 CANCEL ERROR\n{venue.upper()} {sym}\n{err}")

                        # 6) Retry (post-only) ar “nudge”
                        if RETRY_MAX > 0:
                            # mēģini atjaunot orderi ar pielabotu cenu
                            bid, ask = await safe_ticker(cli, sym)
                            new_price = price
                            try:
                                if side == "buy":
                                    # nocelt uz leju, vai līdz bid*(1 - pad)
                                    target = (bid or price) * (1 - MAKER_PAD_BPS/10000)
                                    new_price = min(price * (1 + PRICE_NUDGE_BPS/10000), target)
                                else:
                                    # pacelt uz augšu, vai līdz ask*(1 + pad)
                                    target = (ask or price) * (1 + MAKER_PAD_BPS/10000)
                                    new_price = max(price * (1 - PRICE_NUDGE_BPS/10000), target)
                            except Exception:
                                # ja nav bid/ask — paliec pie price*nudge
                                if side == "buy":
                                    new_price = price * (1 + PRICE_NUDGE_BPS/10000)
                                else:
                                    new_price = price * (1 - PRICE_NUDGE_BPS/10000)

                            attempts, last_err = 0, None
                            while attempts < RETRY_MAX:
                                attempts += 1
                                new_order, err = await safe_create_order(cli, sym, side, max(amt - filled, 0.0), new_price, {"postOnly": True})
                                if new_order:
                                    nid = new_order.get("id")
                                    write_log([time.time(), venue, nid, sym, side, "replaced", 0.0, amt - filled, new_price, "", "retry", f"try={attempts}"])
                                    send(f"🔁 RETRY PLACED\n{venue.upper()} {sym} {side}\npx={new_price}  amt={max(amt-filled,0.0)}")
                                    break
                                else:
                                    last_err = err
                                    write_log([time.time(), venue, oid, sym, side, "retry_err", filled, amt, price, cost, "retry", str(err)])
                                    time.sleep(0.25)

                            if attempts >= RETRY_MAX and last_err:
                                send(f"🚫 RETRY FAILED\n{venue.upper()} {sym} {side}\nerr={last_err}")

        except Exception as e:
            traceback.print_exc()
            send(f"🚨 Verifier loop error: {e}")

        await asyncio.sleep(CHECK_EVERY_S)

def main():
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    print(f"[BOOT] Stage-36 Order Execution Verifier — venues={VENUES} ttl={ORDER_MAX_AGE_S}s retry={RETRY_MAX}")
    asyncio.run(monitor())

if __name__ == "__main__":
    main()
