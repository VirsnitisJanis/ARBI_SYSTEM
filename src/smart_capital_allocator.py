import os, json, time
import ccxt
from notify import send

BASE = os.getenv("BASE","USDC")
DESIRED_BASE_SHARE = float(os.getenv("DESIRED_BASE_SHARE","0.85"))
EDGE_FLOOR_BPS = float(os.getenv("EDGE_FLOOR_BPS","1.2"))
MAX_ORDER_USD = float(os.getenv("MAX_ORDER_USD","50"))
MIN_ORDER_USD = float(os.getenv("MIN_ORDER_USD","10"))
MAX_SLIPPAGE_BPS = float(os.getenv("MAX_SLIPPAGE_BPS","15"))
SEND_TG = os.getenv("SEND_TG","1") == "1"

DRY_RUN = os.getenv("DRY_RUN","1") == "1"
LIVE_CONFIRM = os.getenv("LIVE_CONFIRM","NO").upper() == "YES"

def load_weights():
    raw = os.getenv("WEIGHTS_JSON","")
    if not raw:
        return {"binance":1/3,"kucoin":1/3,"kraken":1/3}
    try:
        w = json.loads(raw)
        s = sum(w.values())
        return {k: v/s for k,v in w.items() if v>0}
    except Exception:
        return {"binance":1/3,"kucoin":1/3,"kraken":1/3}

def mk_clients():
    b = ccxt.binance({'apiKey':os.getenv('BINANCE_API_KEY'),'secret':os.getenv('BINANCE_SECRET_KEY')})
    k = ccxt.kucoin({'apiKey':os.getenv('KUCOIN_API_KEY'),
                     'secret':os.getenv('KUCOIN_SECRET_KEY'),
                     'password':os.getenv('KUCOIN_PASSPHRASE')})
    r = ccxt.kraken({'apiKey':os.getenv('KRAKEN_API_KEY'),'secret':os.getenv('KRAKEN_SECRET_KEY')})
    return {"binance":b,"kucoin":k,"kraken":r}

def fetch_balances(ex):
    out = {}
    for name, cli in ex.items():
        try:
            bal = cli.fetch_balance()
            out[name] = {
                "USDC": float(bal["free"].get("USDC",0.0)),
                "BTC":  float(bal["free"].get("BTC",0.0)),
            }
        except Exception as e:
            out[name] = {"USDC":0.0,"BTC":0.0}
            print(f"[{name.upper()}] BAL ERR:", e)
    return out

def fetch_prices(ex, pair="BTC/USDC"):
    px = {}
    for name, cli in ex.items():
        try:
            t = cli.fetch_ticker(pair)
            bid = float(t.get("bid") or 0)
            ask = float(t.get("ask") or 0)
            px[name] = {"bid":bid,"ask":ask,"mid":(bid+ask)/2 if bid and ask else 0.0}
        except Exception as e:
            px[name] = {"bid":0,"ask":0,"mid":0}
            print(f"[{name.upper()}] PX ERR:", e)
    return px

def value_usd(bal, px):
    # portfeļa USD vērtība: USDC + BTC*mid
    return bal["USDC"] + bal["BTC"] * px["mid"]

def within_exchange_rebalance(name, cli, bal, px):
    """Tikai lokāls USDC/BTC sabalansējums līdz DESIRED_BASE_SHARE robežām."""
    mid = px["mid"]
    if mid <= 0: 
        return []

    total = value_usd(bal, px)
    if total < MIN_ORDER_USD:
        return []

    target_usdc = total * DESIRED_BASE_SHARE
    delta_usdc = target_usdc - bal["USDC"]  # + vajag USDC → pārdod BTC; - vajag BTC → pērc BTC
    actions = []

    # robežot soli
    if abs(delta_usdc) < MIN_ORDER_USD:
        return []

    step = max(MIN_ORDER_USD, min(MAX_ORDER_USD, abs(delta_usdc)))

    if delta_usdc > 0:
        # vajag +USDC → pārdod BTC par USDC
        qty_btc = step / mid
        qty_btc = min(qty_btc, max(0.0, bal["BTC"] - 1e-8))
        if qty_btc > 0:
            actions.append(("sell", "BTC/USDC", qty_btc))
    else:
        # vajag -USDC → nopērc BTC (tērē USDC)
        spend = step
        spend = min(spend, max(0.0, bal["USDC"] - 1e-6))
        if spend > 0:
            qty_btc = spend / mid
            actions.append(("buy", "BTC/USDC", qty_btc))

    # Izpilde
    executed = []
    for side, pair, qty in actions:
        if qty <= 0: 
            continue
        if DRY_RUN or not LIVE_CONFIRM:
            print(f"[PLAN {name}] {side.upper()} {qty:.8f} BTC @ ~{mid:.2f} (USD≈{qty*mid:.2f})")
            executed.append((side, qty, mid, "PLAN"))
            continue
        # LIVE: market order ar konservatīvu param
        try:
            if side == "buy":
                order = cli.create_market_buy_order(pair, qty)
            else:
                order = cli.create_market_sell_order(pair, qty)
            executed.append((side, qty, order.get("price") or mid, "LIVE"))
            print(f"[EXEC {name}] {side} {qty:.8f} BTC done")
        except Exception as e:
            print(f"[{name.upper()}] ORDER ERR:", e)
    return executed

def main():
    weights = load_weights()
    ex = mk_clients()
    bals = fetch_balances(ex)
    pxs = fetch_prices(ex)

    # kopsavilkums
    rows = []
    total_usd = 0.0
    for name in ex.keys():
        v = value_usd(bals[name], pxs[name])
        total_usd += v
        rows.append((name, bals[name], pxs[name], v))
    rows.sort(key=lambda x: x[0])

    print("[ALLOC] Current portfolio value by venue:")
    for name, bal, px, val in rows:
        print(f"  - {name:7s}: USDC={bal['USDC']:.2f}  BTC={bal['BTC']:.6f}  mid={px['mid']:.2f}  →  ${val:.2f}")

    # mērķis per-venue (vērtībā)
    targets = {name: total_usd * weights.get(name,0) for name in ex.keys()}

    print("\n[TARGET] Desired allocation (by value):")
    for name in ex.keys():
        print(f"  - {name:7s}: target=${targets[name]:.2f}  (w={weights.get(name,0):.2%})")

    # pagaidām NEdara cross-exchange (adreses/withdraw setup vajadzīgs).
    print("\n[NOTE] Cross-exchange transfers = PLAN ONLY (nav adreses/tīkla parametru).")
    print("       Izpildām tikai lokālu USDC/BTC balansu katrā biržā.")

    # lokāls sabalansējums katrā biržā
    all_exec = []
    for name, cli in ex.items():
        execd = within_exchange_rebalance(name, cli, bals[name], pxs[name])
        all_exec.extend([(name,)+e for e in execd])

    # Telegram
    if SEND_TG:
        lines = ["📊 Capital Allocator"]
        for name, bal, px, val in rows:
            lines.append(f"{name}: ${val:.2f}  (USDC {bal['USDC']:.2f} | BTC {bal['BTC']:.6f})")
        if all_exec:
            lines.append("\nActions:")
            for (venue, side, qty, price, mode) in all_exec:
                lines.append(f"- {venue}: {side} {qty:.6f} BTC @ ~{price:.2f} [{mode}]")
        else:
            lines.append("\nNo local rebalances (under MIN_ORDER_USD).")
        try: send("\n".join(lines))
        except Exception as e: print("[TG ERR]", e)

    # saglabā arī .env.local audit pēdējo palaidi
    with open(".env.local","a") as f:
        f.write(f"\n# Stage-25 capital allocator run at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

if __name__ == "__main__":
    main()
